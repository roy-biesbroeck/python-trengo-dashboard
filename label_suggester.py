"""AI Label Suggester module.

Suggests labels for Trengo tickets using:
- Layer 1: Customer label history (what labels were used before for this customer)
- Layer 2: GPT-4o-mini content classification
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from trengo_client import TrengoClient
from label_config import MANUAL_ONLY_LABELS, ROUTE_LABELS, SUGGESTABLE_LABELS, get_label_definitions_prompt

logger = logging.getLogger("label_suggester")
logger.setLevel(logging.INFO)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

LOG_FILE = os.path.join(DATA_DIR, "label_suggester.log")
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)

HISTORY_CACHE_FILE = os.path.join(DATA_DIR, "customer_label_history.json")


def _count_labels_from_tickets(tickets: List[Dict]) -> Dict[str, int]:
    """Count label occurrences across a list of tickets.
    Excludes MANUAL_ONLY labels from the counts."""
    counts: Dict[str, int] = {}
    for ticket in tickets:
        labels = ticket.get("labels", [])
        if not labels:
            continue
        for label in labels:
            name = label.get("name", "")
            if name and name not in MANUAL_ONLY_LABELS:
                counts[name] = counts.get(name, 0) + 1
    return counts


def _load_history_cache() -> Dict:
    """Load the customer label history cache from disk."""
    if not os.path.exists(HISTORY_CACHE_FILE):
        return {}
    try:
        with open(HISTORY_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_history_cache(cache: Dict):
    """Save the customer label history cache to disk."""
    with open(HISTORY_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _get_contact_id(ticket: Dict) -> Optional[int]:
    """Extract contact ID from a ticket dict."""
    contact_id = ticket.get("contact_id")
    if contact_id:
        return contact_id
    contact = ticket.get("contact")
    if isinstance(contact, dict):
        return contact.get("id")
    return None


def get_customer_label_history(
    client: TrengoClient,
    contact_id: int,
) -> Dict[str, int]:
    """Get label frequency counts for a customer from their closed tickets.
    Returns dict like {"Route Kust": 8, "Support - Kassa": 3}.
    Uses a local cache to avoid repeated API calls."""
    cache = _load_history_cache()
    cache_key = str(contact_id)

    if cache_key in cache:
        return cache[cache_key].get("label_counts", {})

    try:
        closed_tickets = client.get_closed_tickets()
    except Exception as e:
        logger.error(f"Fout bij ophalen gesloten tickets: {e}")
        return {}

    customer_tickets = [
        t for t in closed_tickets
        if _get_contact_id(t) == contact_id
    ]

    for ticket in customer_tickets:
        if "labels" not in ticket or not ticket["labels"]:
            ticket["labels"] = client.get_ticket_labels(ticket["id"])

    label_counts = _count_labels_from_tickets(customer_tickets)

    cache[cache_key] = {
        "label_counts": label_counts,
        "ticket_count": len(customer_tickets),
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_history_cache(cache)

    return label_counts


# ── Layer 2: GPT-4o-mini Content Classification ─────────

_openai_client = None


def _get_openai_client():
    """Lazy-init the OpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client


def _build_classification_prompt(subject: str, message: str) -> str:
    """Build the full prompt for GPT-4o-mini ticket classification."""
    label_defs = get_label_definitions_prompt()
    return f"""Je bent een ticket-classifier voor een Nederlands IT/kassa support bedrijf.
Bepaal welke label(s) van toepassing zijn op dit ticket.

Beschikbare labels:
{label_defs}

Regels:
- Kies ALLEEN uit de bovenstaande labels, verzin nooit nieuwe labels
- Geef per suggestie een confidence score van 0-100
- Een ticket kan meerdere labels hebben (bijv. "Reparatie @klant" + "Route Kust")
- Antwoord ALLEEN in JSON formaat

Antwoord formaat:
{{"suggestions": [{{"label": "Labelnaam", "confidence": 85, "reason": "Korte uitleg"}}]}}

Ticket onderwerp: {subject}
Ticket bericht: {message}"""


def classify_ticket_content(subject: str, message: str) -> List[Dict]:
    """Classify ticket content using GPT-4o-mini.
    Returns list of dicts: [{"label": str, "confidence": int, "reason": str}]
    Returns empty list on any error."""
    try:
        client = _get_openai_client()
        prompt = _build_classification_prompt(subject, message)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            raw = raw.rsplit("```", 1)[0]

        data = json.loads(raw)
        suggestions = data.get("suggestions", [])

        valid = []
        for s in suggestions:
            if s.get("label") in SUGGESTABLE_LABELS:
                valid.append({
                    "label": s["label"],
                    "confidence": int(s.get("confidence", 0)),
                    "reason": s.get("reason", ""),
                })
        return valid

    except json.JSONDecodeError:
        logger.warning(f"Ongeldige JSON van GPT voor ticket: {subject}")
        return []
    except Exception as e:
        logger.error(f"GPT classificatie fout: {e}")
        return []


# ── Suggestion Combiner ──────────────────────────────

ROUTE_HISTORY_STRONG_THRESHOLD = 3


def combine_suggestions(
    customer_history: Dict[str, int],
    content_suggestions: List[Dict],
    threshold: int = 70,
) -> List[Dict]:
    """Combine Layer 1 (history) and Layer 2 (content) suggestions.

    Priority rules:
    - Route labels: customer history wins if strong (>= 3 tickets)
    - Non-route labels: content classification wins, boosted by history
    - All suggestions below confidence threshold are excluded

    Returns list of dicts with: label, confidence, reason, source
    """
    results: Dict[str, Dict] = {}

    # Step 1: Add content suggestions
    for s in content_suggestions:
        label = s["label"]
        confidence = s["confidence"]
        reason = s["reason"]

        if label in customer_history:
            count = customer_history[label]
            boost = min(count * 2, 15)
            confidence = min(confidence + boost, 100)
            reason = f"{reason} (ook {count}x in historie)"

        results[label] = {
            "label": label,
            "confidence": confidence,
            "reason": reason,
            "source": "content",
        }

    # Step 2: For route labels, let history override if strong
    history_routes = {
        name: count for name, count in customer_history.items()
        if name in ROUTE_LABELS and count >= ROUTE_HISTORY_STRONG_THRESHOLD
    }

    if history_routes:
        for route_name in ROUTE_LABELS:
            if route_name in results:
                del results[route_name]

        best_route = max(history_routes, key=history_routes.get)
        best_count = history_routes[best_route]
        confidence = min(60 + best_count * 5, 98)

        results[best_route] = {
            "label": best_route,
            "confidence": confidence,
            "reason": f"Klant eerder {best_count}x op deze route",
            "source": "history",
        }

    # Step 3: Add route from history even if content didn't suggest any route
    if not any(name in results for name in ROUTE_LABELS):
        for name in ROUTE_LABELS:
            count = customer_history.get(name, 0)
            if count >= ROUTE_HISTORY_STRONG_THRESHOLD:
                confidence = min(60 + count * 5, 98)
                results[name] = {
                    "label": name,
                    "confidence": confidence,
                    "reason": f"Klant eerder {count}x op deze route",
                    "source": "history",
                }
                break

    # Step 4: Filter by confidence threshold
    filtered = [
        s for s in results.values()
        if s["confidence"] >= threshold
    ]

    filtered.sort(key=lambda x: x["confidence"], reverse=True)
    return filtered


# ── Suggestion Queue ─────────────────────────────────

QUEUE_FILE = os.path.join(DATA_DIR, "label_suggestions.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "label_feedback.json")


def _load_queue() -> List[Dict]:
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_queue(queue: List[Dict]):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def add_to_queue(suggestion: Dict):
    """Add a ticket suggestion to the queue. Skips duplicates."""
    queue = _load_queue()
    existing_ids = {q["ticket_id"] for q in queue}
    if suggestion["ticket_id"] in existing_ids:
        return
    suggestion["added_at"] = datetime.now(timezone.utc).isoformat()
    queue.append(suggestion)
    _save_queue(queue)


def remove_from_queue(ticket_id: int, label_name: str):
    """Remove a specific label suggestion from a ticket in the queue."""
    queue = _load_queue()
    new_queue = []
    for entry in queue:
        if entry["ticket_id"] == ticket_id:
            entry["suggestions"] = [
                s for s in entry["suggestions"]
                if s["label"] != label_name
            ]
            if entry["suggestions"]:
                new_queue.append(entry)
        else:
            new_queue.append(entry)
    _save_queue(new_queue)


def get_suggestion_queue() -> List[Dict]:
    """Return the current suggestion queue for the UI."""
    return _load_queue()


# ── Feedback Log ─────────────────────────────────────

def _load_feedback() -> List[Dict]:
    if not os.path.exists(FEEDBACK_FILE):
        return []
    try:
        with open(FEEDBACK_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_feedback(feedback: List[Dict]):
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(feedback, f, ensure_ascii=False, indent=2)


def log_feedback(ticket_id: int, label_name: str, action: str, confidence: int):
    """Log an accept or reject decision."""
    feedback = _load_feedback()
    feedback.append({
        "ticket_id": ticket_id,
        "label": label_name,
        "action": action,
        "confidence": confidence,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    _save_feedback(feedback)
    logger.info(f"Feedback: {action} '{label_name}' voor ticket #{ticket_id}")


def get_tagger_stats() -> Dict:
    """Return tagger statistics."""
    feedback = _load_feedback()
    accepted = sum(1 for f in feedback if f["action"] == "accept")
    rejected = sum(1 for f in feedback if f["action"] == "reject")
    total = accepted + rejected
    rate = round(accepted / total * 100) if total > 0 else 0
    return {
        "total_accepted": accepted,
        "total_rejected": rejected,
        "total_decisions": total,
        "acceptance_rate": rate,
    }

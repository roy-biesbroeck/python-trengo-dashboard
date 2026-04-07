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
from label_config import MANUAL_ONLY_LABELS, ROUTE_LABELS, SUGGESTABLE_LABELS, get_label_definitions_prompt, is_internal_contact
from label_history_parser import get_ever_applied_labels
from customer_matcher import CustomerMatcher

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


def _build_internal_classification_prompt(subject: str, message: str, creator_name: str) -> str:
    """Build GPT prompt for tickets created by internal team members."""
    label_defs = get_label_definitions_prompt()
    return f"""Je bent een ticket-classifier voor een Nederlands IT/kassa support bedrijf.

BELANGRIJK: Dit ticket is aangemaakt door een interne collega ({creator_name})
namens een klant. De echte klantnaam staat meestal op de eerste regel(s) van
het bericht, vóór de eigenlijke beschrijving.

Stap 1: Identificeer de echte klantnaam uit het bericht.
Stap 2: Bepaal welke label(s) van toepassing zijn.

Beschikbare labels:
{label_defs}

Regels:
- Kies ALLEEN uit de bovenstaande labels, verzin nooit nieuwe labels
- Geef per suggestie een confidence score van 0-100
- Een ticket kan meerdere labels hebben
- Antwoord ALLEEN in JSON formaat

Antwoord formaat:
{{"extracted_customer": "Klantnaam uit het bericht", "suggestions": [{{"label": "Labelnaam", "confidence": 85, "reason": "Korte uitleg"}}]}}

Ticket onderwerp: {subject}
Ticket bericht: {message}"""


def classify_ticket_content(subject: str, message: str, internal_creator: str = None) -> Dict:
    """Classify ticket content using GPT-4o-mini.

    For internal tickets, also extracts the real customer name.

    Returns dict: {"extracted_customer": str|None, "suggestions": [{"label", "confidence", "reason"}]}
    """
    try:
        client = _get_openai_client()

        if internal_creator:
            prompt = _build_internal_classification_prompt(subject, message, internal_creator)
        else:
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

        extracted_customer = data.get("extracted_customer") if internal_creator else None

        return {
            "extracted_customer": extracted_customer,
            "suggestions": valid,
        }

    except json.JSONDecodeError:
        logger.warning(f"Ongeldige JSON van GPT voor ticket: {subject}")
        return {"extracted_customer": None, "suggestions": []}
    except Exception as e:
        logger.error(f"GPT classificatie fout: {e}")
        return {"extracted_customer": None, "suggestions": []}


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


# ── Scan Orchestrator ────────────────────────────────

_scan_progress = {"current": 0, "total": 0, "phase": "idle"}


def get_scan_progress() -> Dict:
    """Return current scan progress for live UI updates."""
    return _scan_progress.copy()


def scan_for_suggestions(
    client: TrengoClient = None,
    threshold: int = None,
) -> Dict:
    """Scan recent tickets and generate label suggestions."""
    if threshold is None:
        threshold = int(os.getenv("TAGGER_CONFIDENCE_THRESHOLD", "70"))
    if client is None:
        client = TrengoClient()

    result = {
        "scanned": 0,
        "suggested": 0,
        "skipped_has_labels": 0,
        "skipped_in_queue": 0,
        "errors": 0,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    _scan_progress["phase"] = "fetching"
    _scan_progress["current"] = 0
    _scan_progress["total"] = 0

    try:
        open_tickets = client.get_tickets("OPEN")
        assigned_tickets = client.get_tickets("ASSIGNED")
        all_tickets = open_tickets + assigned_tickets

        # Build set of currently active ticket IDs
        active_ids = {t.get("id") for t in all_tickets if isinstance(t, dict) and t.get("id")}

        # Prune queue: remove entries for tickets that are no longer OPEN/ASSIGNED
        queue = _load_queue()
        before_prune = len(queue)
        queue = [q for q in queue if q["ticket_id"] in active_ids]
        if len(queue) < before_prune:
            _save_queue(queue)
            result["pruned"] = before_prune - len(queue)
            logger.info(f"Wachtrij opgeschoond: {result['pruned']} oude tickets verwijderd")

        queued_ids = {q["ticket_id"] for q in queue}

        _scan_progress["phase"] = "processing"
        _scan_progress["total"] = len(all_tickets)
        _scan_progress["current"] = 0

        for ticket in all_tickets:
            _scan_progress["current"] += 1

            if not isinstance(ticket, dict):
                continue

            ticket_id = ticket.get("id")
            if not ticket_id:
                continue

            if ticket_id in queued_ids:
                result["skipped_in_queue"] += 1
                continue

            existing_labels = ticket.get("labels", [])
            if existing_labels:
                result["skipped_has_labels"] += 1
                continue

            result["scanned"] += 1

            try:
                contact = ticket.get("contact", {}) or {}
                contact_id = _get_contact_id(ticket)
                customer_name = contact.get("name", "Onbekend")
                subject = ticket.get("subject", "")

                messages = client.get_ticket_messages(ticket_id)
                inbound = [m for m in messages if m.get("type") == "INBOUND"]
                first_message = inbound[0].get("body", "") if inbound else ""
                message_text = first_message[:1000] if first_message else ""

                # Detect internal ticket
                creator_name = contact.get("name", "")
                internal_creator = creator_name if is_internal_contact(name=creator_name) else None

                # Layer 2: Content classification (first, to get extracted_customer)
                classification = classify_ticket_content(subject, message_text, internal_creator=internal_creator)
                content_suggestions = classification["suggestions"]
                extracted_customer = classification.get("extracted_customer")

                # Layer 1: Customer history
                customer_history = {}
                if internal_creator and extracted_customer:
                    cache = _load_history_cache()
                    matcher = CustomerMatcher(cache)
                    match = matcher.find(extracted_customer)
                    if match:
                        customer_history = match["label_counts"]
                        logger.info(
                            f"Interne ticket #{ticket_id}: klant '{extracted_customer}' "
                            f"gematcht met '{match['customer_name']}' ({match['similarity']:.0%})"
                        )
                elif contact_id:
                    customer_history = get_customer_label_history(client, contact_id)

                suggestions = combine_suggestions(
                    customer_history=customer_history,
                    content_suggestions=content_suggestions,
                    threshold=threshold,
                )

                if suggestions:
                    queue_entry = {
                        "ticket_id": ticket_id,
                        "ticket_subject": subject,
                        "customer_name": extracted_customer or customer_name,
                        "contact_id": contact_id,
                        "message_preview": message_text[:200],
                        "suggestions": suggestions,
                    }
                    if internal_creator:
                        queue_entry["internal_creator"] = internal_creator
                        queue_entry["extracted_customer"] = extracted_customer
                    add_to_queue(queue_entry)
                    result["suggested"] += 1
                    logger.info(
                        f"Suggesties voor ticket #{ticket_id}: "
                        f"{[s['label'] for s in suggestions]}"
                    )

            except Exception as e:
                result["errors"] += 1
                logger.error(f"Fout bij verwerken ticket #{ticket_id}: {e}")

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Scan fout: {e}")

    _scan_progress["phase"] = "idle"
    logger.info(
        f"Scan klaar: {result['scanned']} verwerkt, "
        f"{result['suggested']} suggesties, "
        f"{result['skipped_has_labels']} al gelabeld, "
        f"{result['skipped_in_queue']} al in wachtrij"
    )
    return result


# ── Accept / Reject Actions ──────────────────────────

def accept_suggestion(
    client: TrengoClient = None,
    ticket_id: int = 0,
    label_name: str = "",
) -> Dict:
    """Accept a suggestion: attach label via Trengo API and log feedback."""
    from label_config import get_label_id

    if client is None:
        client = TrengoClient()

    label_id = get_label_id(label_name)
    if label_id is None:
        return {"success": False, "error": f"Onbekend label: {label_name}"}

    queue = _load_queue()
    confidence = 0
    for entry in queue:
        if entry["ticket_id"] == ticket_id:
            for s in entry["suggestions"]:
                if s["label"] == label_name:
                    confidence = s["confidence"]
                    break

    success = client.attach_label(ticket_id, label_id)
    if not success:
        return {"success": False, "error": "Trengo API fout bij koppelen label"}

    log_feedback(ticket_id, label_name, "accept", confidence)
    remove_from_queue(ticket_id, label_name)

    logger.info(f"Label '{label_name}' toegepast op ticket #{ticket_id}")
    return {"success": True}


def reject_suggestion(ticket_id: int, label_name: str) -> Dict:
    """Reject a suggestion: log feedback and remove from queue."""
    queue = _load_queue()
    confidence = 0
    for entry in queue:
        if entry["ticket_id"] == ticket_id:
            for s in entry["suggestions"]:
                if s["label"] == label_name:
                    confidence = s["confidence"]
                    break

    log_feedback(ticket_id, label_name, "reject", confidence)
    remove_from_queue(ticket_id, label_name)

    logger.info(f"Label '{label_name}' afgewezen voor ticket #{ticket_id}")
    return {"success": True}


# ── Cache Refresh ────────────────────────────────────

def refresh_customer_cache(client: TrengoClient = None) -> Dict:
    """Re-scan closed tickets and update the customer label history cache.

    Uses label event parsing from ticket messages for accuracy.
    Excludes internal contacts.
    """
    if client is None:
        client = TrengoClient()

    try:
        closed_tickets = client.get_closed_tickets()
    except Exception as e:
        logger.error(f"Cache refresh fout: {e}")
        return {"error": str(e), "customers_updated": 0}

    # Parse label events from messages
    ticket_labels: Dict[int, set] = {}
    for ticket in closed_tickets:
        tid = ticket["id"]
        try:
            messages = client.get_ticket_messages(tid)
            labels = get_ever_applied_labels(messages)
            labels = {l for l in labels if l not in MANUAL_ONLY_LABELS}
            ticket_labels[tid] = labels
        except Exception:
            ticket_labels[tid] = set()

    # Group by contact, exclude internal
    groups: Dict[int, List[Dict]] = {}
    for ticket in closed_tickets:
        contact_id = _get_contact_id(ticket)
        if not contact_id:
            continue
        contact_name = (ticket.get("contact") or {}).get("name", "")
        if is_internal_contact(name=contact_name):
            continue
        if contact_id not in groups:
            groups[contact_id] = []
        groups[contact_id].append(ticket)

    cache = _load_history_cache()
    updated = 0
    for contact_id, tickets in groups.items():
        label_counts: Dict[str, int] = {}
        for ticket in tickets:
            for label in ticket_labels.get(ticket["id"], set()):
                label_counts[label] = label_counts.get(label, 0) + 1

        if label_counts:
            contact_name = (tickets[0].get("contact") or {}).get("name", "Onbekend")
            cache[str(contact_id)] = {
                "customer_name": contact_name,
                "label_counts": label_counts,
                "ticket_count": len(tickets),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            updated += 1

    _save_history_cache(cache)

    logger.info(f"Cache vernieuwd: {updated} klanten bijgewerkt uit {len(closed_tickets)} tickets")
    return {"customers_updated": updated, "tickets_scanned": len(closed_tickets)}


# ── Auto-Apply Logic ─────────────────────────────────

MIN_DECISIONS_FOR_AUTO = 10


def _should_auto_apply(label_name: str, confidence: int) -> bool:
    """Check if a label should be auto-applied based on historical acceptance rate."""
    if os.getenv("TAGGER_AUTO_APPLY", "false").lower() not in ("true", "1", "yes"):
        return False

    threshold = int(os.getenv("TAGGER_AUTO_APPLY_THRESHOLD", "95"))

    feedback = _load_feedback()
    label_feedback = [f for f in feedback if f["label"] == label_name]

    if len(label_feedback) < MIN_DECISIONS_FOR_AUTO:
        return False

    accepted = sum(1 for f in label_feedback if f["action"] == "accept")
    rate = round(accepted / len(label_feedback) * 100)

    return rate >= threshold


def get_customer_overview() -> List[Dict]:
    """Return all customers with their label history for the overview page."""
    cache = _load_history_cache()
    customers = []
    for contact_id, data in cache.items():
        label_counts = data.get("label_counts", {})
        sorted_labels = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)
        top_labels = [{"name": name, "count": count} for name, count in sorted_labels[:5]]

        customers.append({
            "contact_id": int(contact_id),
            "customer_name": data.get("customer_name", "Onbekend"),
            "label_counts": label_counts,
            "ticket_count": data.get("ticket_count", 0),
            "top_labels": top_labels,
            "total_labels": len(label_counts),
            "cached_at": data.get("cached_at", ""),
        })

    customers.sort(key=lambda x: x["ticket_count"], reverse=True)
    return customers

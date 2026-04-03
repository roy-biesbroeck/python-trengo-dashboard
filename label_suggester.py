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
from label_config import MANUAL_ONLY_LABELS, ROUTE_LABELS, SUGGESTABLE_LABELS

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

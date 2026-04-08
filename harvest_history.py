"""One-time harvest of historical customer label data.

Reads closed tickets and their messages from the SQLite cache, parses label
events, groups by customer, counts labels, and saves to cache.

Usage:
    python scrape_tickets.py   # populate the SQLite cache first
    python harvest_history.py  # then run this (no API calls)
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List

from ticket_cache import init_db
from label_config import MANUAL_ONLY_LABELS, is_internal_contact
from label_history_parser import get_ever_applied_labels

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_CACHE_FILE = os.path.join(DATA_DIR, "customer_label_history.json")


def _load_ticket_from_row(row) -> Dict:
    return json.loads(row["raw_payload"])


def _load_messages_for_ticket(conn, ticket_id: int) -> List[Dict]:
    rows = conn.execute(
        "SELECT raw_payload FROM messages WHERE ticket_id = ? ORDER BY created_at",
        (ticket_id,),
    ).fetchall()
    return [json.loads(r["raw_payload"]) for r in rows]


def _get_contact_id(ticket: Dict):
    contact_id = ticket.get("contact_id")
    if contact_id:
        return contact_id
    contact = ticket.get("contact")
    if isinstance(contact, dict):
        return contact.get("id")
    return None


def _get_contact_name(ticket: Dict) -> str:
    contact = ticket.get("contact")
    if isinstance(contact, dict):
        return contact.get("name", "Onbekend")
    return "Onbekend"


def _group_tickets_by_contact(tickets: List[Dict]) -> Dict[int, List[Dict]]:
    groups: Dict[int, List[Dict]] = {}
    for ticket in tickets:
        contact_id = _get_contact_id(ticket)
        if not contact_id:
            continue
        groups.setdefault(contact_id, []).append(ticket)
    return groups


def harvest_customer_history(conn=None, cache_file: str = None) -> Dict:
    if conn is None:
        conn = init_db()
    if cache_file is None:
        cache_file = DEFAULT_CACHE_FILE

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    print("Tickets lezen uit cache...")
    ticket_rows = conn.execute(
        "SELECT * FROM tickets WHERE status = 'CLOSED'"
    ).fetchall()
    closed_tickets = [_load_ticket_from_row(r) for r in ticket_rows]
    print(f"  {len(closed_tickets)} gesloten tickets in cache")
    if not closed_tickets:
        print("  WAARSCHUWING: cache is leeg. Voer eerst `python scrape_tickets.py` uit.")

    print("  Label events parsen...")
    ticket_labels: Dict[int, set] = {}
    for ticket in closed_tickets:
        tid = ticket["id"]
        messages = _load_messages_for_ticket(conn, tid)
        labels = get_ever_applied_labels(messages)
        labels = {l for l in labels if l not in MANUAL_ONLY_LABELS}
        ticket_labels[tid] = labels

    groups = _group_tickets_by_contact(closed_tickets)
    print(f"  {len(groups)} unieke contacten gevonden")

    cache: Dict = {}
    internal_skipped = 0
    for contact_id, tickets in groups.items():
        contact_name = _get_contact_name(tickets[0])
        if is_internal_contact(name=contact_name):
            internal_skipped += 1
            continue

        label_counts: Dict[str, int] = {}
        for ticket in tickets:
            for label in ticket_labels.get(ticket["id"], set()):
                label_counts[label] = label_counts.get(label, 0) + 1

        if label_counts:
            cache[str(contact_id)] = {
                "customer_name": contact_name,
                "label_counts": label_counts,
                "ticket_count": len(tickets),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    result = {
        "customers_processed": len(groups),
        "customers_with_labels": len(cache),
        "internal_skipped": internal_skipped,
        "tickets_processed": len(closed_tickets),
        "cache_file": cache_file,
    }

    print("\nKlaar!")
    print(f"  {result['customers_processed']} contacten verwerkt")
    print(f"  {result['internal_skipped']} interne contacten overgeslagen")
    print(f"  {result['customers_with_labels']} klanten met labels opgeslagen")
    print(f"  Cache opgeslagen in {cache_file}")

    return result


if __name__ == "__main__":
    # Usage: run scrape_tickets.py first to populate the cache, then this.
    harvest_customer_history()

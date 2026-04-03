"""One-time harvest of historical customer label data.

Fetches closed tickets from Trengo, parses label events from ticket
messages, groups by customer, counts labels, and saves to cache.

Usage:
    python harvest_history.py
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List

from trengo_client import TrengoClient
from label_config import MANUAL_ONLY_LABELS, is_internal_contact
from label_history_parser import get_ever_applied_labels

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_CACHE_FILE = os.path.join(DATA_DIR, "customer_label_history.json")


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
        if contact_id not in groups:
            groups[contact_id] = []
        groups[contact_id].append(ticket)
    return groups


def harvest_customer_history(
    client: TrengoClient = None,
    cache_file: str = None,
) -> Dict:
    if client is None:
        client = TrengoClient()
    if cache_file is None:
        cache_file = DEFAULT_CACHE_FILE

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    print("Ophalen gesloten tickets van Trengo...")
    closed_tickets = client.get_closed_tickets()
    print(f"  {len(closed_tickets)} gesloten tickets opgehaald")

    # Fetch messages for each ticket to parse label events
    total = len(closed_tickets)
    if total > 0:
        print(f"  Berichten ophalen voor {total} tickets (5 parallel)...")
        done = 0

        def fetch_messages(ticket):
            return ticket["id"], client.get_ticket_messages(ticket["id"])

        ticket_messages: Dict[int, list] = {}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(fetch_messages, t): t for t in closed_tickets}
            for future in as_completed(futures):
                tid, messages = future.result()
                ticket_messages[tid] = messages
                done += 1
                if done % 100 == 0:
                    print(f"    {done}/{total} verwerkt...")
    else:
        ticket_messages = {}

    # Parse label events from messages
    print("  Label events parsen...")
    ticket_labels: Dict[int, set] = {}
    for ticket in closed_tickets:
        tid = ticket["id"]
        messages = ticket_messages.get(tid, [])
        labels = get_ever_applied_labels(messages)
        labels = {l for l in labels if l not in MANUAL_ONLY_LABELS}
        ticket_labels[tid] = labels

    # Group by contact, exclude internal contacts
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

    print(f"\nKlaar!")
    print(f"  {result['customers_processed']} contacten verwerkt")
    print(f"  {result['internal_skipped']} interne contacten overgeslagen")
    print(f"  {result['customers_with_labels']} klanten met labels opgeslagen")
    print(f"  Cache opgeslagen in {cache_file}")

    return result


if __name__ == "__main__":
    harvest_customer_history()

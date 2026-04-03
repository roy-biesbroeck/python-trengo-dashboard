"""One-time harvest of historical customer label data.

Fetches closed tickets from Trengo, groups by customer, counts label
usage, and saves to the customer label history cache.

Usage:
    python harvest_history.py
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List

from trengo_client import TrengoClient
from label_config import MANUAL_ONLY_LABELS

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


def _count_labels(tickets: List[Dict]) -> Dict[str, int]:
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

    tickets_without_labels = [
        t for t in closed_tickets if not t.get("labels")
    ]
    if tickets_without_labels:
        total = len(tickets_without_labels)
        print(f"  Labels ophalen voor {total} tickets (5 parallel)...")
        done = 0

        def fetch_labels(ticket):
            return ticket["id"], client.get_ticket_labels(ticket["id"])

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(fetch_labels, t): t for t in tickets_without_labels}
            for future in as_completed(futures):
                ticket = futures[future]
                ticket_id, labels = future.result()
                ticket["labels"] = labels
                done += 1
                if done % 100 == 0:
                    print(f"    {done}/{total} verwerkt...")

    groups = _group_tickets_by_contact(closed_tickets)
    print(f"  {len(groups)} unieke klanten gevonden")

    cache: Dict = {}
    for contact_id, tickets in groups.items():
        label_counts = _count_labels(tickets)
        if label_counts:
            # Get customer name from the first ticket's contact data
            customer_name = "Onbekend"
            for t in tickets:
                contact = t.get("contact")
                if isinstance(contact, dict) and contact.get("name"):
                    customer_name = contact["name"]
                    break
            cache[str(contact_id)] = {
                "customer_name": customer_name,
                "label_counts": label_counts,
                "ticket_count": len(tickets),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    result = {
        "customers_processed": len(groups),
        "customers_with_labels": len(cache),
        "tickets_processed": len(closed_tickets),
        "cache_file": cache_file,
    }

    print(f"\nKlaar!")
    print(f"  {result['customers_processed']} klanten verwerkt")
    print(f"  {result['customers_with_labels']} klanten met labels opgeslagen")
    print(f"  Cache opgeslagen in {cache_file}")

    return result


if __name__ == "__main__":
    harvest_customer_history()

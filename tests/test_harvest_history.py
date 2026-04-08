import json
import pytest
from harvest_history import harvest_customer_history, _group_tickets_by_contact
from ticket_cache import init_db, upsert_ticket, upsert_messages


def _ticket(id, contact_id, contact_name=None, closed_at="2026-03-15T10:00:00+00:00"):
    return {
        "id": id,
        "contact_id": contact_id,
        "contact": {"id": contact_id, "name": contact_name or f"Klant {contact_id}"},
        "subject": f"Ticket {id}",
        "status": "CLOSED",
        "created_at": "2026-03-14T09:00:00Z",
        "closed_at": closed_at,
        "messages_count": 1,
    }


def _label_messages(ticket_id, label_events):
    msgs = []
    for i, (label, action) in enumerate(label_events):
        if action == "added":
            body = f"Label {label} toegevoegd door Test op 01-04-2026, 10:00"
        else:
            body = f"Label {label} verwijderd door Test op 01-04-2026, 15:00"
        msgs.append({
            "id": ticket_id * 1000 + i,
            "ticket_id": ticket_id,
            "created_at": "2026-03-14T09:00:00Z",
            "type": "SYSTEM",
            "body": body,
        })
    return msgs


def _make_conn(tickets_and_messages):
    """tickets_and_messages: list of (ticket_dict, [message_dicts])"""
    conn = init_db(":memory:")
    for ticket, messages in tickets_and_messages:
        upsert_ticket(conn, ticket)
        if messages:
            upsert_messages(conn, ticket["id"], messages)
    return conn


class TestGroupTicketsByContact:
    def test_groups_correctly(self):
        tickets = [
            {"id": 1, "contact_id": 100, "contact": {"id": 100, "name": "Klant 100"}},
            {"id": 2, "contact_id": 100, "contact": {"id": 100, "name": "Klant 100"}},
            {"id": 3, "contact_id": 200, "contact": {"id": 200, "name": "Klant 200"}},
            {"id": 4, "contact_id": 100, "contact": {"id": 100, "name": "Klant 100"}},
        ]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 2
        assert len(groups[100]) == 3
        assert len(groups[200]) == 1

    def test_skips_tickets_without_contact(self):
        tickets = [
            {"id": 1, "contact_id": None, "contact": None},
            {"id": 2, "contact_id": 100, "contact": {"id": 100, "name": "Klant 100"}},
        ]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 1


class TestHarvestWithLabelEvents:
    def test_uses_message_events_for_labels(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        conn = _make_conn([
            (_ticket(1, 100, contact_name="Restaurant De Haven"),
             _label_messages(1, [("Route Kust", "added"), ("Support - Kassa", "added")])),
            (_ticket(2, 100, contact_name="Restaurant De Haven"),
             _label_messages(2, [("Route Kust", "added")])),
        ])

        result = harvest_customer_history(conn=conn, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert cache["100"]["label_counts"]["Route Kust"] == 2
        assert cache["100"]["label_counts"]["Support - Kassa"] == 1

    def test_captures_labels_removed_before_closing(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        conn = _make_conn([
            (_ticket(1, 100, contact_name="Test Klant"),
             _label_messages(1, [("Route Kust", "added"), ("Route Kust", "removed")])),
        ])

        harvest_customer_history(conn=conn, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert cache["100"]["label_counts"]["Route Kust"] == 1

    def test_excludes_internal_contacts(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        conn = _make_conn([
            (_ticket(1, 100, contact_name="Restaurant De Haven"),
             _label_messages(1, [("Route Kust", "added")])),
            (_ticket(2, 999, contact_name="Jos Biesbroeck"),
             _label_messages(2, [("Route Hulst", "added"), ("Bestelling", "added")])),
        ])

        harvest_customer_history(conn=conn, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert "100" in cache
        assert "999" not in cache

    def test_excludes_manual_only_labels(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        conn = _make_conn([
            (_ticket(1, 100, contact_name="Test"),
             _label_messages(1, [("Route Kust", "added"), ("Route Jos", "added")])),
        ])

        harvest_customer_history(conn=conn, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert "Route Kust" in cache["100"]["label_counts"]
        assert "Route Jos" not in cache["100"]["label_counts"]

    def test_handles_empty_closed_tickets(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        conn = init_db(":memory:")

        result = harvest_customer_history(conn=conn, cache_file=cache_file)
        assert result["customers_processed"] == 0
        assert result["tickets_processed"] == 0

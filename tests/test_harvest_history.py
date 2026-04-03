import pytest
import json
from unittest.mock import patch, MagicMock
from harvest_history import harvest_customer_history, _group_tickets_by_contact


def _ticket(id, contact_id, labels=None, closed_at="2026-03-15T10:00:00+00:00",
            contact_name=None):
    return {
        "id": id,
        "contact_id": contact_id,
        "contact": {"id": contact_id, "name": contact_name or f"Klant {contact_id}"},
        "closed_at": closed_at,
    }


def _label_messages(label_events):
    msgs = []
    for label, action in label_events:
        if action == "added":
            msgs.append({"body": f"Label {label} toegevoegd door Test op 01-04-2026, 10:00", "type": "SYSTEM"})
        elif action == "removed":
            msgs.append({"body": f"Label {label} verwijderd door Test op 01-04-2026, 15:00", "type": "SYSTEM"})
    return msgs


class TestGroupTicketsByContact:
    def test_groups_correctly(self):
        tickets = [_ticket(1, 100), _ticket(2, 100), _ticket(3, 200), _ticket(4, 100)]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 2
        assert len(groups[100]) == 3
        assert len(groups[200]) == 1

    def test_skips_tickets_without_contact(self):
        tickets = [
            {"id": 1, "contact_id": None, "contact": None},
            _ticket(2, 100),
        ]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 1


class TestHarvestWithLabelEvents:
    def test_uses_message_events_for_labels(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Restaurant De Haven"),
            _ticket(2, 100, contact_name="Restaurant De Haven"),
        ]
        mock_client.get_ticket_messages.side_effect = lambda tid: {
            1: _label_messages([("Route Kust", "added"), ("Support - Kassa", "added")]),
            2: _label_messages([("Route Kust", "added")]),
        }[tid]

        result = harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert cache["100"]["label_counts"]["Route Kust"] == 2
        assert cache["100"]["label_counts"]["Support - Kassa"] == 1

    def test_captures_labels_removed_before_closing(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Test Klant"),
        ]
        mock_client.get_ticket_messages.return_value = _label_messages([
            ("Route Kust", "added"),
            ("Route Kust", "removed"),
        ])

        harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert cache["100"]["label_counts"]["Route Kust"] == 1

    def test_excludes_internal_contacts(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Restaurant De Haven"),
            _ticket(2, 999, contact_name="Jos Biesbroeck"),
        ]
        mock_client.get_ticket_messages.side_effect = lambda tid: {
            1: _label_messages([("Route Kust", "added")]),
            2: _label_messages([("Route Hulst", "added"), ("Bestelling", "added")]),
        }[tid]

        harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert "100" in cache
        assert "999" not in cache

    def test_excludes_manual_only_labels(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, contact_name="Test"),
        ]
        mock_client.get_ticket_messages.return_value = _label_messages([
            ("Route Kust", "added"),
            ("Route Jos", "added"),
        ])

        harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert "Route Kust" in cache["100"]["label_counts"]
        assert "Route Jos" not in cache["100"]["label_counts"]

    def test_handles_empty_closed_tickets(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = []

        result = harvest_customer_history(client=mock_client, cache_file=cache_file)
        assert result["customers_processed"] == 0
        assert result["tickets_processed"] == 0

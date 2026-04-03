import pytest
import json
from unittest.mock import patch, MagicMock
from harvest_history import harvest_customer_history, _group_tickets_by_contact


def _ticket(id, contact_id, labels, closed_at="2026-03-15T10:00:00+00:00"):
    return {
        "id": id,
        "contact_id": contact_id,
        "contact": {"id": contact_id, "name": f"Klant {contact_id}"},
        "labels": [{"name": name} for name in labels],
        "closed_at": closed_at,
    }


class TestGroupTicketsByContact:
    def test_groups_correctly(self):
        tickets = [
            _ticket(1, 100, ["Route Kust", "Support - Kassa"]),
            _ticket(2, 100, ["Route Kust"]),
            _ticket(3, 200, ["Boekhoudkoppeling"]),
            _ticket(4, 100, ["Route Kust", "RMA"]),
        ]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 2
        assert len(groups[100]) == 3
        assert len(groups[200]) == 1

    def test_skips_tickets_without_contact(self):
        tickets = [
            {"id": 1, "contact_id": None, "contact": None, "labels": [{"name": "RMA"}]},
            _ticket(2, 100, ["Route Kust"]),
        ]
        groups = _group_tickets_by_contact(tickets)
        assert len(groups) == 1
        assert 100 in groups


class TestHarvestCustomerHistory:
    def test_builds_cache_from_closed_tickets(self, tmp_path):
        cache_file = str(tmp_path / "customer_label_history.json")

        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, ["Route Kust", "Support - Kassa"]),
            _ticket(2, 100, ["Route Kust"]),
            _ticket(3, 100, ["Route Kust", "Boekhoudkoppeling"]),
            _ticket(4, 200, ["Route Hulst"]),
            _ticket(5, 200, ["Route Hulst", "HH - PAX"]),
        ]
        mock_client.get_ticket_labels.return_value = []

        result = harvest_customer_history(client=mock_client, cache_file=cache_file)

        assert result["customers_processed"] == 2
        assert result["tickets_processed"] == 5

        with open(cache_file) as f:
            cache = json.load(f)

        assert cache["100"]["label_counts"]["Route Kust"] == 3
        assert cache["100"]["label_counts"]["Support - Kassa"] == 1
        assert cache["200"]["label_counts"]["Route Hulst"] == 2

    def test_skips_manual_only_labels(self, tmp_path):
        cache_file = str(tmp_path / "customer_label_history.json")

        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, 100, ["Route Kust", "Route Jos"]),
        ]

        harvest_customer_history(client=mock_client, cache_file=cache_file)

        with open(cache_file) as f:
            cache = json.load(f)

        assert "Route Kust" in cache["100"]["label_counts"]
        assert "Route Jos" not in cache["100"]["label_counts"]

    def test_handles_empty_closed_tickets(self, tmp_path):
        cache_file = str(tmp_path / "customer_label_history.json")

        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = []

        result = harvest_customer_history(client=mock_client, cache_file=cache_file)
        assert result["customers_processed"] == 0
        assert result["tickets_processed"] == 0

import pytest
import json
import os
from unittest.mock import patch, MagicMock
from label_suggester import (
    get_customer_label_history,
    _count_labels_from_tickets,
)


def _ticket(id, subject, created_at, contact_id=100, labels=None):
    """Helper to build a fake ticket dict."""
    t = {
        "id": id,
        "subject": subject,
        "created_at": created_at,
        "contact_id": contact_id,
        "contact": {"id": contact_id},
    }
    if labels:
        t["labels"] = labels
    return t


class TestCountLabelsFromTickets:
    def test_counts_labels_correctly(self):
        tickets = [
            {"labels": [{"name": "Route Kust"}, {"name": "Support - Kassa"}]},
            {"labels": [{"name": "Route Kust"}, {"name": "Boekhoudkoppeling"}]},
            {"labels": [{"name": "Route Kust"}]},
        ]
        counts = _count_labels_from_tickets(tickets)
        assert counts == {
            "Route Kust": 3,
            "Support - Kassa": 1,
            "Boekhoudkoppeling": 1,
        }

    def test_empty_tickets(self):
        assert _count_labels_from_tickets([]) == {}

    def test_tickets_without_labels(self):
        tickets = [{"id": 1}, {"id": 2, "labels": []}]
        assert _count_labels_from_tickets(tickets) == {}

    def test_excludes_manual_only_labels(self):
        tickets = [
            {"labels": [{"name": "Route Kust"}, {"name": "Route Jos"}]},
        ]
        counts = _count_labels_from_tickets(tickets)
        assert "Route Kust" in counts
        assert "Route Jos" not in counts


class TestGetCustomerLabelHistory:
    def test_returns_label_counts_for_customer(self):
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            _ticket(1, "Kassa stuk", "2026-03-01T10:00:00+00:00", contact_id=200,
                    labels=[{"name": "Support - Kassa"}, {"name": "Route Kust"}]),
            _ticket(2, "Printer issue", "2026-03-05T10:00:00+00:00", contact_id=200,
                    labels=[{"name": "Route Kust"}]),
            _ticket(3, "Ander klant", "2026-03-05T10:00:00+00:00", contact_id=300,
                    labels=[{"name": "Route Hulst"}]),
        ]

        with patch("label_suggester._load_history_cache", return_value={}), \
             patch("label_suggester._save_history_cache"):
            result = get_customer_label_history(mock_client, contact_id=200)
        assert result["Route Kust"] == 2
        assert result.get("Support - Kassa") == 1
        assert "Route Hulst" not in result

    def test_no_history_returns_empty(self):
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = []

        with patch("label_suggester._load_history_cache", return_value={}), \
             patch("label_suggester._save_history_cache"):
            result = get_customer_label_history(mock_client, contact_id=999)
        assert result == {}

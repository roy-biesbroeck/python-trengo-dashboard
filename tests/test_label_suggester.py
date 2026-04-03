import pytest
import json
import os
from unittest.mock import patch, MagicMock
from label_suggester import (
    get_customer_label_history,
    _count_labels_from_tickets,
    classify_ticket_content,
    _build_classification_prompt,
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


class TestBuildClassificationPrompt:
    def test_contains_label_definitions(self):
        prompt = _build_classification_prompt("Kassa kapot", "Onze kassa start niet meer op")
        assert "Route Kust" in prompt
        assert "Support - Kassa" in prompt
        assert "Route Jos" not in prompt

    def test_contains_ticket_content(self):
        prompt = _build_classification_prompt("Printer stuk", "De bonprinter werkt niet meer")
        assert "Printer stuk" in prompt
        assert "De bonprinter werkt niet meer" in prompt


class TestClassifyTicketContent:
    def test_returns_suggestions_from_gpt(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 92, "reason": "Kassa probleem"},
                {"label": "Reparatie @BA", "confidence": 75, "reason": "Apparaat kapot"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content("Kassa kapot", "De kassa doet het niet meer")

        assert len(result) == 2
        assert result[0]["label"] == "Support - Kassa"
        assert result[0]["confidence"] == 92

    def test_returns_empty_on_api_error(self):
        with patch("label_suggester._get_openai_client", side_effect=Exception("API down")):
            result = classify_ticket_content("Test", "Test bericht")
        assert result == []

    def test_returns_empty_on_malformed_response(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json at all"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content("Test", "Test bericht")
        assert result == []

    def test_filters_out_unknown_labels(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa"},
                {"label": "Verzonnen Label", "confidence": 85, "reason": "Nep"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content("Test", "Test")
        assert len(result) == 1
        assert result[0]["label"] == "Support - Kassa"

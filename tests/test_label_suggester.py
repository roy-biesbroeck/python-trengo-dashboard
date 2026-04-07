import pytest
import json
import os
from unittest.mock import patch, MagicMock
from label_suggester import (
    get_customer_label_history,
    _count_labels_from_tickets,
    classify_ticket_content,
    _build_classification_prompt,
    _build_internal_classification_prompt,
    combine_suggestions,
    add_to_queue, remove_from_queue, get_suggestion_queue,
    log_feedback, get_tagger_stats,
    scan_for_suggestions,
    refresh_customer_cache, _should_auto_apply,
    accept_suggestion, reject_suggestion,
    QUEUE_FILE, FEEDBACK_FILE,
)


@pytest.fixture
def clean_data_files(tmp_path):
    """Use temp files for queue and feedback during tests."""
    queue_file = str(tmp_path / "label_suggestions.json")
    feedback_file = str(tmp_path / "label_feedback.json")
    with patch("label_suggester.QUEUE_FILE", queue_file), \
         patch("label_suggester.FEEDBACK_FILE", feedback_file):
        yield queue_file, feedback_file


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

        assert len(result["suggestions"]) == 2
        assert result["suggestions"][0]["label"] == "Support - Kassa"
        assert result["suggestions"][0]["confidence"] == 92

    def test_returns_empty_on_api_error(self):
        with patch("label_suggester._get_openai_client", side_effect=Exception("API down")):
            result = classify_ticket_content("Test", "Test bericht")
        assert result["suggestions"] == []
        assert result["extracted_customer"] is None

    def test_returns_empty_on_malformed_response(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json at all"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content("Test", "Test bericht")
        assert result["suggestions"] == []
        assert result["extracted_customer"] is None

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
        assert len(result["suggestions"]) == 1
        assert result["suggestions"][0]["label"] == "Support - Kassa"


class TestCombineSuggestions:
    def test_content_only_no_history(self):
        content_suggestions = [
            {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa probleem"},
            {"label": "Reparatie @BA", "confidence": 80, "reason": "Reparatie nodig"},
        ]
        result = combine_suggestions(
            customer_history={},
            content_suggestions=content_suggestions,
            threshold=70,
        )
        assert len(result) == 2
        assert result[0]["label"] == "Support - Kassa"

    def test_route_from_history_when_visit_needed(self):
        customer_history = {"Route Kust": 8, "Support - Kassa": 2}
        content_suggestions = [
            {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa probleem"},
        ]
        result = combine_suggestions(
            customer_history=customer_history,
            content_suggestions=content_suggestions,
            threshold=70,
            needs_visit=True,
        )
        labels = [s["label"] for s in result]
        assert "Route Kust" in labels
        assert "Support - Kassa" in labels

    def test_no_route_when_visit_not_needed(self):
        """Route history exists but ticket doesn't need a visit — no route suggested."""
        customer_history = {"Route Kust": 27}
        content_suggestions = [
            {"label": "Bestelling", "confidence": 80, "reason": "Administratief"},
        ]
        result = combine_suggestions(
            customer_history=customer_history,
            content_suggestions=content_suggestions,
            threshold=70,
            needs_visit=False,
        )
        labels = [s["label"] for s in result]
        assert "Route Kust" not in labels
        assert "Bestelling" in labels

    def test_confidence_threshold_filters_low(self):
        content_suggestions = [
            {"label": "Support - Kassa", "confidence": 90, "reason": "Zeker"},
            {"label": "RMA", "confidence": 50, "reason": "Misschien"},
        ]
        result = combine_suggestions(
            customer_history={},
            content_suggestions=content_suggestions,
            threshold=70,
        )
        labels = [s["label"] for s in result]
        assert "Support - Kassa" in labels
        assert "RMA" not in labels

    def test_history_boosts_matching_content(self):
        customer_history = {"Support - Kassa": 5}
        content_suggestions = [
            {"label": "Support - Kassa", "confidence": 72, "reason": "Kassa"},
        ]
        result = combine_suggestions(
            customer_history=customer_history,
            content_suggestions=content_suggestions,
            threshold=70,
        )
        assert len(result) == 1
        assert result[0]["confidence"] > 72

    def test_route_from_history_shows_count_when_visit_needed(self):
        customer_history = {"Route Kust": 6}
        content_suggestions = []
        result = combine_suggestions(
            customer_history=customer_history,
            content_suggestions=content_suggestions,
            threshold=70,
            needs_visit=True,
        )
        assert len(result) == 1
        assert result[0]["label"] == "Route Kust"
        assert "6x" in result[0]["reason"]
        assert result[0]["source"] == "history"


class TestSuggestionQueue:
    def test_add_and_get_queue(self, clean_data_files):
        suggestion = {
            "ticket_id": 100,
            "ticket_subject": "Kassa kapot",
            "customer_name": "Restaurant De Haven",
            "contact_id": 200,
            "message_preview": "Onze kassa start niet meer op...",
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 92,
                 "reason": "Kassa probleem", "source": "content"},
            ],
        }
        add_to_queue(suggestion)
        queue = get_suggestion_queue()
        assert len(queue) == 1
        assert queue[0]["ticket_id"] == 100

    def test_no_duplicate_tickets_in_queue(self, clean_data_files):
        suggestion = {
            "ticket_id": 100, "ticket_subject": "Kassa kapot",
            "customer_name": "Test", "contact_id": 200,
            "message_preview": "Test",
            "suggestions": [{"label": "RMA", "confidence": 80,
                             "reason": "Test", "source": "content"}],
        }
        add_to_queue(suggestion)
        add_to_queue(suggestion)
        queue = get_suggestion_queue()
        assert len(queue) == 1

    def test_remove_from_queue(self, clean_data_files):
        add_to_queue({
            "ticket_id": 100, "ticket_subject": "A", "customer_name": "X",
            "contact_id": 1, "message_preview": "...",
            "suggestions": [{"label": "RMA", "confidence": 80,
                             "reason": "R", "source": "content"}],
        })
        add_to_queue({
            "ticket_id": 200, "ticket_subject": "B", "customer_name": "Y",
            "contact_id": 2, "message_preview": "...",
            "suggestions": [{"label": "Urgent", "confidence": 90,
                             "reason": "R", "source": "content"}],
        })
        remove_from_queue(ticket_id=100, label_name="RMA")
        queue = get_suggestion_queue()
        t100 = [q for q in queue if q["ticket_id"] == 100]
        if t100:
            labels = [s["label"] for s in t100[0]["suggestions"]]
            assert "RMA" not in labels


class TestFeedbackLog:
    def test_log_accept(self, clean_data_files):
        log_feedback(ticket_id=100, label_name="Support - Kassa",
                     action="accept", confidence=92)
        stats = get_tagger_stats()
        assert stats["total_accepted"] == 1
        assert stats["total_rejected"] == 0

    def test_log_reject(self, clean_data_files):
        log_feedback(ticket_id=100, label_name="RMA",
                     action="reject", confidence=75)
        stats = get_tagger_stats()
        assert stats["total_accepted"] == 0
        assert stats["total_rejected"] == 1

    def test_acceptance_rate(self, clean_data_files):
        for i in range(8):
            log_feedback(ticket_id=i, label_name="A", action="accept", confidence=90)
        for i in range(2):
            log_feedback(ticket_id=100+i, label_name="B", action="reject", confidence=70)
        stats = get_tagger_stats()
        assert stats["acceptance_rate"] == 80


class TestScanForSuggestions:
    def test_scans_untagged_tickets_and_adds_to_queue(self, clean_data_files):
        mock_client = MagicMock()
        mock_client.get_tickets.side_effect = lambda s: [
            {
                "id": 501, "subject": "Kassa kapot", "status": "OPEN",
                "created_at": "2026-04-03T10:00:00+00:00",
                "contact": {"id": 200, "name": "Restaurant De Haven"},
                "labels": [],
            },
        ] if s == "OPEN" else [
            {
                "id": 502, "subject": "Factuur", "status": "ASSIGNED",
                "created_at": "2026-04-03T09:00:00+00:00",
                "contact": {"id": 300, "name": "Bakkerij Janssen"},
                "labels": [{"name": "Boedhoudkoppeling"}],
            },
        ]
        mock_client.get_ticket_messages.return_value = [
            {"body": "Onze kassa start niet meer op na de update", "type": "INBOUND"},
        ]
        mock_client.get_closed_tickets.return_value = []

        mock_gpt_result = {
            "extracted_customer": None,
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa probleem"},
            ],
        }
        with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result), \
             patch("label_suggester._load_history_cache", return_value={}), \
             patch("label_suggester._save_history_cache"):
            result = scan_for_suggestions(client=mock_client, threshold=70)

        assert result["scanned"] == 1
        assert result["suggested"] == 1
        assert result["skipped_has_labels"] == 1

        queue = get_suggestion_queue()
        assert len(queue) == 1
        assert queue[0]["ticket_id"] == 501

    def test_skips_tickets_already_in_queue(self, clean_data_files):
        add_to_queue({
            "ticket_id": 501, "ticket_subject": "Old", "customer_name": "X",
            "contact_id": 1, "message_preview": "...",
            "suggestions": [{"label": "RMA", "confidence": 80,
                             "reason": "R", "source": "content"}],
        })

        mock_client = MagicMock()
        mock_client.get_tickets.side_effect = lambda s: [
            {
                "id": 501, "subject": "Kassa kapot", "status": "OPEN",
                "created_at": "2026-04-03T10:00:00+00:00",
                "contact": {"id": 200, "name": "Test"},
                "labels": [],
            },
        ] if s == "OPEN" else []

        result = scan_for_suggestions(client=mock_client, threshold=70)
        assert result["skipped_in_queue"] == 1

    def test_no_suggestions_when_below_threshold(self, clean_data_files):
        mock_client = MagicMock()
        mock_client.get_tickets.side_effect = lambda s: [
            {
                "id": 601, "subject": "Vaag bericht", "status": "OPEN",
                "created_at": "2026-04-03T10:00:00+00:00",
                "contact": {"id": 400, "name": "Test"},
                "labels": [],
            },
        ] if s == "OPEN" else []
        mock_client.get_ticket_messages.return_value = [
            {"body": "Hallo", "type": "INBOUND"},
        ]
        mock_client.get_closed_tickets.return_value = []

        mock_gpt_result = {
            "extracted_customer": None,
            "suggestions": [
                {"label": "Urgent", "confidence": 30, "reason": "Misschien"},
            ],
        }
        with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result), \
             patch("label_suggester._load_history_cache", return_value={}), \
             patch("label_suggester._save_history_cache"):
            result = scan_for_suggestions(client=mock_client, threshold=70)

        assert result["suggested"] == 0
        queue = get_suggestion_queue()
        assert len(queue) == 0


class TestRefreshCustomerCache:
    def test_updates_cache_from_closed_tickets(self, clean_data_files):
        mock_client = MagicMock()
        mock_client.get_closed_tickets.return_value = [
            {
                "id": 1, "contact_id": 100,
                "contact": {"id": 100, "name": "Test"},
                "closed_at": "2026-04-01T10:00:00+00:00",
            },
            {
                "id": 2, "contact_id": 100,
                "contact": {"id": 100, "name": "Test"},
                "closed_at": "2026-04-02T10:00:00+00:00",
            },
            {
                "id": 3, "contact_id": 200,
                "contact": {"id": 200, "name": "Ander"},
                "closed_at": "2026-04-03T10:00:00+00:00",
            },
        ]
        mock_client.get_ticket_messages.return_value = []

        label_map = {
            1: {"Route Kust", "Support - Kassa"},
            2: {"Route Kust"},
            3: {"Boekhoudkoppeling"},
        }
        call_order = [1, 2, 3]
        call_index = {"i": 0}

        def fake_ever_applied(msgs):
            tid = call_order[call_index["i"]]
            call_index["i"] += 1
            return label_map[tid]

        # Also patch the history cache file to use tmp
        cache_file = str(clean_data_files[0]).replace("label_suggestions", "customer_label_history")
        with patch("label_suggester.HISTORY_CACHE_FILE", cache_file), \
             patch("label_suggester.get_ever_applied_labels", side_effect=fake_ever_applied):
            result = refresh_customer_cache(client=mock_client)

        assert result["customers_updated"] >= 2


class TestShouldAutoApply:
    def test_auto_apply_when_enabled_and_high_rate(self, clean_data_files):
        for i in range(19):
            log_feedback(i, "Support - Kassa", "accept", 90)
        log_feedback(99, "Support - Kassa", "reject", 90)

        with patch.dict("os.environ", {
            "TAGGER_AUTO_APPLY": "true",
            "TAGGER_AUTO_APPLY_THRESHOLD": "95",
        }):
            assert _should_auto_apply("Support - Kassa", 92) is True

    def test_no_auto_apply_when_disabled(self, clean_data_files):
        for i in range(20):
            log_feedback(i, "RMA", "accept", 90)

        with patch.dict("os.environ", {"TAGGER_AUTO_APPLY": "false"}):
            assert _should_auto_apply("RMA", 92) is False

    def test_no_auto_apply_when_rate_too_low(self, clean_data_files):
        for i in range(5):
            log_feedback(i, "Urgent", "accept", 90)
        for i in range(5):
            log_feedback(10 + i, "Urgent", "reject", 90)

        with patch.dict("os.environ", {
            "TAGGER_AUTO_APPLY": "true",
            "TAGGER_AUTO_APPLY_THRESHOLD": "95",
        }):
            assert _should_auto_apply("Urgent", 90) is False

    def test_no_auto_apply_with_insufficient_data(self, clean_data_files):
        for i in range(3):
            log_feedback(i, "Kassarollen", "accept", 90)

        with patch.dict("os.environ", {
            "TAGGER_AUTO_APPLY": "true",
            "TAGGER_AUTO_APPLY_THRESHOLD": "95",
        }):
            assert _should_auto_apply("Kassarollen", 90) is False


class TestAcceptReject:
    def test_accept_calls_trengo_and_logs(self, clean_data_files):
        add_to_queue({
            "ticket_id": 100, "ticket_subject": "Test", "customer_name": "X",
            "contact_id": 200, "message_preview": "...",
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 90,
                 "reason": "Kassa", "source": "content"},
                {"label": "Route Kust", "confidence": 85,
                 "reason": "Route", "source": "history"},
            ],
        })

        mock_client = MagicMock()
        mock_client.attach_label.return_value = True

        result = accept_suggestion(
            client=mock_client,
            ticket_id=100,
            label_name="Support - Kassa",
        )

        assert result["success"] is True
        mock_client.attach_label.assert_called_once_with(100, 1807989)

        stats = get_tagger_stats()
        assert stats["total_accepted"] == 1

        queue = get_suggestion_queue()
        t100 = [q for q in queue if q["ticket_id"] == 100]
        assert len(t100) == 1
        labels = [s["label"] for s in t100[0]["suggestions"]]
        assert "Support - Kassa" not in labels
        assert "Route Kust" in labels

    def test_accept_fails_when_trengo_fails(self, clean_data_files):
        add_to_queue({
            "ticket_id": 100, "ticket_subject": "Test", "customer_name": "X",
            "contact_id": 200, "message_preview": "...",
            "suggestions": [
                {"label": "RMA", "confidence": 80, "reason": "R", "source": "content"},
            ],
        })

        mock_client = MagicMock()
        mock_client.attach_label.return_value = False

        result = accept_suggestion(
            client=mock_client, ticket_id=100, label_name="RMA",
        )

        assert result["success"] is False
        queue = get_suggestion_queue()
        assert len(queue) == 1

    def test_reject_logs_and_removes(self, clean_data_files):
        add_to_queue({
            "ticket_id": 100, "ticket_subject": "Test", "customer_name": "X",
            "contact_id": 200, "message_preview": "...",
            "suggestions": [
                {"label": "RMA", "confidence": 80, "reason": "R", "source": "content"},
            ],
        })

        reject_suggestion(ticket_id=100, label_name="RMA")

        stats = get_tagger_stats()
        assert stats["total_rejected"] == 1

        queue = get_suggestion_queue()
        assert len(queue) == 0


class TestBuildInternalClassificationPrompt:
    def test_includes_internal_instruction(self):
        prompt = _build_internal_classification_prompt(
            "Kassa kapot", "La Porte Dór\n\nKassa start niet meer op",
            creator_name="Jos Biesbroeck",
        )
        assert "interne collega" in prompt
        assert "Jos Biesbroeck" in prompt

    def test_includes_label_definitions(self):
        prompt = _build_internal_classification_prompt("Test", "Test", creator_name="Jos")
        assert "Route Kust" in prompt
        assert "Support - Kassa" in prompt

    def test_requests_extracted_customer(self):
        prompt = _build_internal_classification_prompt("Test", "Test", creator_name="Jos")
        assert "extracted_customer" in prompt

    def test_normal_prompt_unchanged(self):
        prompt = _build_classification_prompt("Test", "Test bericht")
        assert "interne collega" not in prompt


class TestClassifyInternalTicket:
    def test_returns_extracted_customer(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "extracted_customer": "La Porte Dór",
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 88, "reason": "Kassa probleem"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content(
                "Kassa kapot", "La Porte Dór\n\nKassa start niet op",
                internal_creator="Jos Biesbroeck",
            )

        assert result["extracted_customer"] == "La Porte Dór"
        assert len(result["suggestions"]) == 1

    def test_normal_ticket_no_extracted_customer(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa"},
            ]
        })

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("label_suggester._get_openai_client", return_value=mock_client):
            result = classify_ticket_content("Kassa kapot", "Mijn kassa doet het niet")

        assert result["extracted_customer"] is None
        assert len(result["suggestions"]) == 1


class TestScanInternalTicket:
    def test_internal_ticket_uses_extracted_customer_history(self, clean_data_files):
        mock_client = MagicMock()
        mock_client.get_tickets.side_effect = lambda s: [
            {
                "id": 701, "subject": "Kassa kapot", "status": "OPEN",
                "created_at": "2026-04-03T10:00:00+00:00",
                "contact": {"id": 999, "name": "Jos Biesbroeck"},
                "labels": [],
            },
        ] if s == "OPEN" else []
        mock_client.get_ticket_messages.return_value = [
            {"body": "La Porte Dór\n\nKassa start niet op", "type": "INBOUND"},
        ]

        mock_gpt_result = {
            "extracted_customer": "La Porte Dór",
            "needs_visit": True,
            "suggestions": [
                {"label": "Support - Kassa", "confidence": 90, "reason": "Kassa probleem"},
            ],
        }

        mock_cache = {
            "100": {
                "customer_name": "La Porte Dór",
                "label_counts": {"Route Kust": 8},
                "ticket_count": 10,
            },
        }

        with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result), \
             patch("label_suggester._load_history_cache", return_value=mock_cache), \
             patch("label_suggester._save_history_cache"):
            result = scan_for_suggestions(client=mock_client, threshold=70)

        assert result["suggested"] == 1
        queue = get_suggestion_queue()
        assert len(queue) == 1

        suggestions = queue[0]["suggestions"]
        labels = [s["label"] for s in suggestions]
        assert "Route Kust" in labels
        assert "Support - Kassa" in labels

    def test_internal_ticket_unknown_customer(self, clean_data_files):
        mock_client = MagicMock()
        mock_client.get_tickets.side_effect = lambda s: [
            {
                "id": 702, "subject": "Overname", "status": "OPEN",
                "created_at": "2026-04-03T10:00:00+00:00",
                "contact": {"id": 999, "name": "Jos Biesbroeck"},
                "labels": [],
            },
        ] if s == "OPEN" else []
        mock_client.get_ticket_messages.return_value = [
            {"body": "Nieuw Restaurant\n\nOvername per 1 juni", "type": "INBOUND"},
        ]

        mock_gpt_result = {
            "extracted_customer": "Nieuw Restaurant",
            "suggestions": [
                {"label": "Bestelling", "confidence": 75, "reason": "Overname"},
            ],
        }

        with patch("label_suggester.classify_ticket_content", return_value=mock_gpt_result), \
             patch("label_suggester._load_history_cache", return_value={}), \
             patch("label_suggester._save_history_cache"):
            result = scan_for_suggestions(client=mock_client, threshold=70)

        assert result["suggested"] == 1
        queue = get_suggestion_queue()
        suggestions = queue[0]["suggestions"]
        assert any(s["label"] == "Bestelling" for s in suggestions)

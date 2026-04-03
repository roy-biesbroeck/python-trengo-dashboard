import pytest
from label_history_parser import parse_label_events, get_effective_labels, get_ever_applied_labels


class TestParseLabelEvents:
    def test_parses_added_event(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy Ernst op 03-04-2026, 08:37", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert len(events) == 1
        assert events[0]["label"] == "Route Kust"
        assert events[0]["action"] == "added"

    def test_parses_removed_event(self):
        messages = [
            {"body": "Label Route Kust verwijderd door Ziggy op 03-04-2026, 15:00", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert len(events) == 1
        assert events[0]["label"] == "Route Kust"
        assert events[0]["action"] == "removed"

    def test_parses_multiple_events(self):
        messages = [
            {"body": "Hallo, mijn kassa doet het niet", "type": "INBOUND"},
            {"body": "Label Support - Kassa toegevoegd door Roy Ernst op 03-04-2026, 08:37", "type": "SYSTEM"},
            {"body": "Label Route Kust toegevoegd door Roy Ernst op 03-04-2026, 08:37", "type": "SYSTEM"},
            {"body": "We kijken ernaar", "type": "OUTBOUND"},
            {"body": "Label Route Jos toegevoegd door Jos Biesbroeck op 03-04-2026, 09:25", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert len(events) == 3
        labels = [e["label"] for e in events]
        assert "Support - Kassa" in labels
        assert "Route Kust" in labels
        assert "Route Jos" in labels

    def test_ignores_non_label_messages(self):
        messages = [
            {"body": "Hallo, mijn kassa doet het niet", "type": "INBOUND"},
            {"body": "We kijken ernaar", "type": "OUTBOUND"},
            {"body": "Automatisch toegewezen aan Team Support", "type": "SYSTEM"},
        ]
        events = parse_label_events(messages)
        assert events == []

    def test_handles_none_body(self):
        messages = [{"body": None, "type": "SYSTEM"}, {}]
        events = parse_label_events(messages)
        assert events == []


class TestGetEffectiveLabels:
    def test_added_only(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa toegevoegd door Roy op 01-04-2026, 10:01", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert labels == {"Route Kust", "Support - Kassa"}

    def test_added_then_removed(self):
        messages = [
            {"body": "Label Route Hulst toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Route Hulst verwijderd door Roy op 01-04-2026, 10:05", "type": "SYSTEM"},
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:06", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert "Route Hulst" not in labels
        assert "Route Kust" in labels

    def test_removed_without_add_ignored(self):
        messages = [
            {"body": "Label Urgent verwijderd door Ziggy op 01-04-2026, 15:00", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert labels == set()

    def test_label_removed_and_re_added(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Route Kust verwijderd door Ziggy op 01-04-2026, 15:00", "type": "SYSTEM"},
            {"body": "Label Route Kust toegevoegd door Roy op 02-04-2026, 09:00", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert "Route Kust" in labels

    def test_all_removed_before_closing(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa toegevoegd door Roy op 01-04-2026, 10:01", "type": "SYSTEM"},
            {"body": "Label Route Kust verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
        ]
        labels = get_effective_labels(messages)
        assert labels == set()


class TestGetEverAppliedLabels:
    def test_captures_removed_labels(self):
        messages = [
            {"body": "Label Route Kust toegevoegd door Roy op 01-04-2026, 10:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa toegevoegd door Roy op 01-04-2026, 10:01", "type": "SYSTEM"},
            {"body": "Label Route Kust verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
            {"body": "Label Support - Kassa verwijderd door Ziggy op 03-04-2026, 16:00", "type": "SYSTEM"},
        ]
        labels = get_ever_applied_labels(messages)
        assert "Route Kust" in labels
        assert "Support - Kassa" in labels

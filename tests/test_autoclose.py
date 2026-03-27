import pytest
from autoclose import find_ruijie_duplicates


def _ticket(id, subject, created_at, status="OPEN"):
    return {"id": id, "subject": subject, "created_at": created_at, "status": status}


def test_no_ruijie_tickets():
    tickets = [
        _ticket(1, "Help me", "2026-03-27T10:00:00+00:00"),
        _ticket(2, "Other issue", "2026-03-27T11:00:00+00:00"),
    ]
    keep, close = find_ruijie_duplicates(tickets)
    assert keep is None
    assert close == []


def test_single_ruijie_ticket_no_duplicates():
    tickets = [
        _ticket(1, "Ruijie Cloud Alarm Notification", "2026-03-27T10:00:00+00:00"),
    ]
    keep, close = find_ruijie_duplicates(tickets)
    assert keep == 1
    assert close == []


def test_multiple_ruijie_tickets_keeps_newest():
    tickets = [
        _ticket(1, "Ruijie Cloud Alarm Notification", "2026-03-25T10:00:00+00:00"),
        _ticket(2, "Ruijie Cloud Alarm Notification", "2026-03-27T12:00:00+00:00"),
        _ticket(3, "Ruijie Cloud Alarm Notification", "2026-03-26T08:00:00+00:00"),
        _ticket(4, "Other ticket", "2026-03-27T15:00:00+00:00"),
    ]
    keep, close = find_ruijie_duplicates(tickets)
    assert keep == 2
    assert sorted(close) == [1, 3]


def test_ruijie_match_is_case_insensitive():
    tickets = [
        _ticket(1, "ruijie cloud alarm notification", "2026-03-25T10:00:00+00:00"),
        _ticket(2, "Ruijie Cloud Alarm Notification", "2026-03-27T12:00:00+00:00"),
    ]
    keep, close = find_ruijie_duplicates(tickets)
    assert keep == 2
    assert close == [1]


def test_assigned_tickets_included():
    tickets = [
        _ticket(1, "Ruijie Cloud Alarm Notification", "2026-03-25T10:00:00+00:00", "ASSIGNED"),
        _ticket(2, "Ruijie Cloud Alarm Notification", "2026-03-27T12:00:00+00:00", "OPEN"),
    ]
    keep, close = find_ruijie_duplicates(tickets)
    assert keep == 2
    assert close == [1]

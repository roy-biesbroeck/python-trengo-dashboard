import pytest
from unittest.mock import patch, MagicMock, call
from autoclose import find_ruijie_duplicates, run_autoclose


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


def _make_mock_client(open_tickets, assigned_tickets):
    client = MagicMock()
    client.get_tickets.side_effect = lambda s: open_tickets if s == "OPEN" else assigned_tickets
    client.close_ticket.return_value = True
    return client


def test_run_autoclose_dry_run_does_not_close():
    client = _make_mock_client(
        open_tickets=[
            _ticket(1, "Ruijie Cloud Alarm Notification", "2026-03-25T10:00:00+00:00"),
            _ticket(2, "Ruijie Cloud Alarm Notification", "2026-03-27T12:00:00+00:00"),
        ],
        assigned_tickets=[],
    )
    result = run_autoclose(client=client, dry_run=True)

    assert result["kept"] == 2
    assert result["closed_ids"] == []
    assert result["would_close_ids"] == [1]
    assert result["dry_run"] is True
    client.close_ticket.assert_not_called()


def test_run_autoclose_closes_duplicates():
    client = _make_mock_client(
        open_tickets=[
            _ticket(1, "Ruijie Cloud Alarm Notification", "2026-03-25T10:00:00+00:00"),
            _ticket(2, "Ruijie Cloud Alarm Notification", "2026-03-27T12:00:00+00:00"),
            _ticket(3, "Ruijie Cloud Alarm Notification", "2026-03-26T08:00:00+00:00"),
        ],
        assigned_tickets=[],
    )
    result = run_autoclose(client=client, dry_run=False)

    assert result["kept"] == 2
    assert sorted(result["closed_ids"]) == [1, 3]
    assert result["would_close_ids"] == []
    assert result["dry_run"] is False
    assert client.close_ticket.call_count == 2


def test_run_autoclose_respects_max_per_run():
    tickets = [
        _ticket(i, "Ruijie Cloud Alarm Notification", f"2026-03-{10+i:02d}T10:00:00+00:00")
        for i in range(25)
    ]
    client = _make_mock_client(open_tickets=tickets, assigned_tickets=[])
    result = run_autoclose(client=client, dry_run=False, max_per_run=5)

    assert len(result["closed_ids"]) == 5
    assert result["capped"] is True


def test_run_autoclose_no_ruijie_tickets():
    client = _make_mock_client(
        open_tickets=[_ticket(1, "Help me", "2026-03-27T10:00:00+00:00")],
        assigned_tickets=[],
    )
    result = run_autoclose(client=client, dry_run=False)

    assert result["kept"] is None
    assert result["closed_ids"] == []

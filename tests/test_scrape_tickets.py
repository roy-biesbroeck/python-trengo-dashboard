from unittest.mock import MagicMock
from ticket_cache import init_db, get_ticket, get_messages
from scrape_tickets import scrape_all_closed


def _fake_client(tickets, messages_by_id):
    client = MagicMock()
    client.get_all_closed_tickets.return_value = tickets
    client.get_ticket_messages.side_effect = lambda tid: messages_by_id.get(tid, [])
    return client


def _ticket(tid, msgs=2, closed_at="2026-04-01T10:00:00Z"):
    return {
        "id": tid,
        "contact_id": 10,
        "subject": f"T{tid}",
        "status": "CLOSED",
        "created_at": "2026-03-30T09:00:00Z",
        "closed_at": closed_at,
        "messages_count": msgs,
        "contact": {"id": 10, "name": "Test"},
    }


def _msg(mid, ticket_id):
    return {
        "id": mid,
        "ticket_id": ticket_id,
        "created_at": "2026-03-30T09:00:00Z",
        "type": "INBOUND",
        "body": f"body {mid}",
    }


def test_scrape_all_closed_writes_new_tickets_and_messages():
    conn = init_db(":memory:")
    tickets = [_ticket(1), _ticket(2)]
    messages = {
        1: [_msg(101, 1), _msg(102, 1)],
        2: [_msg(201, 2), _msg(202, 2)],
    }
    client = _fake_client(tickets, messages)

    stats = scrape_all_closed(client, conn)

    assert stats["total_remote"] == 2
    assert stats["new_or_updated"] == 2
    assert stats["skipped_unchanged"] == 0
    assert get_ticket(conn, 1)["subject"] == "T1"
    assert len(get_messages(conn, 1)) == 2


def test_scrape_all_closed_skips_unchanged_tickets_on_second_run():
    conn = init_db(":memory:")
    tickets = [_ticket(1), _ticket(2)]
    messages = {1: [_msg(101, 1)], 2: [_msg(201, 2)]}
    client = _fake_client(tickets, messages)

    scrape_all_closed(client, conn)
    client.get_ticket_messages.reset_mock()

    stats = scrape_all_closed(client, conn)

    assert stats["skipped_unchanged"] == 2
    assert stats["new_or_updated"] == 0
    client.get_ticket_messages.assert_not_called()  # no Trengo calls for unchanged


def test_scrape_all_closed_refetches_when_message_count_changes():
    conn = init_db(":memory:")
    client = _fake_client([_ticket(1, msgs=2)], {1: [_msg(101, 1), _msg(102, 1)]})
    scrape_all_closed(client, conn)

    # Ticket now has an extra message
    client.get_all_closed_tickets.return_value = [_ticket(1, msgs=3)]
    client.get_ticket_messages.side_effect = lambda tid: [
        _msg(101, 1), _msg(102, 1), _msg(103, 1)
    ]

    stats = scrape_all_closed(client, conn)
    assert stats["new_or_updated"] == 1
    assert len(get_messages(conn, 1)) == 3


def test_scrape_all_closed_calls_progress_callback():
    conn = init_db(":memory:")
    tickets = [_ticket(i) for i in range(1, 6)]
    messages = {i: [_msg(i * 10, i)] for i in range(1, 6)}
    client = _fake_client(tickets, messages)

    calls = []
    def cb(done, total):
        calls.append((done, total))

    scrape_all_closed(client, conn, progress_cb=cb)

    assert calls, "progress_cb should have been invoked at least once"
    last_done, last_total = calls[-1]
    assert last_total == 5
    assert last_done == 5


def test_scrape_all_closed_continues_when_one_fetch_raises():
    """A single failing fetch must not abort the entire run."""
    conn = init_db(":memory:")
    tickets = [_ticket(1), _ticket(2), _ticket(3)]
    client = MagicMock()
    client.get_all_closed_tickets.return_value = tickets

    def flaky(tid):
        if tid == 2:
            raise RuntimeError("simulated network error")
        return [_msg(tid * 10, tid)]

    client.get_ticket_messages.side_effect = flaky

    stats = scrape_all_closed(client, conn)

    assert stats["errors"] == 1
    assert stats["new_or_updated"] == 2
    # Tickets 1 and 3 made it; 2 didn't
    assert get_ticket(conn, 1) is not None
    assert get_ticket(conn, 3) is not None
    assert get_ticket(conn, 2) is None

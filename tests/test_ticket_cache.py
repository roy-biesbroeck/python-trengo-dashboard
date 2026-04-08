import sqlite3
import pytest
from ticket_cache import init_db


def test_init_db_creates_tickets_and_messages_tables():
    conn = init_db(":memory:")
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "tickets" in tables
    assert "messages" in tables


def test_init_db_tickets_has_expected_columns():
    conn = init_db(":memory:")
    cursor = conn.execute("PRAGMA table_info(tickets)")
    columns = {row[1] for row in cursor.fetchall()}
    expected = {
        "ticket_id", "contact_id", "subject", "status",
        "created_at", "closed_at", "message_count",
        "raw_payload", "scraped_at",
    }
    assert expected.issubset(columns)


def test_init_db_messages_has_expected_columns():
    conn = init_db(":memory:")
    cursor = conn.execute("PRAGMA table_info(messages)")
    columns = {row[1] for row in cursor.fetchall()}
    expected = {
        "message_id", "ticket_id", "created_at",
        "author_type", "body_text", "raw_payload",
    }
    assert expected.issubset(columns)


def test_init_db_is_idempotent():
    """Calling init_db twice on the same path must not raise."""
    conn = init_db(":memory:")
    # Same connection handle; re-running the DDL should be a no-op
    from ticket_cache import _apply_schema
    _apply_schema(conn)  # should not raise
    conn.execute("SELECT 1 FROM tickets")


from ticket_cache import compute_fingerprint, strip_html


def test_compute_fingerprint_stable_for_identical_ticket():
    t1 = {"closed_at": "2026-04-01T10:00:00Z", "messages_count": 7}
    t2 = {"closed_at": "2026-04-01T10:00:00Z", "messages_count": 7}
    assert compute_fingerprint(t1) == compute_fingerprint(t2)


def test_compute_fingerprint_changes_when_closed_at_changes():
    t1 = {"closed_at": "2026-04-01T10:00:00Z", "messages_count": 7}
    t2 = {"closed_at": "2026-04-02T10:00:00Z", "messages_count": 7}
    assert compute_fingerprint(t1) != compute_fingerprint(t2)


def test_compute_fingerprint_changes_when_message_count_changes():
    t1 = {"closed_at": "2026-04-01T10:00:00Z", "messages_count": 7}
    t2 = {"closed_at": "2026-04-01T10:00:00Z", "messages_count": 8}
    assert compute_fingerprint(t1) != compute_fingerprint(t2)


def test_compute_fingerprint_handles_missing_fields():
    """Should not raise on tickets missing closed_at or messages_count."""
    assert compute_fingerprint({}) == compute_fingerprint({})
    assert compute_fingerprint({"closed_at": None}) == compute_fingerprint({})


def test_strip_html_removes_tags_and_collapses_whitespace():
    html = "<p>Hallo  <b>wereld</b></p>\n<br><div>Test</div>"
    assert strip_html(html) == "Hallo wereld Test"


def test_strip_html_handles_none():
    assert strip_html(None) == ""


def test_strip_html_handles_plain_text():
    assert strip_html("gewoon tekst") == "gewoon tekst"


import json
from ticket_cache import init_db, upsert_ticket, upsert_messages, get_ticket, get_messages


def _sample_ticket(tid=101, contact_id=55, closed_at="2026-04-01T10:00:00Z", msgs=3):
    return {
        "id": tid,
        "contact_id": contact_id,
        "subject": "Kassa start niet op",
        "status": "CLOSED",
        "created_at": "2026-03-30T09:00:00Z",
        "closed_at": closed_at,
        "messages_count": msgs,
        "contact": {"id": contact_id, "name": "Bakkerij Jansen"},
    }


def _sample_messages(ticket_id=101):
    return [
        {
            "id": 9001,
            "ticket_id": ticket_id,
            "created_at": "2026-03-30T09:00:00Z",
            "type": "INBOUND",
            "body": "<p>De kassa geeft een foutmelding E42</p>",
        },
        {
            "id": 9002,
            "ticket_id": ticket_id,
            "created_at": "2026-03-30T09:05:00Z",
            "type": "OUTBOUND",
            "body": "Kunt u de kassa herstarten?",
        },
    ]


def test_upsert_ticket_inserts_new_row():
    conn = init_db(":memory:")
    was_written = upsert_ticket(conn, _sample_ticket())
    assert was_written is True

    row = get_ticket(conn, 101)
    assert row["ticket_id"] == 101
    assert row["contact_id"] == 55
    assert row["subject"] == "Kassa start niet op"
    assert row["status"] == "CLOSED"
    assert row["closed_at"] == "2026-04-01T10:00:00Z"
    assert row["message_count"] == 3
    # raw_payload round-trips as JSON
    payload = json.loads(row["raw_payload"])
    assert payload["id"] == 101


def test_upsert_ticket_skips_unchanged_ticket():
    conn = init_db(":memory:")
    upsert_ticket(conn, _sample_ticket())
    was_written = upsert_ticket(conn, _sample_ticket())
    assert was_written is False  # fingerprint unchanged


def test_upsert_ticket_updates_when_fingerprint_changes():
    conn = init_db(":memory:")
    upsert_ticket(conn, _sample_ticket(msgs=3))
    was_written = upsert_ticket(conn, _sample_ticket(msgs=5))
    assert was_written is True
    row = get_ticket(conn, 101)
    assert row["message_count"] == 5


def test_upsert_messages_stores_stripped_body():
    conn = init_db(":memory:")
    upsert_ticket(conn, _sample_ticket())
    count = upsert_messages(conn, 101, _sample_messages())
    assert count == 2
    msgs = get_messages(conn, 101)
    assert len(msgs) == 2
    first = next(m for m in msgs if m["message_id"] == 9001)
    assert first["body_text"] == "De kassa geeft een foutmelding E42"
    assert first["author_type"] == "INBOUND"


def test_upsert_messages_replaces_existing_messages_for_ticket():
    """Re-upserting must not duplicate rows."""
    conn = init_db(":memory:")
    upsert_ticket(conn, _sample_ticket())
    upsert_messages(conn, 101, _sample_messages())
    upsert_messages(conn, 101, _sample_messages())  # same again
    assert len(get_messages(conn, 101)) == 2


def test_get_ticket_returns_none_for_missing_id():
    conn = init_db(":memory:")
    assert get_ticket(conn, 999) is None


from ticket_cache import get_customer_tickets, get_all_ticket_fingerprints


def test_get_customer_tickets_returns_rows_for_that_contact_only():
    conn = init_db(":memory:")
    upsert_ticket(conn, _sample_ticket(tid=1, contact_id=10))
    upsert_ticket(conn, _sample_ticket(tid=2, contact_id=10))
    upsert_ticket(conn, _sample_ticket(tid=3, contact_id=99))
    rows = get_customer_tickets(conn, 10)
    assert {r["ticket_id"] for r in rows} == {1, 2}


def test_get_all_ticket_fingerprints_returns_id_to_fingerprint_map():
    conn = init_db(":memory:")
    upsert_ticket(conn, _sample_ticket(tid=1, msgs=3))
    upsert_ticket(conn, _sample_ticket(tid=2, msgs=7))
    fps = get_all_ticket_fingerprints(conn)
    assert set(fps.keys()) == {1, 2}
    assert fps[1] != fps[2]

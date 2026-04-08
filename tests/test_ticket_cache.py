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

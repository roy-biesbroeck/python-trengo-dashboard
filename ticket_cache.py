"""SQLite-backed cache of Trengo tickets and messages.

Stores raw Trengo payloads verbatim alongside a few indexed columns so
downstream features can query historical data without hitting the Trengo API.
"""

import os
import sqlite3
from typing import Optional
import json
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "ticket_analysis.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id     INTEGER PRIMARY KEY,
    contact_id    INTEGER,
    subject       TEXT,
    status        TEXT,
    created_at    TEXT,
    closed_at     TEXT,
    message_count INTEGER,
    raw_payload   TEXT NOT NULL,
    scraped_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tickets_contact  ON tickets(contact_id);
CREATE INDEX IF NOT EXISTS idx_tickets_closed   ON tickets(closed_at);

CREATE TABLE IF NOT EXISTS messages (
    message_id   INTEGER PRIMARY KEY,
    ticket_id    INTEGER NOT NULL,
    created_at   TEXT,
    author_type  TEXT,
    body_text    TEXT,
    raw_payload  TEXT NOT NULL,
    FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_ticket ON messages(ticket_id);
"""


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def init_db(path: Optional[str] = None) -> sqlite3.Connection:
    """Open (or create) the cache database and ensure the schema is applied."""
    if path is None:
        path = DEFAULT_DB_PATH
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_schema(conn)
    return conn


import re


def compute_fingerprint(ticket: dict) -> str:
    """Stable identifier of a ticket's current content state.

    Changes if the ticket is reopened and re-closed (closed_at moves) or if
    new messages are added (messages_count changes). Used to decide whether
    to re-fetch messages for a ticket we already have cached.
    """
    closed_at = ticket.get("closed_at") or ""
    message_count = ticket.get("messages_count") or 0
    return f"{closed_at}|{message_count}"


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(value) -> str:
    """Convert HTML-ish message body to plain text. Safe for None."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    text = _WS_RE.sub(" ", text).strip()
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _existing_fingerprint(conn: sqlite3.Connection, ticket_id: int) -> Optional[str]:
    row = conn.execute(
        "SELECT closed_at, message_count FROM tickets WHERE ticket_id = ?",
        (ticket_id,),
    ).fetchone()
    if row is None:
        return None
    return compute_fingerprint(
        {"closed_at": row["closed_at"], "messages_count": row["message_count"]}
    )


def upsert_ticket(conn: sqlite3.Connection, ticket: dict) -> bool:
    """Insert or update a ticket. Returns True if a write occurred,
    False if the cached row was already current (fingerprint unchanged)."""
    ticket_id = ticket["id"]
    new_fp = compute_fingerprint(ticket)
    old_fp = _existing_fingerprint(conn, ticket_id)
    if old_fp is not None and old_fp == new_fp:
        return False

    contact = ticket.get("contact") or {}
    contact_id = ticket.get("contact_id") or contact.get("id")

    conn.execute(
        """
        INSERT INTO tickets (
            ticket_id, contact_id, subject, status,
            created_at, closed_at, message_count,
            raw_payload, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticket_id) DO UPDATE SET
            contact_id    = excluded.contact_id,
            subject       = excluded.subject,
            status        = excluded.status,
            created_at    = excluded.created_at,
            closed_at     = excluded.closed_at,
            message_count = excluded.message_count,
            raw_payload   = excluded.raw_payload,
            scraped_at    = excluded.scraped_at
        """,
        (
            ticket_id,
            contact_id,
            ticket.get("subject"),
            ticket.get("status"),
            ticket.get("created_at"),
            ticket.get("closed_at"),
            ticket.get("messages_count") or 0,
            json.dumps(ticket, ensure_ascii=False),
            _now_iso(),
        ),
    )
    conn.commit()
    return True


def upsert_messages(
    conn: sqlite3.Connection, ticket_id: int, messages: list
) -> int:
    """Replace all messages for a ticket with the supplied list. Returns
    the number of messages written."""
    conn.execute("DELETE FROM messages WHERE ticket_id = ?", (ticket_id,))
    rows = []
    for m in messages:
        rows.append(
            (
                m["id"],
                ticket_id,
                m.get("created_at"),
                m.get("type"),
                strip_html(m.get("body")),
                json.dumps(m, ensure_ascii=False),
            )
        )
    conn.executemany(
        """
        INSERT INTO messages (
            message_id, ticket_id, created_at,
            author_type, body_text, raw_payload
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_ticket(conn: sqlite3.Connection, ticket_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()


def get_messages(conn: sqlite3.Connection, ticket_id: int) -> list:
    return list(
        conn.execute(
            "SELECT * FROM messages WHERE ticket_id = ? ORDER BY created_at",
            (ticket_id,),
        ).fetchall()
    )

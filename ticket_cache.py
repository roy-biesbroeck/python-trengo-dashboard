"""SQLite-backed cache of Trengo tickets and messages.

Stores raw Trengo payloads verbatim alongside a few indexed columns so
downstream features can query historical data without hitting the Trengo API.
"""

import os
import sqlite3
from typing import Optional

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

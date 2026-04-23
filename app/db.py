import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings
from .guardrail import GuardrailResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    risk_level TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'input',
    matched_signals TEXT NOT NULL,
    user_message TEXT NOT NULL,
    bot_response TEXT,
    acknowledged INTEGER DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_escalations_acknowledged ON escalations(acknowledged);
CREATE INDEX IF NOT EXISTS idx_escalations_created_at ON escalations(created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_conversation_id ON conversations(conversation_id);
"""


def init_db() -> None:
    Path(settings.database_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.database_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_message(conversation_id: str, role: str, content: str, risk_level: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (conversation_id, role, content, risk_level) "
            "VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, risk_level),
        )


def recent_history(conversation_id: str, limit: int = 10) -> list[dict[str, str]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations "
            "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def conversation_messages(conversation_id: str, limit: int = 200) -> list[dict]:
    """All messages for a conversation, oldest first, with timestamps."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, risk_level, created_at FROM conversations "
            "WHERE conversation_id = ? ORDER BY id ASC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def log_escalation(
    conversation_id: str,
    result: GuardrailResult,
    user_message: str,
    bot_response: str,
    source: str = "input",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO escalations "
            "(conversation_id, risk_level, source, matched_signals, user_message, bot_response) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                result.risk.value,
                source,
                json.dumps(result.matched),
                user_message,
                bot_response,
            ),
        )
        return cur.lastrowid


def log_divergence(conversation_id: str, user_message: str, bot_response: str) -> int:
    # The model volunteered a crisis resource on a message the rule-based
    # guardrail rated NONE. That mismatch is what a human reviewer needs to see —
    # it's evidence the LLM is broadening "crisis" beyond the documented policy.
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO escalations "
            "(conversation_id, risk_level, source, matched_signals, user_message, bot_response) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                "divergence",
                "divergence",
                json.dumps(["divergence: bot mentioned crisis resource on NONE-risk message"]),
                user_message,
                bot_response,
            ),
        )
        return cur.lastrowid


def list_escalations(unack_only: bool = False, limit: int = 200) -> list[dict]:
    sql = "SELECT * FROM escalations"
    if unack_only:
        sql += " WHERE acknowledged = 0"
    sql += " ORDER BY created_at DESC LIMIT ?"
    with get_conn() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [dict(r) for r in rows]


def acknowledge_escalation(escalation_id: int, reviewer: str, notes: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE escalations SET acknowledged = 1, acknowledged_by = ?, "
            "acknowledged_at = CURRENT_TIMESTAMP, notes = ? WHERE id = ?",
            (reviewer, notes, escalation_id),
        )

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

CREATE TABLE IF NOT EXISTS conversation_state (
    conversation_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'bot',
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_escalations_acknowledged ON escalations(acknowledged);
CREATE INDEX IF NOT EXISTS idx_escalations_created_at ON escalations(created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_conversation_id ON conversations(conversation_id);
"""

REVIEWER_RISK_LABEL = "human-reviewer"
PAUSED_NOTICE = (
    "Your message was received. A human reviewer is engaged in this conversation "
    "and will respond shortly. The automated bot has been paused for now."
)


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
            "SELECT id, role, content, risk_level, created_at FROM conversations "
            "WHERE conversation_id = ? ORDER BY id ASC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def conversation_previews(conversation_ids: list[str]) -> list[dict]:
    """Return summary info for the given conversation IDs.

    Result preserves the input order for UI stability and skips IDs the server
    has never seen (e.g., a freshly-created cid that has no messages yet).
    """
    if not conversation_ids:
        return []
    placeholders = ",".join("?" for _ in conversation_ids)
    sql = f"""
        SELECT
            conversation_id,
            COUNT(*) AS message_count,
            MAX(created_at) AS last_message_at,
            (SELECT content FROM conversations c2
                WHERE c2.conversation_id = c1.conversation_id
                ORDER BY id DESC LIMIT 1) AS last_message,
            (SELECT role FROM conversations c2
                WHERE c2.conversation_id = c1.conversation_id
                ORDER BY id DESC LIMIT 1) AS last_role,
            MAX(CASE WHEN risk_level IN ('low','medium','high')
                THEN risk_level END) AS highest_risk
        FROM conversations c1
        WHERE conversation_id IN ({placeholders})
        GROUP BY conversation_id
    """
    with get_conn() as conn:
        rows = conn.execute(sql, conversation_ids).fetchall()
    by_id = {r["conversation_id"]: dict(r) for r in rows}
    out: list[dict] = []
    for cid in conversation_ids:
        r = by_id.get(cid)
        if not r:
            continue
        preview = (r["last_message"] or "").strip().replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:77] + "…"
        out.append({
            "conversation_id": cid,
            "message_count": r["message_count"],
            "last_message_at": r["last_message_at"],
            "last_role": r["last_role"],
            "preview": preview,
            "highest_risk": r["highest_risk"],
        })
    return out


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
    sql = (
        "SELECT e.*, COALESCE(s.state, 'bot') AS conversation_state "
        "FROM escalations e "
        "LEFT JOIN conversation_state s ON s.conversation_id = e.conversation_id"
    )
    if unack_only:
        sql += " WHERE e.acknowledged = 0"
    sql += " ORDER BY e.created_at DESC LIMIT ?"
    with get_conn() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_conversation_state(conversation_id: str) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT state FROM conversation_state WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
    return row["state"] if row else "bot"


def set_conversation_state(conversation_id: str, state: str, changed_by: str) -> None:
    if state not in ("bot", "human"):
        raise ValueError(f"invalid state: {state}")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversation_state (conversation_id, state, changed_at, changed_by) "
            "VALUES (?, ?, CURRENT_TIMESTAMP, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET "
            "state = excluded.state, changed_at = CURRENT_TIMESTAMP, changed_by = excluded.changed_by",
            (conversation_id, state, changed_by),
        )


def save_reviewer_message(conversation_id: str, content: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (conversation_id, role, content, risk_level) "
            "VALUES (?, 'assistant', ?, ?)",
            (conversation_id, content, REVIEWER_RISK_LABEL),
        )
        return cur.lastrowid


def acknowledge_escalation(escalation_id: int, reviewer: str, notes: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE escalations SET acknowledged = 1, acknowledged_by = ?, "
            "acknowledged_at = CURRENT_TIMESTAMP, notes = ? WHERE id = ?",
            (reviewer, notes, escalation_id),
        )

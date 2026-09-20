"""
Persistent chat history (SQLite, standard library only).

    chat_sessions  (id, user_id, document_id, title, summary, summarized_upto, created_at, updated_at)
    chat_messages  (id, session_id -> chat_sessions, role, content, created_at)
    message_sources(id, message_id -> chat_messages, source_document, source_chunk_ids)

`user_id` is the client session id (this app has no separate accounts). A chat session is always
looked up by (user_id, document_id) - a client can never address a chat session id directly, so one
learner's history cannot be read through another learner's requests. Deterministic Python only.
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence

from backend import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    summarized_upto INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_doc ON chat_sessions(user_id, document_id, updated_at);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);

CREATE TABLE IF NOT EXISTS message_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    source_document TEXT NOT NULL,
    source_chunk_ids TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_message_sources_message ON message_sources(message_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChatHistoryService:
    def __init__(self, path):
        self._path = str(path)
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- sessions ---------------------------------------------------------
    def find_session(self, user_id: str, document_id: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM chat_sessions WHERE user_id=? AND document_id=? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
                (user_id, document_id),
            ).fetchone()
        return row["id"] if row else None

    def get_or_create_session(self, user_id: str, document_id: str) -> str:
        existing = self.find_session(user_id, document_id)
        if existing:
            return existing
        session_id, now = uuid.uuid4().hex, _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO chat_sessions (id, user_id, document_id, title, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (session_id, user_id, document_id, "", now, now),
            )
        return session_id

    def summary(self, chat_session_id: Optional[str]) -> str:
        if not chat_session_id:
            return ""
        with self._conn() as conn:
            row = conn.execute("SELECT summary FROM chat_sessions WHERE id=?", (chat_session_id,)).fetchone()
        return row["summary"] if row else ""

    def title(self, chat_session_id: str) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT title FROM chat_sessions WHERE id=?", (chat_session_id,)).fetchone()
        return row["title"] if row else ""

    # ---- messages ---------------------------------------------------------
    def add_exchange(
        self,
        chat_session_id: str,
        user_content: str,
        assistant_content: str,
        source_document: Optional[str] = None,
        chunk_ids: Optional[Sequence[int]] = None,
    ) -> Dict[str, int]:
        """Stores the user message and the assistant reply (and its sources) in ONE transaction."""
        now = _now()
        limit = config.MAX_STORED_MESSAGE_CHARS
        with self._conn() as conn:
            u = conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                (chat_session_id, "user", user_content[:limit], now),
            ).lastrowid
            a = conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                (chat_session_id, "assistant", assistant_content[:limit], now),
            ).lastrowid
            if source_document and chunk_ids:
                conn.execute(
                    "INSERT INTO message_sources (message_id, source_document, source_chunk_ids) VALUES (?,?,?)",
                    (a, source_document, json.dumps([int(i) for i in chunk_ids])),
                )
            conn.execute(
                "UPDATE chat_sessions SET updated_at=?, title=CASE WHEN title='' THEN ? ELSE title END WHERE id=?",
                (now, " ".join(user_content.split())[:60], chat_session_id),
            )
        return {"user_message_id": u, "assistant_message_id": a}

    def recent_messages(self, chat_session_id: Optional[str], limit: int = config.CHAT_RECENT_MESSAGES) -> List[Dict[str, str]]:
        """The last `limit` messages, oldest first - the only history that is ever sent to the model."""
        if not chat_session_id:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM chat_messages WHERE session_id=? AND role IN ('user','assistant') ORDER BY id DESC LIMIT ?",
                (chat_session_id, limit),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def list_messages(self, chat_session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM (SELECT * FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT ?) ORDER BY id",
                (chat_session_id, limit),
            ).fetchall()
            out = []
            for r in rows:
                sources = conn.execute("SELECT source_document, source_chunk_ids FROM message_sources WHERE message_id=?", (r["id"],)).fetchall()
                out.append(
                    {
                        "id": r["id"],
                        "role": r["role"],
                        "content": r["content"],
                        "created_at": r["created_at"],
                        "sources": [{"source_document": s["source_document"], "chunk_ids": json.loads(s["source_chunk_ids"])} for s in sources],
                    }
                )
        return out

    # ---- rolling summary --------------------------------------------------
    def messages_needing_summary(self, chat_session_id: str, keep_recent: int = config.CHAT_RECENT_MESSAGES) -> List[Dict[str, Any]]:
        """Older messages (outside the recent window) that are not yet folded into the summary."""
        with self._conn() as conn:
            upto = conn.execute("SELECT summarized_upto FROM chat_sessions WHERE id=?", (chat_session_id,)).fetchone()
            if upto is None:
                return []
            rows = conn.execute(
                """SELECT id, role, content FROM chat_messages
                   WHERE session_id=? AND id > ? AND role IN ('user','assistant')
                     AND id NOT IN (SELECT id FROM chat_messages WHERE session_id=? ORDER BY id DESC LIMIT ?)
                   ORDER BY id""",
                (chat_session_id, upto["summarized_upto"], chat_session_id, keep_recent),
            ).fetchall()
        return [{"id": r["id"], "role": r["role"], "content": r["content"]} for r in rows]

    def update_summary(self, chat_session_id: str, summary: str, upto_message_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE chat_sessions SET summary=?, summarized_upto=? WHERE id=?",
                (summary[: config.SUMMARY_MAX_CHARS], upto_message_id, chat_session_id),
            )

    # ---- deletion -----------------------------------------------------------
    def delete_for_document(self, user_id: str, document_id: str) -> int:
        with self._conn() as conn:
            return conn.execute("DELETE FROM chat_sessions WHERE user_id=? AND document_id=?", (user_id, document_id)).rowcount

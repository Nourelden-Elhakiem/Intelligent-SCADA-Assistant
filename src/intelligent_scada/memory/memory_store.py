"""Persistent document-scoped transcripts; starting a new session does not erase old ones."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from intelligent_scada.config import validate_document_key
from intelligent_scada.database.connection import transaction


def _session_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("session_id must be a valid UUID") from exc


class MemoryStore:
    def __init__(self, conn_str: str | None) -> None:
        self.conn_str = conn_str

    def create_or_load_session(
        self,
        document_key: str,
        session_id: str | None = None,
        *,
        memory_enabled: bool = True,
    ) -> str:
        validate_document_key(document_key)
        resolved_id = _session_id(session_id) if session_id is not None else str(uuid.uuid4())
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM documents WHERE document_key = %s",
                (document_key,),
            )
            document = cursor.fetchone()
            if document is None:
                raise LookupError(f"Document is not indexed: {document_key}")
            cursor.execute(
                """
                    INSERT INTO chat_sessions (
                        session_id, document_id, memory_enabled
                    ) VALUES (%s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        memory_enabled = EXCLUDED.memory_enabled,
                        updated_at = NOW()
                    WHERE chat_sessions.document_id = EXCLUDED.document_id
                    RETURNING session_id
                    """,
                (resolved_id, int(document[0]), memory_enabled),
            )
            if cursor.fetchone() is None:
                raise ValueError("A session ID cannot be reused with a different document")
        return resolved_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        useful: bool,
        citations: Sequence[Mapping[str, Any]] | None = None,
    ) -> int:
        session_id = _session_id(session_id)
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    INSERT INTO chat_messages (
                        session_id, role, content, is_context_useful, citations
                    ) VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                (session_id, role, content, useful, json.dumps(citations or [])),
            )
            if useful:
                cursor.execute(
                    """
                        UPDATE chat_sessions
                        SET useful_message_count = useful_message_count + 1,
                            updated_at = NOW()
                        WHERE session_id = %s
                        RETURNING useful_message_count
                        """,
                    (session_id,),
                )
                return int(cursor.fetchone()[0])
        return self.useful_message_count(session_id)

    def context(self, session_id: str, *, limit: int = 8) -> dict[str, Any]:
        session_id = _session_id(session_id)
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT summary, memory_enabled, useful_message_count
                    FROM chat_sessions WHERE session_id = %s
                    """,
                (session_id,),
            )
            session = cursor.fetchone()
            if session is None:
                raise LookupError(f"Unknown session: {session_id}")
            cursor.execute(
                """
                    SELECT role, content
                    FROM chat_messages
                    WHERE session_id = %s AND is_context_useful = TRUE
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                (session_id, limit),
            )
            messages = [
                {"role": row[0], "content": row[1]} for row in reversed(cursor.fetchall())
            ]
        return {
            "summary": session[0] or "",
            "memory_enabled": bool(session[1]),
            "useful_message_count": int(session[2]),
            "messages": messages,
        }

    def useful_message_count(self, session_id: str) -> int:
        session_id = _session_id(session_id)
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT useful_message_count FROM chat_sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cursor.fetchone()
        return int(row[0]) if row else 0

    def update_summary(self, session_id: str, summary: str) -> None:
        session_id = _session_id(session_id)
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    UPDATE chat_sessions
                    SET summary = %s, updated_at = NOW()
                    WHERE session_id = %s
                    """,
                (summary, session_id),
            )

    def messages(self, session_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return a session transcript in chronological order."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        session_id = _session_id(session_id)
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT role, content, citations, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                """,
                (session_id, limit),
            )
            rows = list(reversed(cursor.fetchall()))
        if not rows:
            raise LookupError(f"Unknown or empty session: {session_id}")
        return [
            {
                "role": row[0],
                "content": row[1],
                "citations": row[2] if isinstance(row[2], list) else json.loads(row[2]),
                "created_at": row[3],
            }
            for row in rows
        ]

import sqlite3
from pathlib import Path
from typing import Optional


class StateStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS thread_state (
                    thread_id TEXT PRIMARY KEY,
                    last_response_id TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY,
                    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letters (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    from_email TEXT,
                    subject TEXT,
                    error TEXT,
                    attempts INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'dead_letter',
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbound_replies (
                    message_id TEXT PRIMARY KEY,
                    sent_message_id TEXT,
                    status TEXT DEFAULT 'sent',
                    source TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get_last_response_id(self, thread_id: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT last_response_id FROM thread_state WHERE thread_id = ?", (thread_id,)
            ).fetchone()
            return row[0] if row else None

    def set_last_response_id(self, thread_id: str, response_id: str):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO thread_state (thread_id, last_response_id)
                VALUES (?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                  last_response_id = excluded.last_response_id,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (thread_id, response_id),
            )

    def is_processed(self, message_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)
            ).fetchone()
            return row is not None

    def mark_processed(self, message_id: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_messages (message_id) VALUES (?)", (message_id,)
            )

    def unmark_processed(self, message_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM processed_messages WHERE message_id = ?", (message_id,))

    def mark_reply_sent(self, message_id: str, sent_message_id: str | None = None, source: str = "api_send"):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO outbound_replies (message_id, sent_message_id, status, source)
                VALUES (?, ?, 'sent', ?)
                ON CONFLICT(message_id) DO UPDATE SET
                  sent_message_id = COALESCE(excluded.sent_message_id, outbound_replies.sent_message_id),
                  status = 'sent',
                  source = excluded.source,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (message_id, sent_message_id, source),
            )

    def has_reply_been_sent(self, message_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM outbound_replies WHERE message_id = ? AND status = 'sent'", (message_id,)
            ).fetchone()
            return row is not None

    def upsert_dead_letter(
        self,
        message_id: str,
        error: str,
        attempts: int,
        thread_id: str | None = None,
        from_email: str | None = None,
        subject: str | None = None,
        status: str = "dead_letter",
    ):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO dead_letters (
                    message_id, thread_id, from_email, subject, error, attempts, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                  thread_id = COALESCE(excluded.thread_id, dead_letters.thread_id),
                  from_email = COALESCE(excluded.from_email, dead_letters.from_email),
                  subject = COALESCE(excluded.subject, dead_letters.subject),
                  error = excluded.error,
                  attempts = excluded.attempts,
                  status = excluded.status,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (message_id, thread_id, from_email, subject, error[:4000], attempts, status),
            )

    def list_dead_letters(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT message_id, thread_id, from_email, subject, error, attempts, status, updated_at
                FROM dead_letters
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "message_id": row[0],
                "thread_id": row[1],
                "from_email": row[2],
                "subject": row[3],
                "error": row[4],
                "attempts": row[5],
                "status": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def list_requeued_message_ids(self, limit: int = 20) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT message_id
                FROM dead_letters
                WHERE status = 'requeued'
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row[0] for row in rows]

    def mark_dead_letter_requeued(self, message_id: str):
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE dead_letters
                SET status = 'requeued', updated_at = CURRENT_TIMESTAMP
                WHERE message_id = ?
                """,
                (message_id,),
            )

    def clear_dead_letter(self, message_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM dead_letters WHERE message_id = ?", (message_id,))

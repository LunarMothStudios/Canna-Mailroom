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

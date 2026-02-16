from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class MemoryEvent:
    ts: float
    role: str  # "user" | "agent" | "tool" | "llm"
    content: str
    meta: Dict[str, Any]


class MemoryStore:
    def __init__(self, db_path: str = "memory.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    session_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    meta_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events(session_id, ts)"
            )

    def add_event(
        self,
        session_id: str,
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        meta = meta or {}
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events(session_id, ts, role, content, meta_json) VALUES (?, ?, ?, ?, ?)",
                (session_id, time.time(), role, content, json.dumps(meta)),
            )

    def get_recent(self, session_id: str, limit: int = 50) -> List[MemoryEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT ts, role, content, meta_json
                FROM events
                WHERE session_id = ?
                ORDER BY ts DESC
                LIMIT ?
                """
                ,
                (session_id, limit),
            ).fetchall()

        events: List[MemoryEvent] = []
        for ts, role, content, meta_json in reversed(rows):
            events.append(
                MemoryEvent(ts=ts, role=role, content=content, meta=json.loads(meta_json))
            )
        return events

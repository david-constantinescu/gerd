"""SQLite logger.

WAL mode + 30 s batched writes. Schema:

- ``sessions``  power-on / off, wear-side, calibration baselines
- ``events``    meals, symptoms, food photos, med acknowledgments
- ``posture_log`` sparse pitch/roll snapshots (only on state-significant changes)
- ``sleep_log`` per-night summary
- ``inbox``     "messages from the webapp to the firmware" — the webapp INSERTs
                requests here, the FSM polls them once per loop tick. Avoids
                sharing Python objects across processes.
- ``foods``     editable food risk dictionary (mirror of foods.json on disk)
- ``medications`` user-configured med reminders
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from typing import Any

from ..config import DB_PATH

log = logging.getLogger("services.logger")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    wear_side TEXT,
    pitch_baseline REAL,
    roll_baseline REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);
CREATE TABLE IF NOT EXISTS posture_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    pitch REAL, roll REAL, state TEXT
);
CREATE INDEX IF NOT EXISTS idx_posture_ts ON posture_log(ts DESC);
CREATE TABLE IF NOT EXISTS sleep_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    night_of TEXT NOT NULL,
    duration_s INTEGER, left_pct REAL, right_pct REAL,
    back_pct REAL, front_pct REAL, score INTEGER, nudges INTEGER,
    payload TEXT
);
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT,
    consumed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dose TEXT,
    time TEXT NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'daily',
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS foods (
    name TEXT PRIMARY KEY,
    risk TEXT NOT NULL,
    upright_hours REAL NOT NULL
);
"""


class Logger:
    def __init__(self, path: str | None = None) -> None:
        self.path = str(path or DB_PATH)
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._buffer: list[tuple[str, tuple[Any, ...]]] = []
        self._last_flush = time.time()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(SCHEMA)
        self._session_id: int | None = None

    # ---- writes ----

    def _enqueue(self, sql: str, params: tuple[Any, ...]) -> None:
        with self._lock:
            self._buffer.append((sql, params))
        if time.time() - self._last_flush > 30.0:
            self.flush()

    def boot_session(self, wear_side: str = "left") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions(started_at, wear_side) VALUES (?, ?)",
                (time.time(), wear_side),
            )
            self._session_id = cur.lastrowid
        return self._session_id  # type: ignore[return-value]

    def end_session(self) -> None:
        if self._session_id is None:
            return
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (time.time(), self._session_id),
            )

    def event(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        self._enqueue(
            "INSERT INTO events(ts, kind, payload) VALUES (?, ?, ?)",
            (time.time(), kind, json.dumps(payload or {})),
        )

    def posture(self, pitch: float, roll: float, state: str) -> None:
        self._enqueue(
            "INSERT INTO posture_log(ts, pitch, roll, state) VALUES (?, ?, ?, ?)",
            (time.time(), pitch, roll, state),
        )

    def sleep_summary(self, **kw: Any) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO sleep_log
                   (night_of, duration_s, left_pct, right_pct, back_pct, front_pct,
                    score, nudges, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    kw.get("night_of"),
                    kw.get("duration_s"),
                    kw.get("left_pct"),
                    kw.get("right_pct"),
                    kw.get("back_pct"),
                    kw.get("front_pct"),
                    kw.get("score"),
                    kw.get("nudges"),
                    json.dumps(kw.get("payload", {})),
                ),
            )

    def flush(self) -> None:
        with self._lock:
            if not self._buffer:
                self._last_flush = time.time()
                return
            try:
                self._conn.execute("BEGIN")
                for sql, params in self._buffer:
                    self._conn.execute(sql, params)
                self._conn.execute("COMMIT")
            except sqlite3.Error as e:
                log.error("flush failed: %s", e)
                self._conn.execute("ROLLBACK")
            self._buffer.clear()
            self._last_flush = time.time()

    # ---- reads ----

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, kind, payload FROM events ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"ts": r[0], "kind": r[1], "payload": json.loads(r[2] or "{}")}
            for r in rows
        ]

    def last_meal(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT ts, payload FROM events WHERE kind='meal' ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {"ts": row[0], **json.loads(row[1] or "{}")}

    def consume_inbox(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ts, kind, payload FROM inbox WHERE consumed=0 ORDER BY id"
            ).fetchall()
            if rows:
                placeholders = ",".join("?" * len(rows))
                self._conn.execute(
                    f"UPDATE inbox SET consumed=1 WHERE id IN ({placeholders})",
                    tuple(r[0] for r in rows),
                )
        return [
            {"id": r[0], "ts": r[1], "kind": r[2], "payload": json.loads(r[3] or "{}")}
            for r in rows
        ]

    def push_inbox(self, kind: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO inbox(ts, kind, payload) VALUES (?, ?, ?)",
                (time.time(), kind, json.dumps(payload)),
            )

    def close(self) -> None:
        self.flush()
        self.end_session()
        with self._lock:
            self._conn.close()

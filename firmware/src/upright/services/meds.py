"""Medication reminders.

Reminders are stored in the SQLite ``medications`` table (CRUD via the
webapp). The FSM polls :meth:`MedReminders.tick` every loop iteration; due
reminders fire as ``MED_REMINDER`` events. If the user doesn't acknowledge
within 5 minutes the reminder fires again.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from ..events import Event, EventBus, EventType
from .logger import Logger

log = logging.getLogger("services.meds")

REPEAT_AFTER = timedelta(minutes=5)


class MedReminders:
    def __init__(self, bus: EventBus, db: Logger) -> None:
        self.bus = bus
        self.db = db
        # name -> next-fire datetime
        self._next: dict[str, datetime] = {}
        self._pending: dict[str, datetime] = {}
        self._refresh_schedule()

    def _refresh_schedule(self) -> None:
        with self.db._lock:  # noqa: SLF001 — internal helper
            rows = self.db._conn.execute(
                "SELECT id, name, time FROM medications WHERE enabled=1"
            ).fetchall()
        today = datetime.now().date()
        for _id, name, t in rows:
            try:
                hh, mm = (int(x) for x in t.split(":"))
            except ValueError:
                continue
            self._next[name] = datetime.combine(today, datetime.min.time()).replace(
                hour=hh, minute=mm
            )

    def tick(self) -> None:
        now = datetime.now()
        for name, when in list(self._next.items()):
            if now >= when:
                self._fire(name)
                self._next[name] = when + timedelta(days=1)
        for name, when in list(self._pending.items()):
            if now - when >= REPEAT_AFTER:
                self._fire(name)
                self._pending[name] = now

    def _fire(self, name: str) -> None:
        log.info("med reminder: %s", name)
        self._pending[name] = datetime.now()
        self.bus.publish(Event(EventType.MED_REMINDER, payload={"name": name}))

    def acknowledge(self, name: str) -> None:
        self._pending.pop(name, None)
        self.db.event("med_acknowledged", {"name": name, "ts": time.time()})

    def status_line(self) -> str:
        """One-line med summary for the watch face."""
        if self._pending:
            name = next(iter(self._pending))
            return f"Med due: {name[:14]}"
        now = datetime.now()
        future = [(when, name) for name, when in self._next.items() if when > now]
        if not future:
            return ""
        when, name = min(future, key=lambda x: x[0])
        return f"Next med {when.strftime('%H:%M')} {name[:10]}"

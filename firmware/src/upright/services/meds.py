"""Medication reminders.

Reminders are stored in the SQLite ``medications`` table (CRUD via the
webapp). The FSM polls :meth:`MedReminders.tick` every loop iteration; due
reminders fire as ``MED_REMINDER`` events. If the user doesn't acknowledge
within 5 minutes the reminder fires again.

In demo mode, a single reminder fires once, relative to demo session boot time
(see ``demo_week.json`` ``demo_reminders`` — default 30s after boot).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from ..events import Event, EventBus, EventType
from . import demo_seed
from .logger import Logger

log = logging.getLogger("services.meds")

REPEAT_AFTER = timedelta(minutes=5)


class MedReminders:
    def __init__(self, bus: EventBus, db: Logger) -> None:
        self.bus = bus
        self.db = db
        self._next: dict[str, datetime] = {}
        self._pending: dict[str, datetime] = {}
        self._demo_fired: set[str] = set()
        self._refresh_schedule()

    def _refresh_schedule(self) -> None:
        self._next.clear()
        if demo_seed.is_demo_mode():
            self._apply_demo_schedule()
            return
        self._demo_fired.clear()
        with self.db._lock:  # noqa: SLF001
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

    @staticmethod
    def _demo_offset_seconds(item: dict) -> float:
        if "seconds_after_boot" in item:
            return float(item["seconds_after_boot"])
        return float(item.get("minutes_after_boot", 0.5)) * 60.0

    def _apply_demo_schedule(self) -> None:
        start = demo_seed.get_demo_session_start() or time.time()
        base = datetime.fromtimestamp(start)
        self._next.clear()
        self._pending.clear()
        plan = demo_seed.demo_reminder_plan()
        # Showroom: one med popup per boot (first plan entry only).
        for item in plan[:1]:
            name = str(item.get("name", ""))
            if not name:
                continue
            offset_s = self._demo_offset_seconds(item)
            self._next[name] = base + timedelta(seconds=offset_s)
        self._demo_fired.clear()
        if self._next:
            name, when = next(iter(self._next.items()))
            log.info(
                "demo med reminder once @ +%.0fs (%s at %s)",
                (when - base).total_seconds(),
                name,
                when.strftime("%H:%M:%S"),
            )

    def _lookup_med(self, name: str) -> tuple[str, str, str]:
        with self.db._lock:  # noqa: SLF001
            row = self.db._conn.execute(
                "SELECT name, dose FROM medications WHERE name=?", (name,)
            ).fetchone()
        if row:
            details = demo_seed.demo_med_details(name) if demo_seed.is_demo_mode() else {}
            brand = details.get("brand", row[0])
            return row[0], brand, row[1] or ""
        return name, name, ""

    def tick(self) -> None:
        now = datetime.now()
        if demo_seed.is_demo_mode():
            for name, when in list(self._next.items()):
                if name in self._demo_fired:
                    continue
                if now >= when:
                    self._fire(name)
                    self._demo_fired.add(name)
            return

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
        med_name, brand, dose = self._lookup_med(name)
        payload = {
            "name": med_name,
            "brand": brand,
            "dose": dose,
            "demo": demo_seed.is_demo_mode(),
        }
        self.bus.publish(Event(EventType.MED_REMINDER, payload=payload))

    def acknowledge(self, name: str) -> None:
        self._pending.pop(name, None)
        self.db.event_now("med_acknowledged", {"name": name, "ts": time.time()})

    def dismiss(self, name: str) -> None:
        """Close reminder without logging taken."""
        self._pending.pop(name, None)

    def pending_names(self) -> list[str]:
        return list(self._pending.keys())

    def status_line(self) -> str:
        if self._pending:
            name = next(iter(self._pending))
            if demo_seed.is_demo_mode():
                _n, brand, dose = self._lookup_med(name)
                line = f"Med: {brand}"
                if dose:
                    line += f" {dose}"
                return line[:24]
            return f"Med due: {name[:14]}"
        now = datetime.now()
        future = [(when, name) for name, when in self._next.items() if when > now]
        if not future:
            return ""
        when, name = min(future, key=lambda x: x[0])
        return f"Next med {when.strftime('%H:%M')} {name[:10]}"

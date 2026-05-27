"""Pimoroni Zero LiPo low-battery alert on GPIO 4 (active low)."""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_LIPO_ALERT
from ..events import Event, EventBus, EventType
from .gpio_lgpio import claim_input, read_active_low

log = logging.getLogger("hal.power")

_PCT_OK = 100
_PCT_LOW = 18


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:
    claim_input(PIN_LIPO_ALERT)
    low_since: float | None = None
    while not stop.is_set():
        low = read_active_low(PIN_LIPO_ALERT)
        now = time.time()
        if low:
            if low_since is None:
                low_since = now
        else:
            low_since = None
        low_battery = low_since is not None and (now - low_since) > 1.5
        pct = _PCT_LOW if low_battery else _PCT_OK
        evt_bus.publish(
            Event(
                EventType.POWER_SAMPLE,
                payload={
                    "battery_pct": pct,
                    "battery_low": low_battery,
                    "battery_ok": not low_battery,
                },
            )
        )
        stop.wait(5.0)


def _stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    while not stop.is_set():
        evt_bus.publish(
            Event(
                EventType.POWER_SAMPLE,
                payload={"battery_pct": 100, "battery_low": False, "battery_ok": True},
            )
        )
        stop.wait(30.0)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
        log.info("starting power stub thread")
    else:
        try:
            claim_input(PIN_LIPO_ALERT)
            target = lambda: _loop(evt_bus, stop)  # noqa: E731
            log.info("starting Zero LiPo monitor on GPIO %s", PIN_LIPO_ALERT)
        except Exception as e:
            log.error("could not read LiPo alert pin (%s) — using stub", e)
            target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.power", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    return th

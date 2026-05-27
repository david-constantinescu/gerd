"""Coin vibration motor on GPIO 22 / physical pin 15 (via driver transistor)."""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_MOTOR
from .gpio_lgpio import claim_output, write

log = logging.getLogger("hal.motor")

# GPIO is on/off only — longer bursts + more repeats = stronger perceived haptic.
PATTERNS: dict[str, list[float]] = {
    "gentle": [0.30, 0.12, 0.30, 0.0],
    "moderate": [0.45, 0.15, 0.45, 0.15, 0.45, 0.0],
    "strong": [0.65, 0.18, 0.65, 0.18, 0.65, 0.18, 0.65, 0.0],
    "max": [
        0.95,
        0.18,
        0.95,
        0.18,
        0.95,
        0.18,
        0.95,
        0.18,
        0.95,
        0.0,
    ],
}


class Motor:
    def __init__(self, *, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._ready = False
        if not dry_run:
            try:
                claim_output(PIN_MOTOR, initial=0)
                self._ready = True
            except Exception as e:
                log.error("motor init failed (%s) — running in stub mode", e)

    def buzz(self, pattern: str = "gentle") -> None:
        seq = PATTERNS.get(pattern, PATTERNS["gentle"])
        log.info("buzz: %s", pattern)
        if not self._ready:
            return
        for i, dur in enumerate(seq):
            write(PIN_MOTOR, 1 if i % 2 == 0 else 0)
            time.sleep(dur)
        write(PIN_MOTOR, 0)

    def buzz_async(self, pattern: str = "gentle") -> None:
        threading.Thread(target=self.buzz, args=(pattern,), daemon=True).start()

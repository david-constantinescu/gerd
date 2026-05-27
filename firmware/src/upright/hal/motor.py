"""Coin vibration motor on GPIO 5 (via 2N2222 + 1N4001)."""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_MOTOR
from .gpio_lgpio import claim_output, write

log = logging.getLogger("hal.motor")

PATTERNS: dict[str, list[float]] = {
    "gentle": [0.10, 0.0],
    "moderate": [0.10, 0.10, 0.10, 0.0],
    "strong": [0.20, 0.10, 0.20, 0.10, 0.20, 0.0],
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

"""Coin vibration motor on GPIO 5 (via 2N2222 + 1N4001)."""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_MOTOR

log = logging.getLogger("hal.motor")

PATTERNS: dict[str, list[float]] = {
    # on, off, on, off, ...  (seconds)
    "gentle": [0.10, 0.0],
    "moderate": [0.10, 0.10, 0.10, 0.0],
    "strong": [0.20, 0.10, 0.20, 0.10, 0.20, 0.0],
}


class Motor:
    def __init__(self, *, dry_run: bool = False) -> None:
        self._gpio = None
        self._dry_run = dry_run
        if not dry_run:
            try:
                import RPi.GPIO as GPIO  # type: ignore[import-not-found]

                GPIO.setmode(GPIO.BCM)
                GPIO.setup(PIN_MOTOR, GPIO.OUT)
                GPIO.output(PIN_MOTOR, 0)
                self._gpio = GPIO
            except Exception as e:
                log.error("motor init failed (%s) — running in stub mode", e)

    def buzz(self, pattern: str = "gentle") -> None:
        seq = PATTERNS.get(pattern, PATTERNS["gentle"])
        log.info("buzz: %s", pattern)
        if self._gpio is None:
            return
        for i, dur in enumerate(seq):
            self._gpio.output(PIN_MOTOR, 1 if i % 2 == 0 else 0)
            time.sleep(dur)
        self._gpio.output(PIN_MOTOR, 0)

    def buzz_async(self, pattern: str = "gentle") -> None:
        threading.Thread(target=self.buzz, args=(pattern,), daemon=True).start()

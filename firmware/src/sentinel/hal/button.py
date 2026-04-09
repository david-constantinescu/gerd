"""Tactile button on GPIO 4. Recognises 5 press patterns:

- single press   (<400 ms)             → mild symptom
- double press   (2x within 500 ms)    → moderate symptom
- triple press                          → severe symptom
- long press     (1.5–3 s)              → log meal
- very long press (≥3 s)               → enter calibration mode
"""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_BUTTON
from ..events import Event, EventBus, EventType

log = logging.getLogger("hal.button")

_DOUBLE_GAP = 0.5  # seconds between presses to count as multi-press
_LONG_THRESHOLD = 1.5
_VERYLONG_THRESHOLD = 3.0


def classify(presses: list[float], hold_duration: float) -> str:
    """Pure function — easy to unit-test."""
    if hold_duration >= _VERYLONG_THRESHOLD:
        return "verylong"
    if hold_duration >= _LONG_THRESHOLD:
        return "long"
    n = len(presses)
    if n >= 3:
        return "triple"
    if n == 2:
        return "double"
    return "single"


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:  # pragma: no cover - hardware
    import RPi.GPIO as GPIO  # type: ignore[import-not-found]

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    presses: list[float] = []
    pressed_at: float | None = None

    while not stop.is_set():
        is_down = GPIO.input(PIN_BUTTON) == 0
        now = time.time()
        if is_down and pressed_at is None:
            pressed_at = now
        elif not is_down and pressed_at is not None:
            hold = now - pressed_at
            pressed_at = None
            if hold >= _LONG_THRESHOLD:
                pattern = classify([], hold)
                evt_bus.publish(Event(EventType.BUTTON_PRESS, payload={"pattern": pattern}))
                presses.clear()
            else:
                presses.append(now)
        if presses and (now - presses[-1]) > _DOUBLE_GAP and pressed_at is None:
            pattern = classify(presses, 0)
            evt_bus.publish(Event(EventType.BUTTON_PRESS, payload={"pattern": pattern}))
            presses.clear()
        time.sleep(0.02)


def _stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    while not stop.is_set():
        stop.wait(60.0)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    target = (
        (lambda: _stub_loop(evt_bus, stop))
        if dry_run
        else (lambda: _loop(evt_bus, stop))
    )
    th = threading.Thread(target=target, name="hal.button", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    log.info("button thread started (dry_run=%s)", dry_run)
    return th

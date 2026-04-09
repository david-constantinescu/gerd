"""EC11 rotary encoder. Hardware debounce via 10 nF caps on CLK/DT is mandatory."""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_ENCODER_CLK, PIN_ENCODER_DT, PIN_ENCODER_SW
from ..events import Event, EventBus, EventType

log = logging.getLogger("hal.encoder")


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:  # pragma: no cover - hardware
    import RPi.GPIO as GPIO  # type: ignore[import-not-found]

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN_ENCODER_CLK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_ENCODER_DT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_ENCODER_SW, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    last_clk = GPIO.input(PIN_ENCODER_CLK)
    last_sw = 1
    while not stop.is_set():
        clk = GPIO.input(PIN_ENCODER_CLK)
        dt = GPIO.input(PIN_ENCODER_DT)
        if clk != last_clk and clk == 0:
            direction = "cw" if dt != clk else "ccw"
            evt_bus.publish(Event(EventType.ENCODER_ROTATE, payload={"dir": direction}))
        last_clk = clk
        sw = GPIO.input(PIN_ENCODER_SW)
        if last_sw == 1 and sw == 0:
            evt_bus.publish(Event(EventType.ENCODER_CLICK))
        last_sw = sw
        time.sleep(0.001)


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
    th = threading.Thread(target=target, name="hal.encoder", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    log.info("encoder thread started (dry_run=%s)", dry_run)
    return th

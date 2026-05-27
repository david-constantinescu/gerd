"""EC11 rotary encoder via lgpio (same stack as buttons; avoids RPi.GPIO vs SPI)."""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_ENCODER_CLK, PIN_ENCODER_DT, PIN_ENCODER_SW
from ..events import Event, EventBus, EventType
from .gpio_lgpio import claim_input, read_gpio

log = logging.getLogger("hal.encoder")

_ROTATE_DEBOUNCE_S = 0.04


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:  # pragma: no cover
    for pin in (PIN_ENCODER_CLK, PIN_ENCODER_DT, PIN_ENCODER_SW):
        claim_input(pin)

    last_clk = read_gpio(PIN_ENCODER_CLK)
    last_sw = read_gpio(PIN_ENCODER_SW)
    last_rotate = 0.0

    log.info(
        "encoder on GPIO CLK=%s DT=%s SW=%s",
        PIN_ENCODER_CLK,
        PIN_ENCODER_DT,
        PIN_ENCODER_SW,
    )

    while not stop.is_set():
        clk = read_gpio(PIN_ENCODER_CLK)
        dt = read_gpio(PIN_ENCODER_DT)
        if clk != last_clk:
            now = time.time()
            if now - last_rotate >= _ROTATE_DEBOUNCE_S:
                direction = "cw" if dt != clk else "ccw"
                evt_bus.publish(Event(EventType.ENCODER_ROTATE, payload={"dir": direction}))
                last_rotate = now
            last_clk = clk

        sw = read_gpio(PIN_ENCODER_SW)
        if last_sw == 1 and sw == 0:
            evt_bus.publish(Event(EventType.ENCODER_CLICK))
        last_sw = sw
        time.sleep(0.002)


def _stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    while not stop.is_set():
        stop.wait(60.0)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    else:
        try:
            for pin in (PIN_ENCODER_CLK, PIN_ENCODER_DT, PIN_ENCODER_SW):
                claim_input(pin)
            target = lambda: _loop(evt_bus, stop)  # noqa: E731
        except Exception as e:
            log.error("encoder init failed (%s)", e)
            target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.encoder", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    log.info("encoder thread started (dry_run=%s)", dry_run)
    return th

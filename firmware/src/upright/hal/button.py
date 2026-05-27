"""Two tactile buttons (active low, pull-up) via lgpio."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from ..config import PIN_BUTTON_A, PIN_BUTTON_B
from ..events import Event, EventBus, EventType
from .gpio_lgpio import claim_input, read_active_low

log = logging.getLogger("hal.button")

_DOUBLE_GAP = 0.5
_LONG_THRESHOLD = 1.5
_VERYLONG_THRESHOLD = 3.0


def classify(presses: list[float], hold_duration: float) -> str:
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


@dataclass
class _BtnState:
    name: str
    pin: int
    map_short: str
    map_long: str
    map_verylong: str | None = None
    presses: list[float] = field(default_factory=list)
    pressed_at: float | None = None


def _map_pattern(state: _BtnState, pattern: str) -> str:
    if pattern == "verylong" and state.map_verylong:
        return state.map_verylong
    if pattern == "long":
        return state.map_long
    return state.map_short if pattern == "single" else pattern


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:  # pragma: no cover
    states = [
        _BtnState("a", PIN_BUTTON_A, map_short="long", map_long="long", map_verylong="verylong"),
        _BtnState("b", PIN_BUTTON_B, map_short="single", map_long="double", map_verylong="triple"),
    ]
    for st in states:
        claim_input(st.pin)

    log.info("buttons on GPIO %s (A) and GPIO %s (B)", PIN_BUTTON_A, PIN_BUTTON_B)

    while not stop.is_set():
        now = time.time()
        for st in states:
            is_down = read_active_low(st.pin)
            if is_down and st.pressed_at is None:
                st.pressed_at = now
            elif not is_down and st.pressed_at is not None:
                hold = now - st.pressed_at
                st.pressed_at = None
                if hold >= _LONG_THRESHOLD:
                    pattern = classify([], hold)
                    mapped = _map_pattern(st, pattern)
                    evt_bus.publish(
                        Event(
                            EventType.BUTTON_PRESS,
                            payload={"pattern": mapped, "button": st.name, "raw": pattern},
                        )
                    )
                    st.presses.clear()
                else:
                    st.presses.append(now)
            if st.presses and (now - st.presses[-1]) > _DOUBLE_GAP and st.pressed_at is None:
                pattern = classify(st.presses, 0)
                mapped = _map_pattern(st, pattern)
                evt_bus.publish(
                    Event(
                        EventType.BUTTON_PRESS,
                        payload={"pattern": mapped, "button": st.name, "raw": pattern},
                    )
                )
                st.presses.clear()
        time.sleep(0.02)


def _stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    while not stop.is_set():
        stop.wait(60.0)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    else:
        try:
            claim_input(PIN_BUTTON_A)
            claim_input(PIN_BUTTON_B)
            target = lambda: _loop(evt_bus, stop)  # noqa: E731
        except Exception as e:
            log.error("button init failed (%s)", e)
            target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.button", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    log.info("button thread started (dry_run=%s)", dry_run)
    return th

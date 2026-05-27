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

# Same timing both buttons. Short = release before 1.8s; long fires at 1.8s while held.
_DOUBLE_GAP = 0.5
_LONG_THRESHOLD = 1.8
_VERYLONG_THRESHOLD = 3.5
_LONG_COOLDOWN = 0.1


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


def classify_hold(hold_duration: float) -> str:
    if hold_duration >= _VERYLONG_THRESHOLD:
        return "verylong"
    if hold_duration >= _LONG_THRESHOLD:
        return "long"
    return "single"


@dataclass
class _BtnState:
    name: str
    pin: int
    presses: list[float] = field(default_factory=list)
    pressed_at: float | None = None
    long_fired: bool = False
    cooldown_until: float = 0.0


def _emit(evt_bus: EventBus, st: _BtnState, pattern: str) -> None:
    evt_bus.publish(
        Event(
            EventType.BUTTON_PRESS,
            payload={"pattern": pattern, "button": st.name, "raw": pattern},
        )
    )


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:  # pragma: no cover
    states = [
        _BtnState("a", PIN_BUTTON_A),
        _BtnState("b", PIN_BUTTON_B),
    ]
    for st in states:
        claim_input(st.pin)

    log.info(
        "buttons GPIO %s / %s — long at %.1fs (instant), short gap %.2fs, cooldown %.1fs",
        PIN_BUTTON_A,
        PIN_BUTTON_B,
        _LONG_THRESHOLD,
        _DOUBLE_GAP,
        _LONG_COOLDOWN,
    )

    while not stop.is_set():
        now = time.time()
        for st in states:
            if now < st.cooldown_until:
                continue

            is_down = read_active_low(st.pin)

            if is_down:
                if st.pressed_at is None:
                    st.pressed_at = now
                    st.long_fired = False
                elif not st.long_fired and (now - st.pressed_at) >= _LONG_THRESHOLD:
                    hold = now - st.pressed_at
                    pattern = classify_hold(hold)
                    st.long_fired = True
                    _emit(evt_bus, st, pattern)
                    st.presses.clear()
                    st.cooldown_until = now + _LONG_COOLDOWN
            elif st.pressed_at is not None:
                if not st.long_fired:
                    st.presses.append(now)
                st.pressed_at = None
                st.long_fired = False

            if (
                st.presses
                and st.pressed_at is None
                and now >= st.cooldown_until
                and (now - st.presses[-1]) > _DOUBLE_GAP
            ):
                pattern = classify(st.presses, 0)
                _emit(evt_bus, st, pattern)
                st.presses.clear()
                st.cooldown_until = now + _LONG_COOLDOWN

        time.sleep(0.01)


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

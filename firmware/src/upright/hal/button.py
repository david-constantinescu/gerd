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

_VERYLONG_THRESHOLD = 3.5
_LONG_COOLDOWN = 0.1

# Per-button timing — bottom (B) gets a longer short window before long fires.
_BTN_TIMING: dict[str, dict[str, float]] = {
    "a": {"long": 1.8, "gap": 0.50},
    "b": {"long": 2.35, "gap": 0.62},
}


def classify(presses: list[float], hold_duration: float, *, long_threshold: float) -> str:
    if hold_duration >= _VERYLONG_THRESHOLD:
        return "verylong"
    if hold_duration >= long_threshold:
        return "long"
    n = len(presses)
    if n >= 3:
        return "triple"
    if n == 2:
        return "double"
    return "single"


def classify_hold(hold_duration: float, *, long_threshold: float) -> str:
    if hold_duration >= _VERYLONG_THRESHOLD:
        return "verylong"
    if hold_duration >= long_threshold:
        return "long"
    return "single"


@dataclass
class _BtnState:
    name: str
    pin: int
    long_threshold: float
    double_gap: float
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


def _read_pressed(pin: int) -> bool:
    """Three-sample debounce — helps flaky bottom button contacts."""
    hits = sum(1 for _ in range(3) if read_active_low(pin))
    return hits >= 2


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:  # pragma: no cover
    states = [
        _BtnState(
            "a",
            PIN_BUTTON_A,
            long_threshold=_BTN_TIMING["a"]["long"],
            double_gap=_BTN_TIMING["a"]["gap"],
        ),
        _BtnState(
            "b",
            PIN_BUTTON_B,
            long_threshold=_BTN_TIMING["b"]["long"],
            double_gap=_BTN_TIMING["b"]["gap"],
        ),
    ]
    for st in states:
        claim_input(st.pin)

    log.info(
        "buttons GPIO %s / %s — A long=%.2fs gap=%.2fs | B long=%.2fs gap=%.2fs",
        PIN_BUTTON_A,
        PIN_BUTTON_B,
        _BTN_TIMING["a"]["long"],
        _BTN_TIMING["a"]["gap"],
        _BTN_TIMING["b"]["long"],
        _BTN_TIMING["b"]["gap"],
    )

    while not stop.is_set():
        now = time.time()
        for st in states:
            if now < st.cooldown_until:
                continue

            is_down = _read_pressed(st.pin)

            if is_down:
                if st.pressed_at is None:
                    st.pressed_at = now
                    st.long_fired = False
                elif not st.long_fired and (now - st.pressed_at) >= st.long_threshold:
                    hold = now - st.pressed_at
                    pattern = classify_hold(hold, long_threshold=st.long_threshold)
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
                and (now - st.presses[-1]) > st.double_gap
            ):
                pattern = classify(
                    st.presses, 0, long_threshold=st.long_threshold
                )
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

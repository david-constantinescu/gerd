"""Two tactile buttons (active low, pull-up) via lgpio.

Tap patterns only — no long-press detection. Double-tap carries the actions
that used to be on long press (back on top, open menu / branch on bottom).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from ..config import PIN_BUTTON_A, PIN_BUTTON_B, TUNABLES
from ..events import Event, EventBus, EventType
from .gpio_lgpio import claim_input, read_gpio

log = logging.getLogger("hal.button")

_COOLDOWN = 0.08

# Max gap between taps in a multi-tap gesture (seconds).
_BTN_TIMING: dict[str, float] = {
    "a": 0.50,
    "b": 0.62,  # bottom button — slightly more forgiving
}


def classify(presses: list[float]) -> str:
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
    double_gap: float
    presses: list[float] = field(default_factory=list)
    pressed_at: float | None = None
    cooldown_until: float = 0.0


def _emit(evt_bus: EventBus, st: _BtnState, pattern: str) -> None:
    log.info("button %s %s", st.name, pattern)
    evt_bus.publish(
        Event(
            EventType.BUTTON_PRESS,
            payload={"pattern": pattern, "button": st.name, "raw": pattern},
        )
    )


def _is_pressed_level(level: int) -> bool:
    if getattr(TUNABLES, "button_active_high", False):
        return level == 1
    return level == 0


def _read_pressed(pin: int) -> bool:
    """Two-sample debounce under the global GPIO lock."""
    hits = sum(1 for _ in range(2) if _is_pressed_level(read_gpio(pin)))
    return hits >= 1


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:  # pragma: no cover
    states = [
        _BtnState("a", PIN_BUTTON_A, double_gap=_BTN_TIMING["a"]),
        _BtnState("b", PIN_BUTTON_B, double_gap=_BTN_TIMING["b"]),
    ]
    for st in states:
        if not claim_input(st.pin):
            log.error("button %s GPIO %s not claimed", st.name, st.pin)

    log.info(
        "buttons GPIO %s / %s — tap only (A gap=%.2fs | B gap=%.2fs)",
        PIN_BUTTON_A,
        PIN_BUTTON_B,
        _BTN_TIMING["a"],
        _BTN_TIMING["b"],
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
            elif st.pressed_at is not None:
                st.presses.append(now)
                st.pressed_at = None

            if (
                st.presses
                and st.pressed_at is None
                and now >= st.cooldown_until
                and (now - st.presses[-1]) > st.double_gap
            ):
                pattern = classify(st.presses)
                _emit(evt_bus, st, pattern)
                st.presses.clear()
                st.cooldown_until = now + _COOLDOWN

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

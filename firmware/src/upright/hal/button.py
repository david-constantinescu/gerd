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
from .gpio_lgpio import claim_input, read_active_low

log = logging.getLogger("hal.button")

_COOLDOWN = 0.08


def classify(presses: list[float]) -> str:
    n = len(presses)
    if n >= 2:
        return "double"
    return "single"


def ready_to_emit(
    presses: list[float],
    now: float,
    *,
    gap: float,
    window: float,
    pressed_at: float | None,
) -> bool:
    """Wait for a possible second tap before emitting a lone single."""
    if not presses or pressed_at is not None:
        return False
    if (now - presses[-1]) < gap:
        return False
    if len(presses) == 1 and (now - presses[0]) < window:
        return False
    return True


def _timing() -> tuple[float, float]:
    gap = float(getattr(TUNABLES, "button_double_gap_s", 0.40) or 0.40)
    window = float(getattr(TUNABLES, "button_multi_tap_window_s", 0.60) or 0.60)
    return gap, max(window, gap + 0.15)


@dataclass
class _BtnState:
    name: str
    pin: int
    presses: list[float] = field(default_factory=list)
    pressed_at: float | None = None
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
    gap, window = _timing()
    states = [
        _BtnState("a", PIN_BUTTON_A),
        _BtnState("b", PIN_BUTTON_B),
    ]
    for st in states:
        claim_input(st.pin)

    log.info(
        "buttons GPIO %s / %s — gap=%.2fs window=%.2fs",
        PIN_BUTTON_A,
        PIN_BUTTON_B,
        gap,
        window,
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

            if ready_to_emit(
                st.presses, now, gap=gap, window=window, pressed_at=st.pressed_at
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

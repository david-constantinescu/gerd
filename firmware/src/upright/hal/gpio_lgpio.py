"""GPIO input/output via lgpio — avoids RPi.GPIO clashes with luma SPI (DC/RST)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_chip: int | None = None


def _handle() -> int:
    global _chip
    import lgpio  # type: ignore[import-not-found]

    with _lock:
        if _chip is None:
            _chip = lgpio.gpiochip_open(0)
        return _chip


def claim_input(pin: int) -> None:
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        try:
            lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
        except lgpio.error:
            pass


def claim_output(pin: int, *, initial: int = 0) -> None:
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        try:
            lgpio.gpio_claim_output(h, pin, initial)
        except lgpio.error:
            pass


def read_active_low(pin: int) -> bool:
    return read_gpio(pin) == 0


def read_gpio(pin: int) -> int:
    """Return 0 or 1 (high = 1)."""
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        return int(lgpio.gpio_read(h, pin))


def write(pin: int, value: int) -> None:
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        lgpio.gpio_write(h, pin, value)

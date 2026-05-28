"""GPIO input/output via lgpio — avoids RPi.GPIO clashes with luma SPI (DC/RST)."""

from __future__ import annotations

import logging
import threading

log = logging.getLogger("hal.gpio")

_lock = threading.RLock()
_chip: int | None = None
_claimed_inputs: set[int] = set()


def _handle() -> int:
    global _chip
    import lgpio  # type: ignore[import-not-found]

    with _lock:
        if _chip is None:
            _chip = lgpio.gpiochip_open(0)
        return _chip


def _free_unlocked(h: int, pin: int) -> None:
    """Release a pin without taking _lock (caller must hold the lock)."""
    import lgpio  # type: ignore[import-not-found]

    try:
        lgpio.gpio_free(h, pin)
    except lgpio.error:
        pass
    _claimed_inputs.discard(pin)


def claim_input(pin: int) -> bool:
    """Claim BCM pin as input with pull-up. Returns True on success."""
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        try:
            lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
            _claimed_inputs.add(pin)
            return True
        except lgpio.error as e:
            log.warning("GPIO %s input claim failed: %s", pin, e)
            return False


def reclaim_input(pin: int) -> bool:
    """Free then reclaim — use after Blinka/luma display init may have touched the chip."""
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        _free_unlocked(h, pin)
        try:
            lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
            _claimed_inputs.add(pin)
            return True
        except lgpio.error as e:
            log.warning("GPIO %s reclaim failed: %s", pin, e)
            return False


def reclaim_button_inputs() -> None:
    """Re-assert button inputs after display drivers initialize."""
    from ..config import PIN_BUTTON_A, PIN_BUTTON_B

    for pin, label in ((PIN_BUTTON_A, "top"), (PIN_BUTTON_B, "bottom")):
        ok = reclaim_input(pin)
        level = read_gpio(pin) if ok else -1
        log.info(
            "button GPIO %s (%s): %s idle=%s",
            pin,
            label,
            "ok" if ok else "FAILED",
            level,
        )


def claim_output(pin: int, *, initial: int = 0) -> None:
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        try:
            lgpio.gpio_claim_output(h, pin, initial)
        except lgpio.error:
            pass


def read_gpio(pin: int) -> int:
    """Return 0 or 1 (high = 1)."""
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        return int(lgpio.gpio_read(h, pin))


def read_active_low(pin: int) -> bool:
    return read_gpio(pin) == 0


def write(pin: int, value: int) -> None:
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        lgpio.gpio_write(h, pin, value)


def free(pin: int) -> None:
    h = _handle()
    with _lock:
        _free_unlocked(h, pin)


def claim_input_strict(pin: int) -> None:
    """Claim with pull-up; raises if pin is reserved (e.g. GPIO 28 on Pi Zero)."""
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        _free_unlocked(h, pin)
        lgpio.gpio_claim_input(h, pin, lgpio.SET_PULL_UP)
        _claimed_inputs.add(pin)


def claim_output_strict(pin: int, *, initial: int = 0) -> None:
    import lgpio  # type: ignore[import-not-found]

    h = _handle()
    with _lock:
        _free_unlocked(h, pin)
        lgpio.gpio_claim_output(h, pin, initial)

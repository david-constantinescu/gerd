#!/usr/bin/env python3
"""Live button test — run on the Pi while you press the physical buttons.

Stop the main app first (it owns the GPIO pins):

    sudo systemctl stop upright
    cd ~/upright/firmware && source ../.venv/bin/activate
    PYTHONPATH=src python3 scripts/pi_button_live_test.py

Results print on screen and are saved to /tmp/upright_button_test.log
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from upright.config import PIN_BUTTON_A, PIN_BUTTON_B
from upright.events import EventBus, EventType
from upright.hal import button
from upright.hal.gpio_lgpio import claim_input_strict, read_gpio

LOG_PATH = Path("/tmp/upright_button_test.log")


def _log(msg: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _sample_raw(seconds: float) -> tuple[int, int, bool]:
    """Return (press_count_a, press_count_b, any_low_idle)."""
    count_a = count_b = 0
    saw_low = False
    end = time.time() + seconds
    last_a = last_b = 1
    while time.time() < end:
        a, b = read_gpio(PIN_BUTTON_A), read_gpio(PIN_BUTTON_B)
        if a == 0 and last_a == 1:
            count_a += 1
            _log(f"RAW GPIO  press TOP    (GPIO{PIN_BUTTON_A}=0)")
        if b == 0 and last_b == 1:
            count_b += 1
            _log(f"RAW GPIO  press BOTTOM (GPIO{PIN_BUTTON_B}=0)")
        if a == 0 or b == 0:
            saw_low = True
        last_a, last_b = a, b
        time.sleep(0.02)
    return count_a, count_b, saw_low


def main() -> int:
    parser = argparse.ArgumentParser(description="Live UpRight button test")
    parser.add_argument(
        "--seconds",
        type=int,
        default=90,
        help="How long to listen (default 90)",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Only poll GPIO (skip firmware tap classifier)",
    )
    args = parser.parse_args()

    LOG_PATH.write_text(f"=== button test started {datetime.now().isoformat()} ===\n")

    _log("UpRight button live test")
    _log(f"TOP=GPIO{PIN_BUTTON_A}  BOTTOM=GPIO{PIN_BUTTON_B}  (active low: idle 1, pressed 0)")
    _log("")

    for pin, label in ((PIN_BUTTON_A, "TOP"), (PIN_BUTTON_B, "BOTTOM")):
        try:
            claim_input_strict(pin)
            level = read_gpio(pin)
            _log(f"Claimed {label} GPIO{pin} — idle level={level} ({'OK' if level == 1 else 'STUCK LOW?'})")
        except Exception as e:
            _log(f"FAILED to claim {label} GPIO{pin}: {e}")
            _log("Stop upright.service and try again.")
            return 1

    _log("")
    _log(f">>> Press TOP and BOTTOM buttons now ({args.seconds}s) <<<")
    _log("")

    hal_events: list[str] = []
    if not args.raw_only:
        bus = EventBus()
        th = button.start_thread(bus, dry_run=False)
        end = time.time() + args.seconds
        while time.time() < end:
            ev = bus.get(timeout=0.1)
            if ev and ev.type == EventType.BUTTON_PRESS:
                btn = ev.payload.get("button", "?")
                pat = ev.payload.get("pattern", "?")
                side = "TOP" if btn == "a" else "BOTTOM" if btn == "b" else btn
                msg = f"FIRMWARE  {side}  {pat}"
                _log(msg)
                hal_events.append(msg)
        th.stop.set()  # type: ignore[attr-defined]
        th.join(timeout=1.0)

    raw_a, raw_b, _ = _sample_raw(args.seconds if args.raw_only else 0.5)

    if not args.raw_only and args.seconds > 1:
        _log("")
        _log("--- also sampling raw GPIO for 0.5s ---")
        raw_a, raw_b, _ = _sample_raw(0.5)

    _log("")
    _log("=== SUMMARY ===")
    _log(f"  Raw GPIO edges — top: {raw_a}  bottom: {raw_b}")
    if not args.raw_only:
        _log(f"  Firmware tap events: {len(hal_events)}")
        for line in hal_events:
            _log(f"    {line}")

    if raw_a == 0 and raw_b == 0 and not hal_events:
        _log("")
        _log("FAIL: Pi did not see any button presses.")
        _log("Check: wires on GPIO 20 (top) and 21 (bottom), common GND, buttons active-low.")
        return 2
    if raw_a + raw_b > 0 and not hal_events and not args.raw_only:
        _log("")
        _log("PARTIAL: GPIO works but tap classifier emitted nothing — timing/wiring bounce.")
        return 3
    if hal_events or raw_a + raw_b > 0:
        _log("")
        _log("OK: Buttons are reaching the Pi.")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

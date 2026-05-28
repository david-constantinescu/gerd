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
from upright.hal.gpio_lgpio import claim_input, read_gpio

LOG_PATH = Path("/tmp/upright_button_test.log")


def _log(msg: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live UpRight button test")
    parser.add_argument(
        "--seconds",
        type=int,
        default=90,
        help="How long to listen (default 90)",
    )
    args = parser.parse_args()

    LOG_PATH.write_text(f"=== button test started {datetime.now().isoformat()} ===\n")

    _log("UpRight button live test")
    _log(f"TOP=GPIO{PIN_BUTTON_A}  BOTTOM=GPIO{PIN_BUTTON_B}  (idle=1, pressed=0)")
    _log("")

    for pin, label in ((PIN_BUTTON_A, "TOP"), (PIN_BUTTON_B, "BOTTOM")):
        try:
            claim_input(pin)
            level = read_gpio(pin)
            state = "OK" if level == 1 else "STUCK LOW — check wiring"
            _log(f"GPIO{pin} {label}: idle level={level} ({state})")
        except Exception as e:
            _log(f"FAILED GPIO{pin} {label}: {e}")
            _log("Run: sudo systemctl stop upright")
            return 1

    _log("")
    _log(f">>> PRESS TOP AND BOTTOM NOW ({args.seconds} seconds) <<<")
    _log("")

    bus = EventBus()
    th = button.start_thread(bus, dry_run=False)

    raw_a = raw_b = 0
    hal_events: list[str] = []
    last_a, last_b = read_gpio(PIN_BUTTON_A), read_gpio(PIN_BUTTON_B)
    end = time.time() + args.seconds

    while time.time() < end:
        ev = bus.get(timeout=0.02)
        if ev and ev.type == EventType.BUTTON_PRESS:
            btn = ev.payload.get("button", "?")
            pat = ev.payload.get("pattern", "?")
            side = "TOP" if btn == "a" else "BOTTOM" if btn == "b" else btn
            msg = f"FIRMWARE  {side}  tap={pat}"
            _log(msg)
            hal_events.append(msg)

        a, b = read_gpio(PIN_BUTTON_A), read_gpio(PIN_BUTTON_B)
        if a == 0 and last_a == 1:
            raw_a += 1
            _log(f"RAW GPIO  TOP pressed")
        if b == 0 and last_b == 1:
            raw_b += 1
            _log(f"RAW GPIO  BOTTOM pressed")
        last_a, last_b = a, b

    th.stop.set()  # type: ignore[attr-defined]
    th.join(timeout=1.0)

    _log("")
    _log("=== SUMMARY ===")
    _log(f"  Raw press edges — top: {raw_a}  bottom: {raw_b}")
    _log(f"  Firmware tap events: {len(hal_events)}")

    if raw_a == 0 and raw_b == 0:
        _log("")
        _log("FAIL: GPIO never went low — wiring or wrong pins.")
        _log("Expected: top→GPIO20, bottom→GPIO21, GND common.")
        return 2
    if raw_a + raw_b > 0 and len(hal_events) == 0:
        _log("")
        _log("PARTIAL: GPIO sees presses but tap detector emitted nothing.")
        return 3
    _log("")
    _log("OK: Buttons work at GPIO and firmware levels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

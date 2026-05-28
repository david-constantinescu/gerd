#!/usr/bin/env python3
"""Read button GPIO levels — stop upright first: sudo systemctl stop upright."""

from __future__ import annotations

import sys
import time

from upright.config import PIN_BUTTON_A, PIN_BUTTON_B
from upright.hal.gpio_lgpio import reclaim_input, read_gpio


def main() -> int:
    print("Button diagnostic (BCM 20 = top/A, BCM 21 = bottom/B)")
    print("Active-low: idle=1, pressed=0\n")
    for pin, name in ((PIN_BUTTON_A, "A top"), (PIN_BUTTON_B, "B bottom")):
        try:
            reclaim_input(pin)
            print(f"  {name} GPIO{pin}: claimed, idle={read_gpio(pin)}")
        except Exception as e:
            print(f"  {name} GPIO{pin}: FAILED — {e}")
            return 1
    print("\nSampling 10s — press each button…")
    saw = False
    for _ in range(100):
        a, b = read_gpio(PIN_BUTTON_A), read_gpio(PIN_BUTTON_B)
        if a == 0 or b == 0:
            print(f"  PRESS  A={a}  B={b}")
            saw = True
        time.sleep(0.1)
    if not saw:
        print("  No presses seen. Check wiring to GPIO 20/21 and common GND.")
        return 2
    print("OK — GPIO sees button presses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

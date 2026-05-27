#!/usr/bin/env python3
"""Quick I²C device scan. Run on the Pi after wiring sensors:

    python3 firmware/scripts/i2c_scan.py

Scans every ``/dev/i2c-*`` bus (same idea as ``i2cdetect -y N``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upright.hal.i2c_util import list_buses  # noqa: E402


def main() -> int:
    try:
        import smbus2
    except ImportError:
        print("smbus2 not installed — run on the Pi: pip install smbus2")
        return 1

    labels = {0x68: "MPU6050", 0x57: "MAX30102", 0x3C: "OLED", 0x3D: "OLED?"}
    found_any = False
    for bus_num in list_buses():
        print(f"Scanning I²C bus {bus_num}…")
        bus = smbus2.SMBus(bus_num)
        found = []
        for addr in range(0x03, 0x78):
            try:
                bus.read_byte(addr)
                found.append(addr)
            except OSError:
                continue
        bus.close()
        if not found:
            print("  (no devices)")
            continue
        found_any = True
        for addr in found:
            label = labels.get(addr, "?")
            print(f"  0x{addr:02x}  {label}")
    return 0 if found_any else 1


if __name__ == "__main__":
    raise SystemExit(main())

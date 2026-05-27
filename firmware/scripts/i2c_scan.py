#!/usr/bin/env python3
"""Quick I²C device scan. Run on the Pi after wiring sensors:

    sudo python3 firmware/scripts/i2c_scan.py

Scans every ``/dev/i2c-*`` bus (same idea as ``i2cdetect -y N``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upright.hal.i2c_probe import log_scan_results, scan_buses  # noqa: E402


def main() -> int:
    found = scan_buses()
    if not found:
        print("No I²C devices found on any bus.")
        print("Expected wiring: MPU6050 SDA=GPIO27, SCL=GPIO28, 3V3, GND")
        print("Enable bus: sudo bash scripts/pi-enable-hardware.sh && sudo reboot")
        log_scan_results(found)
        return 1
    for bus_num, addrs in sorted(found.items()):
        print(f"Scanning I²C bus {bus_num}…")
        from upright.hal.i2c_probe import _KNOWN

        for addr in addrs:
            print(f"  0x{addr:02x}  {_KNOWN.get(addr, '?')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

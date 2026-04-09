#!/usr/bin/env python3
"""Quick I²C device scan. Run on the Pi after wiring sensors:

    python3 firmware/scripts/i2c_scan.py

Equivalent to ``i2cdetect -y 1`` but spelled out.
"""

from __future__ import annotations


def main() -> int:
    try:
        import smbus2
    except ImportError:
        print("smbus2 not installed — run on the Pi: pip install smbus2")
        return 1
    bus = smbus2.SMBus(1)
    print("Scanning I²C bus 1…")
    found = []
    for addr in range(0x03, 0x78):
        try:
            bus.read_byte(addr)
            found.append(addr)
        except OSError:
            continue
    if not found:
        print("No devices found.")
        return 1
    for addr in found:
        label = {0x68: "MPU6050", 0x57: "MAX30102", 0x3C: "OLED", 0x3D: "OLED?"}.get(addr, "?")
        print(f"  0x{addr:02x}  {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Probe Pimoroni Zero LiPo / LiPo SHIM and any I²C fuel gauges."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upright.config import PIN_LIPO_ALERT  # noqa: E402


def _probe_zero_lipo() -> str | None:
    try:
        import RPi.GPIO as GPIO  # type: ignore[import-not-found]

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_LIPO_ALERT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        low = GPIO.input(PIN_LIPO_ALERT) == 0
        if low:
            return f"Zero LiPo GPIO {PIN_LIPO_ALERT}: LOW (battery warning ~<3.4V)"
        return f"Zero LiPo GPIO {PIN_LIPO_ALERT}: OK (pin high, battery above warning)"
    except Exception as e:
        return f"Zero LiPo GPIO {PIN_LIPO_ALERT}: unreadable ({e})"


def _probe_max17043() -> str | None:
    try:
        import smbus2  # type: ignore[import-not-found]
    except Exception:
        return None

    from upright.hal.i2c_util import list_buses

    addr = 0x36
    for bus_num in list_buses():
        try:
            bus = smbus2.SMBus(bus_num)
            msb = bus.read_byte_data(addr, 0x04)
            lsb = bus.read_byte_data(addr, 0x05)
            soc = msb + lsb / 256.0
            return f"MAX17043 on bus {bus_num}: {soc:.1f}%"
        except OSError:
            continue
        finally:
            try:
                bus.close()
            except Exception:
                pass
    return None


def _probe_power_supply() -> list[str]:
    out: list[str] = []
    root = Path("/sys/class/power_supply")
    if not root.exists():
        return out
    for dev in root.iterdir():
        if not dev.is_dir():
            continue
        cap = (dev / "capacity").read_text().strip() if (dev / "capacity").exists() else "?"
        volt = (
            (dev / "voltage_now").read_text().strip()
            if (dev / "voltage_now").exists()
            else "?"
        )
        out.append(f"{dev.name}: capacity={cap} voltage_now={volt}")
    return out


def main() -> int:
    print("== Battery / power ==")

    zl = _probe_zero_lipo()
    if zl:
        print(" ", zl)

    fg = _probe_max17043()
    if fg:
        print(" ", fg)
    else:
        print("  MAX17043 I²C gauge: not detected")

    ps = _probe_power_supply()
    if ps:
        for line in ps:
            print(" ", line)
    else:
        print("  /sys/class/power_supply: no entries")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

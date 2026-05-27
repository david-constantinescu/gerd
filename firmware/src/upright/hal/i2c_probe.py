"""Shared I²C discovery helpers for boot diagnostics and driver init."""

from __future__ import annotations

import logging

log = logging.getLogger("hal.i2c_probe")

_KNOWN: dict[int, str] = {
    0x36: "MAX17043/48 fuel gauge",
    0x3C: "OLED/SH1106",
    0x3D: "OLED alt",
    0x40: "INA219?",
    0x41: "INA219?",
    0x44: "INA219?",
    0x45: "INA219?",
    0x57: "MAX30102",
    0x68: "MPU6050",
    0x69: "MPU6050 AD0=1",
    0x6A: "LSM6DS3?",
    0x6B: "LSM6DS3?",
}


def scan_buses() -> dict[int, list[int]]:
    try:
        import smbus2  # type: ignore[import-not-found]
    except ImportError:
        return {}

    from .i2c_util import is_ghost_bus, list_buses

    found: dict[int, list[int]] = {}
    for bus_num in list_buses():
        if is_ghost_bus(bus_num):
            log.warning(
                "I²C bus %s skipped (ghost/stuck lines — check SDA=GPIO27 SCL=GPIO3)",
                bus_num,
            )
            continue
        addrs: list[int] = []
        bus = None
        try:
            bus = smbus2.SMBus(bus_num)
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    addrs.append(addr)
                except OSError:
                    continue
        except OSError as e:
            log.warning("I²C bus %s unavailable: %s", bus_num, e)
            continue
        finally:
            if bus is not None:
                bus.close()
        if addrs:
            found[bus_num] = addrs
    return found


def log_scan_results(found: dict[int, list[int]] | None = None) -> None:
    found = found if found is not None else scan_buses()
    if not found:
        log.warning(
            "I²C scan: no devices on any bus — MPU6050 expected @ 0x68 on "
            "GPIO 27/3 (SDA=27 SCL=3 — see reference docs/WIRING.md)"
        )
        return
    for bus_num, addrs in sorted(found.items()):
        parts = [f"0x{a:02x} ({_KNOWN.get(a, 'unknown')})" for a in addrs]
        log.info("I²C bus %s: %s", bus_num, ", ".join(parts))

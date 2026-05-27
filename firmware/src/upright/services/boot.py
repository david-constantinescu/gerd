"""Boot-time helpers — I²C summary and waiting for first HAL samples."""

from __future__ import annotations

import time

from ..events import EventBus, EventType
from ..hal.i2c_probe import scan_buses


def format_device_line(found: dict[int, list[int]] | None) -> str:
    """One-line summary of key peripherals for the boot OLED."""
    if not found:
        return "I2C: scanning…"
    addrs: set[int] = set()
    for devs in found.values():
        addrs.update(devs)
    parts: list[str] = []
    if 0x68 in addrs or 0x69 in addrs:
        parts.append("IMU")
    if 0x57 in addrs:
        parts.append("HR")
    if any(a in addrs for a in (0x36, 0x40, 0x41, 0x44, 0x45)):
        parts.append("Pwr")
    if not parts:
        n = sum(len(v) for v in found.values())
        return f"I2C: {n} dev"
    return " ".join(parts)


def scan_summary(*, dry_run: bool) -> tuple[dict[int, list[int]], str]:
    if dry_run:
        return {}, "Dry run"
    found = scan_buses()
    return found, format_device_line(found)


def wait_for_hal_samples(
    bus: EventBus,
    *,
    timeout_s: float = 3.5,
) -> tuple[bool, bool]:
    """Drain the bus until first posture and power samples (or timeout)."""
    deadline = time.time() + timeout_s
    imu_ok = False
    power_ok = False
    while time.time() < deadline:
        remaining = deadline - time.time()
        ev = bus.get(timeout=min(0.15, max(0.05, remaining)))
        if ev is None:
            continue
        if ev.type == EventType.POSTURE_SAMPLE:
            imu_ok = True
        elif ev.type == EventType.POWER_SAMPLE:
            power_ok = True
        if imu_ok and power_ok:
            break
    return imu_ok, power_ok


def sensor_status_line(*, imu_ok: bool, power_ok: bool, dry_run: bool) -> str:
    if dry_run:
        return "Sensors: simulated"
    imu = "IMU OK" if imu_ok else "IMU --"
    pwr = "Pwr OK" if power_ok else "Pwr --"
    return f"{imu}  {pwr}"

"""Boot sequence helpers."""

from __future__ import annotations

import time
from unittest.mock import patch

from upright.events import Event, EventBus, EventType
from upright.main import is_cold_boot
from upright.services.boot import (
    format_device_line,
    sensor_status_line,
    wait_for_hal_samples,
)


def test_format_device_line_mpu() -> None:
    line = format_device_line({1: [0x68, 0x57]})
    assert "IMU" in line
    assert "HR" in line


def test_wait_for_hal_samples() -> None:
    bus = EventBus()

    def publisher() -> None:
        time.sleep(0.05)
        bus.publish(
            Event(EventType.POSTURE_SAMPLE, payload={"pitch": 0.0, "roll": 0.0})
        )
        bus.publish(Event(EventType.POWER_SAMPLE, payload={"pct": 90}))

    import threading

    threading.Thread(target=publisher, daemon=True).start()
    imu, pwr = wait_for_hal_samples(bus, timeout_s=2.0)
    assert imu and pwr


def test_sensor_status_line() -> None:
    assert "OK" in sensor_status_line(imu_ok=True, power_ok=True, dry_run=False)
    assert "simulated" in sensor_status_line(imu_ok=False, power_ok=False, dry_run=True)


def test_is_cold_boot() -> None:
    with patch("upright.main._kernel_uptime_s", return_value=30.0):
        assert is_cold_boot()
    with patch("upright.main._kernel_uptime_s", return_value=600.0):
        assert not is_cold_boot()

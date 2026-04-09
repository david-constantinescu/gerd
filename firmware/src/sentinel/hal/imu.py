"""MPU6050 IMU driver.

Reads raw accelerometer registers over I²C and converts to pitch / roll
angles. Publishes ``POSTURE_SAMPLE`` events at the configured rate. Sampling
rate is dynamic — driven by the FSM state via :func:`set_rate`.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque

from ..config import I2C_ADDR_MPU6050
from ..events import Event, EventBus, EventType

log = logging.getLogger("hal.imu")

# MPU6050 register map (subset)
_PWR_MGMT_1 = 0x6B
_ACCEL_XOUT_H = 0x3B

_current_rate_hz: float = 2.0
_rate_lock = threading.Lock()


def set_rate(hz: float) -> None:
    """Called by the FSM whenever it switches state."""
    global _current_rate_hz
    with _rate_lock:
        _current_rate_hz = max(0.01, hz)


def _open_bus():
    import smbus2  # type: ignore[import-not-found]

    bus = smbus2.SMBus(1)
    # Wake up the MPU6050 (default is sleep mode after power-on).
    bus.write_byte_data(I2C_ADDR_MPU6050, _PWR_MGMT_1, 0)
    return bus


def _read_accel(bus) -> tuple[float, float, float]:
    raw = bus.read_i2c_block_data(I2C_ADDR_MPU6050, _ACCEL_XOUT_H, 6)
    ax = _twos(raw[0] << 8 | raw[1]) / 16384.0
    ay = _twos(raw[2] << 8 | raw[3]) / 16384.0
    az = _twos(raw[4] << 8 | raw[5]) / 16384.0
    return ax, ay, az


def _twos(val: int) -> int:
    return val - 65536 if val & 0x8000 else val


def angles_from_accel(ax: float, ay: float, az: float) -> tuple[float, float]:
    """Convert accel vector → (pitch_deg, roll_deg). Pitch = forward lean."""
    pitch = math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az)))
    roll = math.degrees(math.atan2(ay, math.sqrt(ax * ax + az * az)))
    return pitch, roll


def _loop(bus_obj, evt_bus: EventBus, stop: threading.Event) -> None:
    pitch_window: deque[float] = deque(maxlen=8)
    roll_window: deque[float] = deque(maxlen=8)
    while not stop.is_set():
        with _rate_lock:
            hz = _current_rate_hz
        try:
            ax, ay, az = _read_accel(bus_obj)
        except Exception as e:  # pragma: no cover
            log.warning("imu read failed: %s", e)
            time.sleep(1.0)
            continue
        pitch, roll = angles_from_accel(ax, ay, az)
        pitch_window.append(pitch)
        roll_window.append(roll)
        evt_bus.publish(
            Event(
                EventType.POSTURE_SAMPLE,
                payload={
                    "pitch": sum(pitch_window) / len(pitch_window),
                    "roll": sum(roll_window) / len(roll_window),
                    "pitch_raw": pitch,
                    "ax": ax,
                    "ay": ay,
                    "az": az,
                },
            )
        )
        stop.wait(1.0 / hz)


def _stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    """Generates sinusoidal posture data so the FSM has something to chew on
    during macOS development."""
    t0 = time.time()
    while not stop.is_set():
        with _rate_lock:
            hz = _current_rate_hz
        t = time.time() - t0
        pitch = 5.0 * math.sin(t / 7.0)  # gentle sway
        roll = 2.0 * math.sin(t / 11.0)
        evt_bus.publish(Event(EventType.POSTURE_SAMPLE, payload={"pitch": pitch, "roll": roll}))
        stop.wait(1.0 / hz)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
        log.info("starting IMU stub thread")
    else:
        try:
            bus_obj = _open_bus()
            target = lambda: _loop(bus_obj, evt_bus, stop)  # noqa: E731
            log.info("starting IMU thread @ %.2f Hz", _current_rate_hz)
        except Exception as e:
            log.error("could not open MPU6050 (%s) — falling back to stub", e)
            target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.imu", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    return th

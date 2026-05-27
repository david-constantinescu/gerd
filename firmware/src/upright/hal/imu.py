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

from ..config import I2C_ADDR_MPU6050, TUNABLES
from ..events import Event, EventBus, EventType
from .i2c_probe import log_scan_results, scan_buses

log = logging.getLogger("hal.imu")

# MPU6050 register map (subset)
_PWR_MGMT_1 = 0x6B
_CONFIG = 0x1A
_ACCEL_XOUT_H = 0x3B

# DLPF ≈5 Hz accel bandwidth — cuts high-frequency vibration noise.
_DLPF_5HZ = 6

_MPU_ADDRS = (I2C_ADDR_MPU6050, 0x69)

_current_rate_hz: float = 2.0
_rate_lock = threading.Lock()


def set_rate(hz: float) -> None:
    """Called by the FSM whenever it switches state."""
    global _current_rate_hz
    with _rate_lock:
        _current_rate_hz = max(0.01, hz)


def _open_bus() -> tuple[object, int]:
    from .i2c_util import open_smbus, probe_address

    last_err: Exception | None = None
    for addr in _MPU_ADDRS:
        preferred = probe_address(addr)
        if preferred is None:
            continue
        try:
            bus, bus_num = open_smbus(addr, preferred=preferred)
            bus.write_byte_data(addr, _PWR_MGMT_1, 0)
            bus.write_byte_data(addr, _CONFIG, _DLPF_5HZ)
            log.info("MPU6050 opened on bus %s at 0x%02x (DLPF 5 Hz)", bus_num, addr)
            return bus, addr
        except Exception as e:
            last_err = e
    raise OSError(f"could not open MPU6050 at {_MPU_ADDRS}") from last_err


def _read_accel(bus, addr: int) -> tuple[float, float, float]:
    raw = bus.read_i2c_block_data(addr, _ACCEL_XOUT_H, 6)
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


def _loop(bus_obj, addr: int, evt_bus: EventBus, stop: threading.Event) -> None:
    pitch_ema: float | None = None
    roll_ema: float | None = None
    while not stop.is_set():
        with _rate_lock:
            hz = _current_rate_hz
        alpha = max(0.05, min(1.0, TUNABLES.imu_smooth_alpha))
        try:
            ax, ay, az = _read_accel(bus_obj, addr)
        except Exception as e:  # pragma: no cover
            log.warning("imu read failed: %s", e)
            time.sleep(1.0)
            continue
        pitch_raw, roll_raw = angles_from_accel(ax, ay, az)
        if pitch_ema is None:
            pitch_ema = pitch_raw
            roll_ema = roll_raw
        else:
            pitch_ema = alpha * pitch_raw + (1.0 - alpha) * pitch_ema
            roll_ema = alpha * roll_raw + (1.0 - alpha) * roll_ema
        evt_bus.publish(
            Event(
                EventType.POSTURE_SAMPLE,
                payload={
                    "pitch": pitch_ema,
                    "roll": roll_ema,
                    "pitch_raw": pitch_raw,
                    "ax": ax,
                    "ay": ay,
                    "az": az,
                },
            )
        )
        stop.wait(1.0 / hz)


def _dev_stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    """Animated posture for macOS / dry-run development."""
    t0 = time.time()
    while not stop.is_set():
        with _rate_lock:
            hz = _current_rate_hz
        t = time.time() - t0
        pitch = 5.0 * math.sin(t / 7.0)
        roll = 2.0 * math.sin(t / 11.0)
        evt_bus.publish(
            Event(EventType.POSTURE_SAMPLE, payload={"pitch": pitch, "roll": roll})
        )
        stop.wait(1.0 / hz)


def _neutral_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    """Stable neutral posture when no IMU is connected on real hardware."""
    log.warning(
        "IMU unavailable — reporting neutral posture (0°). "
        "Connect MPU6050 on I²C and run firmware/scripts/i2c_scan.py"
    )
    while not stop.is_set():
        with _rate_lock:
            hz = _current_rate_hz
        evt_bus.publish(
            Event(
                EventType.POSTURE_SAMPLE,
                payload={"pitch": 0.0, "roll": 0.0},
            )
        )
        stop.wait(1.0 / hz)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _dev_stub_loop(evt_bus, stop)  # noqa: E731
        log.info("starting IMU dev stub thread")
    else:
        found = scan_buses()
        log_scan_results(found)
        try:
            bus_obj, addr = _open_bus()
            target = lambda: _loop(bus_obj, addr, evt_bus, stop)  # noqa: E731
            log.info("starting IMU thread @ %.2f Hz", _current_rate_hz)
        except Exception as e:
            log.warning("could not open MPU6050 (%s) — using neutral posture", e)
            target = lambda: _neutral_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.imu", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    return th

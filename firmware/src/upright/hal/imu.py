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

from ..config import I2C_ADDR_MPU6050, TUNABLES, USE_KERNEL_MPU_I2C
from ..events import Event, EventBus, EventType
from .i2c_probe import log_scan_results, scan_buses

log = logging.getLogger("hal.imu")

# MPU6050 register map (subset)
_PWR_MGMT_1 = 0x6B
_WHO_AM_I = 0x75
_MPU_WHO_AM_I_VALUE = 0x68
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
    from .i2c_util import is_ghost_bus, list_buses, open_smbus

    last_err: Exception | None = None
    for bus_num in list_buses():
        if is_ghost_bus(bus_num):
            log.warning(
                "I²C bus %s looks stuck (ghost ACKs) — check MPU6050 wiring/pull-ups on GPIO 27/28",
                bus_num,
            )
            continue
        for addr in _MPU_ADDRS:
            bus_obj = None
            try:
                bus_obj, found_bus = open_smbus(addr, preferred=bus_num)
                bus_obj.write_byte_data(addr, _PWR_MGMT_1, 0)
                time.sleep(0.05)
                who = bus_obj.read_byte_data(addr, _WHO_AM_I)
                if who != _MPU_WHO_AM_I_VALUE:
                    raise OSError(f"WHO_AM_I=0x{who:02x} expected 0x68")
                bus_obj.write_byte_data(addr, _CONFIG, _DLPF_5HZ)
                log.info(
                    "MPU6050 opened on bus %s at 0x%02x (WHO_AM_I ok, DLPF 5 Hz)",
                    found_bus,
                    addr,
                )
                return bus_obj, addr
            except Exception as e:
                last_err = e
                if bus_obj is not None:
                    try:
                        bus_obj.close()
                    except Exception:
                        pass
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


def _loop_smbus(bus_obj, addr: int, evt_bus: EventBus, stop: threading.Event) -> None:
    _loop_reader(lambda: _read_accel(bus_obj, addr), evt_bus, stop)


def _loop_bitbang(reader, evt_bus: EventBus, stop: threading.Event) -> None:
    _loop_reader(reader.read_accel, evt_bus, stop)


def _loop_reader(read_accel, evt_bus: EventBus, stop: threading.Event) -> None:
    pitch_ema: float | None = None
    roll_ema: float | None = None
    while not stop.is_set():
        with _rate_lock:
            hz = _current_rate_hz
        alpha = max(0.05, min(1.0, TUNABLES.imu_smooth_alpha))
        try:
            ax, ay, az = read_accel()
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


def _open_bitbang():
    from .i2c_bitbang import Mpu6050Bitbang

    reader = Mpu6050Bitbang()
    reader.open()
    return ("bitbang", reader, reader._addr)


def _open_mpu():
    """GPIO bit-bang on 27/28 by default; optional kernel smbus."""
    if not USE_KERNEL_MPU_I2C:
        try:
            return _open_bitbang()
        except OSError as e:
            log.warning("bit-bang MPU6050 failed (%s) — trying smbus", e)
    try:
        bus_obj, addr = _open_bus()
        return ("smbus", bus_obj, addr)
    except OSError as e:
        if USE_KERNEL_MPU_I2C:
            log.warning("smbus MPU6050 failed (%s) — trying bit-bang", e)
            return _open_bitbang()
        raise


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _dev_stub_loop(evt_bus, stop)  # noqa: E731
        log.info("starting IMU dev stub thread")
    else:
        found = scan_buses()
        log_scan_results(found)
        try:
            kind, handle, addr = _open_mpu()
            if kind == "smbus":
                target = lambda: _loop_smbus(handle, addr, evt_bus, stop)  # noqa: E731
            else:
                target = lambda: _loop_bitbang(handle, evt_bus, stop)  # noqa: E731
            log.info("starting IMU thread @ %.2f Hz", _current_rate_hz)
        except Exception as e:
            log.warning("could not open MPU6050 (%s) — using neutral posture", e)
            target = lambda: _neutral_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.imu", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    return th

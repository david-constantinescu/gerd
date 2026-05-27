"""MAX30102 HRV / heart-rate driver.

Reads the optical pulse-ox FIFO, runs a very lightweight peak detector on the
IR channel, and publishes ``HRV_SAMPLE`` events with running BPM and RMSSD.
Pauses cleanly when the sensor reports no skin contact (DC level too low).
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque

from ..config import I2C_ADDR_MAX30102
from ..events import Event, EventBus, EventType

log = logging.getLogger("hal.hrv")

_FIFO_DATA = 0x07
_MODE_CONFIG = 0x09
_SPO2_CONFIG = 0x0A
_LED1_PA = 0x0C  # red
_LED2_PA = 0x0D  # IR


def _open_bus():
    from .i2c_util import open_smbus

    bus, _ = open_smbus(I2C_ADDR_MAX30102)
    # Heart-rate mode, 100Hz, ~half-power LEDs.
    bus.write_byte_data(I2C_ADDR_MAX30102, _MODE_CONFIG, 0x02)
    bus.write_byte_data(I2C_ADDR_MAX30102, _SPO2_CONFIG, 0x27)
    bus.write_byte_data(I2C_ADDR_MAX30102, _LED1_PA, 0x24)
    bus.write_byte_data(I2C_ADDR_MAX30102, _LED2_PA, 0x24)
    return bus


def _read_sample(bus) -> tuple[int, int]:
    raw = bus.read_i2c_block_data(I2C_ADDR_MAX30102, _FIFO_DATA, 6)
    red = ((raw[0] & 0x03) << 16) | (raw[1] << 8) | raw[2]
    ir = ((raw[3] & 0x03) << 16) | (raw[4] << 8) | raw[5]
    return red, ir


class _BeatDetector:
    """Very small AC-coupled threshold detector. Good enough for prototype."""

    def __init__(self) -> None:
        self.window: deque[int] = deque(maxlen=64)
        self.last_beat: float = 0.0
        self.intervals: deque[float] = deque(maxlen=20)
        self.rising = False

    def update(self, ir: int, now: float) -> bool:
        self.window.append(ir)
        if len(self.window) < 16:
            return False
        avg = sum(self.window) / len(self.window)
        if ir > avg * 1.01 and not self.rising:
            self.rising = True
            return False
        if ir < avg * 0.99 and self.rising:
            self.rising = False
            if self.last_beat:
                interval = now - self.last_beat
                if 0.4 < interval < 1.6:  # 37–150 BPM sanity range
                    self.intervals.append(interval)
            self.last_beat = now
            return True
        return False

    def bpm(self) -> float | None:
        if len(self.intervals) < 3:
            return None
        avg_interval = sum(self.intervals) / len(self.intervals)
        return 60.0 / avg_interval

    def rmssd_ms(self) -> float | None:
        if len(self.intervals) < 4:
            return None
        diffs = [
            (self.intervals[i + 1] - self.intervals[i]) * 1000.0
            for i in range(len(self.intervals) - 1)
        ]
        if not diffs:
            return None
        mean_sq = sum(d * d for d in diffs) / len(diffs)
        return math.sqrt(mean_sq)


def _loop(bus_obj, evt_bus: EventBus, stop: threading.Event) -> None:
    detector = _BeatDetector()
    while not stop.is_set():
        try:
            _, ir = _read_sample(bus_obj)
        except Exception as e:  # pragma: no cover
            log.warning("hrv read failed: %s", e)
            stop.wait(1.0)
            continue
        if ir < 5000:  # no skin contact
            stop.wait(0.5)
            continue
        now = time.time()
        if detector.update(ir, now):
            evt_bus.publish(
                Event(
                    EventType.HRV_SAMPLE,
                    payload={"bpm": detector.bpm(), "rmssd": detector.rmssd_ms()},
                )
            )
        stop.wait(0.01)  # ~100Hz


def _stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    while not stop.is_set():
        evt_bus.publish(Event(EventType.HRV_SAMPLE, payload={"bpm": 68.0, "rmssd": 42.0}))
        stop.wait(5.0)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
        log.info("starting HRV stub thread")
    else:
        try:
            bus_obj = _open_bus()
            target = lambda: _loop(bus_obj, evt_bus, stop)  # noqa: E731
            log.info("starting HRV thread")
        except Exception as e:
            log.error("could not open MAX30102 (%s) — falling back to stub", e)
            target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.hrv", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    return th

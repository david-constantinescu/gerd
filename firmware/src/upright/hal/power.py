"""Battery monitoring — I²C fuel gauge / INA219 preferred, Zero LiPo alert fallback."""

from __future__ import annotations

import logging
import threading
import time

from ..config import PIN_LIPO_ALERT
from ..events import Event, EventBus, EventType
from .gpio_lgpio import claim_input, read_active_low

log = logging.getLogger("hal.power")

_FUEL_GAUGE_ADDR = 0x36
_INA219_ADDRS = (0x40, 0x41, 0x44, 0x45)
_PCT_OK = 100
_PCT_LOW = 18

_source = "unknown"


def battery_source() -> str:
    """How ``battery_pct`` is derived: ``gauge``, ``ina219``, or ``alert_pin``."""
    return _source


def _read_max17043() -> float | None:
    try:
        import smbus2  # type: ignore[import-not-found]
    except ImportError:
        return None

    from .i2c_util import list_buses

    for bus_num in list_buses():
        bus = None
        try:
            bus = smbus2.SMBus(bus_num)
            msb = bus.read_byte_data(_FUEL_GAUGE_ADDR, 0x04)
            lsb = bus.read_byte_data(_FUEL_GAUGE_ADDR, 0x05)
            soc = msb + lsb / 256.0
            if 0.0 <= soc <= 100.0:
                return soc
        except OSError:
            continue
        finally:
            if bus is not None:
                bus.close()
    return None


def _read_ina219_mv() -> float | None:
    try:
        import smbus2  # type: ignore[import-not-found]
    except ImportError:
        return None

    from .i2c_util import list_buses

    for bus_num in list_buses():
        for addr in _INA219_ADDRS:
            bus = None
            try:
                bus = smbus2.SMBus(bus_num)
                raw = bus.read_word_data(addr, 0x02)
                # INA219 bus voltage register is big-endian; lower 3 bits are flags.
                value = ((raw & 0xFF) << 8) | (raw >> 8)
                mv = (value >> 3) * 4.0
                if 2500.0 <= mv <= 4300.0:
                    return mv
            except OSError:
                continue
            finally:
                if bus is not None:
                    bus.close()
    return None


def lipo_pct_from_voltage_mv(mv: float) -> int:
    """Rough single-cell LiPo state-of-charge from terminal voltage."""
    if mv >= 4200:
        return 100
    if mv >= 4000:
        return int(80 + (mv - 4000) / 200 * 20)
    if mv >= 3800:
        return int(50 + (mv - 3800) / 200 * 30)
    if mv >= 3700:
        return int(30 + (mv - 3700) / 100 * 20)
    if mv >= 3400:
        return int(10 + (mv - 3400) / 300 * 20)
    if mv >= 3300:
        return int((mv - 3300) / 100 * 10)
    return 0


def _sample_alert_pin() -> tuple[int, bool]:
    low_since_attr = "_lipo_low_since"
    low = read_active_low(PIN_LIPO_ALERT)
    now = time.time()
    if not hasattr(_sample_alert_pin, low_since_attr):
        setattr(_sample_alert_pin, low_since_attr, None)
    low_since: float | None = getattr(_sample_alert_pin, low_since_attr)
    if low:
        if low_since is None:
            low_since = now
            setattr(_sample_alert_pin, low_since_attr, low_since)
    else:
        low_since = None
        setattr(_sample_alert_pin, low_since_attr, None)
    low_battery = low_since is not None and (now - low_since) > 1.5
    pct = _PCT_LOW if low_battery else _PCT_OK
    return pct, low_battery


def sample_battery() -> tuple[int, bool, str]:
    """Return ``(pct, low_flag, source)``."""
    global _source

    soc = _read_max17043()
    if soc is not None:
        pct = int(round(soc))
        _source = "gauge"
        return max(0, min(100, pct)), pct <= 20, _source

    mv = _read_ina219_mv()
    if mv is not None:
        pct = lipo_pct_from_voltage_mv(mv)
        _source = "ina219"
        return pct, pct <= 20, _source

    pct, low = _sample_alert_pin()
    _source = "alert_pin"
    return pct, low, _source


def _loop(evt_bus: EventBus, stop: threading.Event) -> None:
    claim_input(PIN_LIPO_ALERT)
    pct, low, source = sample_battery()
    log.info(
        "battery monitor: source=%s initial=%s%% low=%s",
        source,
        pct,
        low,
    )
    while not stop.is_set():
        pct, low, source = sample_battery()
        evt_bus.publish(
            Event(
                EventType.POWER_SAMPLE,
                payload={
                    "battery_pct": pct,
                    "battery_low": low,
                    "battery_ok": not low,
                    "battery_source": source,
                },
            )
        )
        stop.wait(5.0)


def _stub_loop(evt_bus: EventBus, stop: threading.Event) -> None:
    global _source
    _source = "stub"
    while not stop.is_set():
        evt_bus.publish(
            Event(
                EventType.POWER_SAMPLE,
                payload={
                    "battery_pct": 100,
                    "battery_low": False,
                    "battery_ok": True,
                    "battery_source": "stub",
                },
            )
        )
        stop.wait(30.0)


def start_thread(evt_bus: EventBus, *, dry_run: bool) -> threading.Thread:
    stop = threading.Event()
    if dry_run:
        target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
        log.info("starting power stub thread")
    else:
        try:
            claim_input(PIN_LIPO_ALERT)
            target = lambda: _loop(evt_bus, stop)  # noqa: E731
            log.info("starting battery monitor on GPIO %s (+ I²C gauge scan)", PIN_LIPO_ALERT)
        except Exception as e:
            log.error("could not read LiPo alert pin (%s) — using stub", e)
            target = lambda: _stub_loop(evt_bus, stop)  # noqa: E731
    th = threading.Thread(target=target, name="hal.power", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    return th

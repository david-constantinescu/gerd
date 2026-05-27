"""I²C bus discovery helpers — scan every ``/dev/i2c-*`` node."""

from __future__ import annotations

from pathlib import Path

_CACHED_BUS: int | None = None


def list_buses() -> list[int]:
    buses: list[int] = []
    for path in sorted(Path("/dev").glob("i2c-*")):
        try:
            buses.append(int(path.name.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return buses or [1]


def ghost_bus_responders(bus_num: int) -> int:
    """Bit-bang buses with stuck SDA often ACK every address — treat as invalid."""
    import smbus2  # type: ignore[import-not-found]

    count = 0
    try:
        bus = smbus2.SMBus(bus_num)
    except OSError:
        return 0
    try:
        for addr in range(0x03, 0x78):
            try:
                bus.read_byte(addr)
                count += 1
            except OSError:
                continue
    finally:
        bus.close()
    return count


def is_ghost_bus(bus_num: int) -> bool:
    return ghost_bus_responders(bus_num) > 20


def probe_address(addr: int, *, buses: list[int] | None = None) -> int | None:
    import smbus2  # type: ignore[import-not-found]

    for bus_num in buses or list_buses():
        try:
            bus = smbus2.SMBus(bus_num)
        except OSError:
            continue
        try:
            bus.read_byte(addr)
        except OSError:
            continue
        finally:
            bus.close()
        return bus_num
    return None


def open_smbus(addr: int, *, preferred: int | None = None) -> tuple[object, int]:
    """Return ``(smbus, bus_number)`` for the first bus that responds at ``addr``."""
    global _CACHED_BUS
    import smbus2  # type: ignore[import-not-found]

    order: list[int] = []
    if preferred is not None and not is_ghost_bus(preferred):
        order.append(preferred)
    if _CACHED_BUS is not None and _CACHED_BUS not in order and not is_ghost_bus(_CACHED_BUS):
        order.append(_CACHED_BUS)
    for bus_num in list_buses():
        if bus_num not in order and not is_ghost_bus(bus_num):
            order.append(bus_num)

    last_err: Exception | None = None
    for bus_num in order:
        try:
            bus = smbus2.SMBus(bus_num)
            bus.read_byte(addr)
            _CACHED_BUS = bus_num
            return bus, bus_num
        except Exception as e:
            last_err = e
            continue
    raise OSError(f"no I²C device at 0x{addr:02x} on buses {order}") from last_err

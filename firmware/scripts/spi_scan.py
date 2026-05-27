#!/usr/bin/env python3
"""Inventory SPI buses/devices and run a harmless transfer test."""

from __future__ import annotations

import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    print("== SPI inventory ==")
    nodes = sorted(glob.glob("/dev/spidev*"))
    if not nodes:
        print("  no /dev/spidev* nodes — enable SPI: dtparam=spi=on")
        print("  disable fbtft kernel overlays if they claim the bus")
        return 1

    ok = 0
    for node in nodes:
        print(f"  device: {node}")
        try:
            import spidev  # type: ignore[import-not-found]

            parts = node.replace("/dev/spidev", "").split(".")
            bus, dev = int(parts[0]), int(parts[1])
            spi = spidev.SpiDev()
            spi.open(bus, dev)
            spi.max_speed_hz = 1_000_000
            spi.mode = 0
            resp = spi.xfer2([0x00, 0x00])
            spi.close()
            print(f"    xfer2 ok → {resp}")
            ok += 1
        except Exception as e:
            print(f"    FAIL open/xfer: {e}")

    print(f"== SPI summary: {ok}/{len(nodes)} devices responded ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

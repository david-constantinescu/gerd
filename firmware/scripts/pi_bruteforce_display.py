#!/usr/bin/env python3
"""Brute-force SPI DC/RST pin pairs for colour TFT panels."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upright.hal.display import _SPI_CANDIDATES, _open_spi, _save_config, _test_device

# Avoid encoder/button/motor/I2C/SPI lines
DC_PINS = [6, 9, 13, 16, 19, 20, 21, 23, 24, 25, 26]
RST_PINS = [5, 6, 12, 13, 16, 19, 20, 21, 23, 24, 25, 26]
DRIVERS = [
    ("st7789", 240, 240),
    ("st7789", 240, 320),
    ("ili9341", 240, 320),
    ("st7735", 128, 160),
]


def main() -> int:
    tried = 0
    for driver, w, h in DRIVERS:
        for dc in DC_PINS:
            for rst in RST_PINS:
                if dc == rst:
                    continue
                cfg = {
                    "interface": "spi",
                    "driver": driver,
                    "width": w,
                    "height": h,
                    "dc": dc,
                    "rst": rst,
                    "rotate": 0,
                }
                tried += 1
                try:
                    dev = _open_spi(cfg)
                    _test_device(dev, cfg)
                except Exception:
                    continue
                print(f"FOUND {cfg}")
                _save_config(cfg)
                return 0
    print(f"FAIL after {tried} combinations")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Recovery sweep: simple black text on white, then save best config."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageDraw

from upright.hal.display import DISPLAY_CONFIG_PATH, _close_device, _open_spi, _save_config

# User wiring: D/C BCM25, RST BCM24, 128x160 ST7735R panel.
CANDIDATES: list[dict] = [
    {
        "name": "adafruit-160-r90",
        "cfg": {
            "interface": "spi",
            "driver": "adafruit_st7735r",
            "width": 128,
            "height": 160,
            "dc": 25,
            "rst": 24,
            "rotate": 90,
            "x_offset": 0,
            "y_offset": 0,
            "port": 0,
            "device": 0,
            "bus_speed_hz": 500_000,
            "swap_rb": False,
        },
    },
    {
        "name": "adafruit-160-r90-swap",
        "cfg": {
            "interface": "spi",
            "driver": "adafruit_st7735r",
            "width": 128,
            "height": 160,
            "dc": 25,
            "rst": 24,
            "rotate": 90,
            "x_offset": 0,
            "y_offset": 0,
            "port": 0,
            "device": 0,
            "bus_speed_hz": 500_000,
            "swap_rb": True,
        },
    },
    {
        "name": "luma-128",
        "cfg": {
            "interface": "spi",
            "driver": "st7735",
            "width": 128,
            "height": 128,
            "dc": 25,
            "rst": 24,
            "rotate": 0,
            "bgr": False,
            "h_offset": 0,
            "v_offset": 0,
            "port": 0,
            "device": 0,
            "bus_speed_hz": 500_000,
        },
    },
    {
        "name": "luma-128-bgr",
        "cfg": {
            "interface": "spi",
            "driver": "st7735",
            "width": 128,
            "height": 128,
            "dc": 25,
            "rst": 24,
            "rotate": 0,
            "bgr": True,
            "h_offset": 2,
            "v_offset": 1,
            "port": 0,
            "device": 0,
            "bus_speed_hz": 500_000,
        },
    },
]


def _frame(w: int, h: int, label: str, i: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(0, 0, 0))
    d.text((8, 10), "UPRIGHT", fill=(0, 0, 0))
    d.text((8, 28), label, fill=(0, 0, 0))
    d.text((8, 46), "BLACK ON WHITE", fill=(0, 0, 0))
    d.text((8, 64), f"FRAME {i:03d}", fill=(0, 0, 0))
    return img


def _try_cfg(name: str, cfg: dict, hold_s: float = 8.0) -> bool:
    print(f"\n=== {name} ===", flush=True)
    try:
        dev = _open_spi(cfg)
    except Exception as exc:
        print(f"  OPEN FAIL: {exc}", flush=True)
        return False
    w, h = int(cfg["width"]), int(cfg["height"])
    try:
        n = max(1, int(hold_s / 0.15))
        for i in range(n):
            dev.display(_frame(w, h, name, i))
            time.sleep(0.15)
        print("  OK", flush=True)
        return True
    except Exception as exc:
        print(f"  RENDER FAIL: {exc}", flush=True)
        return False
    finally:
        _close_device(dev)


def main() -> int:
    print("Display recovery — stop upright/upright-web first\n", flush=True)
    picked: dict | None = None
    for entry in CANDIDATES:
        if _try_cfg(entry["name"], entry["cfg"], hold_s=10.0):
            picked = entry["cfg"]
            # First successful candidate is usually best; hold extra for user check.
            _save_config(picked)
            print(f"Saved -> {DISPLAY_CONFIG_PATH}", flush=True)
            dev = _open_spi(picked)
            try:
                w, h = int(picked["width"]), int(picked["height"])
                img = _frame(w, h, entry["name"], 999)
                for _ in range(80):
                    dev.display(img)
                    time.sleep(0.15)
            finally:
                _close_device(dev)
            break

    if not picked:
        print("\nNo config rendered.", flush=True)
        return 1
    print("\nRecovery config saved. Restart: sudo systemctl restart upright upright-web", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

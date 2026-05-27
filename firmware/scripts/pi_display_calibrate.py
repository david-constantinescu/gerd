#!/usr/bin/env python3
"""Calibrate ST7735 wiring by showing solid full-screen colors.

Run on the Pi with the app stopped:

    sudo systemctl stop upright upright-web
    cd ~/upright/firmware
    PYTHONPATH=src python3 scripts/pi_display_calibrate.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image

from upright.hal.display import DISPLAY_CONFIG_PATH, _SPI_CANDIDATES, _close_device, _open_spi, _save_config

# Solid fills only — easiest way to tell good init from noise.
_TESTS = [
    {"name": "black", "fill": (0, 0, 0)},
    {"name": "red", "fill": (220, 0, 0)},
    {"name": "green", "fill": (0, 220, 0)},
    {"name": "blue", "fill": (0, 0, 220)},
    {"name": "white", "fill": (255, 255, 255)},
]


def _show_solid(cfg: dict, label: str, fill: tuple[int, int, int], seconds: float = 2.0) -> bool:
    w, h = int(cfg["width"]), int(cfg["height"])
    try:
        dev = _open_spi(cfg)
    except Exception as exc:
        print(f"  FAIL {label}: {exc}")
        return False
    img = Image.new("RGB", (w, h), fill)
    try:
        for _ in range(int(seconds * 2)):
            dev.display(img)
            time.sleep(0.5)
        print(f"  PASS {label}")
        return True
    except Exception as exc:
        print(f"  FAIL {label}: {exc}")
        return False
    finally:
        _close_device(dev)


def main() -> int:
    print("Display calibration (app must be stopped)\n")
    best: dict | None = None
    best_score = -1

    for idx, base in enumerate(_SPI_CANDIDATES):
        cfg = {"interface": "spi", **base}
        print(f"\nConfig {idx}: dc={cfg['dc']} rst={cfg.get('rst')} "
              f"{cfg['width']}x{cfg['height']} bgr={cfg.get('bgr')} "
              f"off=({cfg.get('h_offset',0)},{cfg.get('v_offset',0)}) "
              f"speed={cfg.get('bus_speed_hz')}")

        score = 0
        for t in _TESTS:
            if _show_solid(cfg, f"{idx}-{t['name']}", t["fill"], seconds=2.0):
                score += 1

        print(f"  score={score}/{len(_TESTS)}")
        if score > best_score:
            best_score = score
            best = cfg

    if best is None:
        print("\nNo working config found.")
        return 1

    _save_config(best)
    print(f"\nSaved working config to {DISPLAY_CONFIG_PATH}")
    print(json.dumps(best, indent=2))

    # Hold winner with text for visual confirmation.
    dev = _open_spi(best)
    w, h = int(best["width"]), int(best["height"])
    img = Image.new("RGB", (w, h), (20, 30, 60))
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(255, 255, 255))
    d.text((8, 8), "DISPLAY OK", fill=(255, 255, 0))
    d.text((8, 28), "NOISE FIXED", fill=(180, 255, 180))
    for _ in range(20):
        dev.display(img)
        time.sleep(0.5)
    _close_device(dev)
    print("Holding OK screen for 10s...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

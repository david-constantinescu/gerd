#!/usr/bin/env python3
"""Timed display walkthrough for white-screen debugging.

Cycles multiple ST7735 configs and draws a distinct color/text frame.
Watch the panel while this runs, then keep the best config in display.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from PIL import Image, ImageDraw

from upright.hal.display import DISPLAY_CONFIG_PATH, _SPI_CANDIDATES, _open_spi, _save_config


def _draw_frame(cfg: dict, idx: int):
    w, h = int(cfg["width"]), int(cfg["height"])
    color = [(180, 0, 0), (0, 140, 0), (0, 0, 180), (120, 60, 0), (80, 0, 120)][idx % 5]
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(255, 255, 255))
    d.text((4, 4), f"CFG {idx}", fill=(255, 255, 0))
    d.text((4, 20), f"d{cfg.get('device',0)} dc{cfg['dc']} r{cfg.get('rst',-1)}", fill=(255, 255, 255))
    d.text((4, 36), f"{cfg['width']}x{cfg['height']} rot{cfg.get('rotate',0)}", fill=(255, 255, 255))
    return img


def main() -> int:
    print("Walking display configs...")
    for idx, base in enumerate(_SPI_CANDIDATES):
        cfg = {"interface": "spi", **base}
        print(f"TRY {idx}: {json.dumps(cfg)}", flush=True)
        try:
            dev = _open_spi(cfg)
            img = _draw_frame(cfg, idx)
            for _ in range(18):  # ~9s per config
                dev.display(img)
                time.sleep(0.5)
            try:
                dev.cleanup()
            except Exception:
                pass
        except Exception as e:
            print(f"FAIL {idx}: {e}", flush=True)
            continue

    # Keep safest baseline if user didn't pick one manually.
    fallback = {"interface": "spi", **_SPI_CANDIDATES[0]}
    _save_config(fallback)
    print(f"DONE. Fallback saved: {DISPLAY_CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


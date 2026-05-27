#!/usr/bin/env python3
"""Draw 'UPRIGHT' on the detected display (OLED, SPI TFT, or fbtft framebuffer)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import ImageDraw

from upright.hal.display import Display


def main() -> int:
    disp = Display(autoprobe=True)
    if disp._device is None:
        print("no display backend available", file=sys.stderr)
        return 1
    img = disp.new_frame()
    d = ImageDraw.Draw(img)
    if img.mode == "RGB":
        d.rectangle((0, 0, disp.width - 1, disp.height - 1), outline=(255, 255, 255))
        d.text((12, 90), "UPRIGHT", fill=(0, 255, 0))
        d.text((12, 120), "DISPLAY OK", fill=(255, 255, 255))
    else:
        d.rectangle((0, 0, disp.width - 1, disp.height - 1), outline=1)
        d.text((6, 22), "UPRIGHT", fill=1)
        d.text((6, 44), "DISPLAY OK", fill=1)
    disp.show(img)
    print(f"frame sent ({disp.width}x{disp.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

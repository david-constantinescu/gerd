#!/usr/bin/env python3
"""Capture one frame from the OV9712 USB camera and preview it on the OLED."""

from PIL import ImageOps

from sentinel.hal.camera import capture_with_warmup
from sentinel.hal.oled import OLED


def main() -> int:
    img = capture_with_warmup()
    if img is None:
        print("capture failed — is fswebcam installed?")
        return 1
    print(f"captured {img.size} image")
    oled = OLED()
    preview = ImageOps.fit(img, (oled.width, oled.height)).convert("1")
    oled.show(preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

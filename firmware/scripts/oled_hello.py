#!/usr/bin/env python3
"""Draw 'REFLUX SENTINEL' on the OLED to confirm wiring."""

from PIL import ImageDraw

from sentinel.hal.oled import OLED


def main() -> int:
    oled = OLED()
    img = oled.new_frame()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, oled.width - 1, oled.height - 1), outline=1)
    d.text((6, 8), "REFLUX", fill=1)
    d.text((6, 22), "SENTINEL", fill=1)
    d.text((6, 44), "OLED OK", fill=1)
    oled.show(img)
    print("frame sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

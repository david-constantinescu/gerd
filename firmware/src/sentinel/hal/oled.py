"""1.3" SSD1306/SH1106 OLED wrapper.

We avoid pulling ``luma.oled`` at import-time so the package stays
mac-importable. Renderers in ``modes.ui`` build a PIL ``Image`` and pass it
through ``OLED.show``.
"""

from __future__ import annotations

import logging
import time

from ..config import I2C_ADDR_OLED, OLED_AUTO_BLANK_SECONDS, OLED_HEIGHT, OLED_WIDTH

log = logging.getLogger("hal.oled")


class OLED:
    def __init__(self, *, dry_run: bool = False) -> None:
        self.width = OLED_WIDTH
        self.height = OLED_HEIGHT
        self._device = None
        self._dry_run = dry_run
        self._last_show = 0.0
        self._blanked = False
        if not dry_run:
            try:
                from luma.core.interface.serial import i2c  # type: ignore[import-not-found]
                from luma.oled.device import sh1106  # type: ignore[import-not-found]

                serial = i2c(port=1, address=I2C_ADDR_OLED)
                self._device = sh1106(serial, width=self.width, height=self.height)
                log.info("OLED initialised on i2c@0x%02x", I2C_ADDR_OLED)
            except Exception as e:
                log.error("OLED init failed (%s) — running headless", e)

    def new_frame(self):
        from PIL import Image

        return Image.new("1", (self.width, self.height), 0)

    def show(self, image) -> None:
        self._last_show = time.time()
        self._blanked = False
        if self._device is not None:
            self._device.display(image)
        elif self._dry_run:
            # Cheap ASCII preview when running on Mac.
            log.debug("OLED frame (dry-run) %dx%d", self.width, self.height)

    def auto_blank_tick(self) -> None:
        if self._blanked or self._device is None:
            return
        if time.time() - self._last_show > OLED_AUTO_BLANK_SECONDS:
            try:
                self._device.clear()
            except Exception:
                pass
            self._blanked = True

    def clear(self) -> None:
        if self._device is not None:
            self._device.clear()
        self._blanked = True

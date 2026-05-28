"""Display backend — auto-detect I²C OLED or SPI TFT and render PIL frames."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from ..config import (
    DATA_DIR,
    I2C_ADDR_OLED,
    OLED_HEIGHT,
    OLED_WIDTH,
    TUNABLES,
    SPI_DISPLAY_BL,
    SPI_DISPLAY_DC,
    SPI_DISPLAY_DEVICE,
    SPI_DISPLAY_HEIGHT,
    SPI_DISPLAY_H_OFFSET,
    SPI_DISPLAY_PORT,
    SPI_DISPLAY_RST,
    SPI_DISPLAY_V_OFFSET,
    SPI_DISPLAY_WIDTH,
)

log = logging.getLogger("hal.display")

_DISPLAY_LOCK = threading.Lock()

DISPLAY_CONFIG_PATH = DATA_DIR / "display.json"

# Userspace SPI (no fbtft overlay). Prefer slow, correct pin order first — fast/wrong
# init looks like random noise on the panel.
_SPI_CANDIDATES: list[dict[str, Any]] = [
    {
        "driver": "st7735",
        "width": 128,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 0,
        "bgr": False,
        "h_offset": 0,
        "v_offset": 0,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 500_000,
    },
    {
        "driver": "st7735",
        "width": 128,
        "height": 128,
        "dc": 25,
        "rst": 24,
        "rotate": 0,
        "bgr": False,
        "h_offset": 0,
        "v_offset": 0,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 500_000,
    },
    {
        "driver": "st7735",
        "width": 128,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 0,
        "bgr": True,
        "h_offset": 2,
        "v_offset": 1,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 500_000,
    },
    {
        "driver": "st7735",
        "width": SPI_DISPLAY_WIDTH,
        "height": SPI_DISPLAY_HEIGHT,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 0,
        "bgr": False,
        "h_offset": 0,
        "v_offset": 0,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 1_000_000,
    },
    {
        "driver": "st7735",
        "width": 160,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 1,
        "bgr": True,
        "h_offset": 0,
        "v_offset": 0,
        "port": 0,
        "device": 0,
        "bus_speed_hz": 1_000_000,
    },
    {
        "driver": "st7735",
        "width": 160,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": -1,  # reset hard-wired on some breakouts
        "rotate": 1,
        "bgr": True,
        "h_offset": 0,
        "v_offset": 0,
        "port": 0,
        "device": 0,
        "bus_speed_hz": 1_000_000,
    },
    {
        "driver": "st7735",
        "width": 128,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": -1,
        "rotate": 0,
        "bgr": False,
        "h_offset": 0,
        "v_offset": 0,
        "port": 0,
        "device": 0,
        "bus_speed_hz": 1_000_000,
    },
    {
        "driver": "st7735",
        "width": 128,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 0,
        "bgr": False,
        "h_offset": 0,
        "v_offset": 0,
        "port": 0,
        "device": 1,  # CE1
        "bus_speed_hz": 1_000_000,
    },
    {
        "driver": "st7735",
        "width": 160,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": -1,
        "rotate": 1,
        "bgr": True,
        "h_offset": 0,
        "v_offset": 0,
        "port": 0,
        "device": 1,
        "bus_speed_hz": 1_000_000,
    },
    {
        "driver": "st7735",
        "width": 128,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 0,
        "bgr": True,
        "h_offset": 2,
        "v_offset": 1,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 2_000_000,
    },
    {
        "driver": "st7735",
        "width": 160,
        "height": 128,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 1,
        "bgr": True,
        "h_offset": 0,
        "v_offset": 0,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 2_000_000,
    },
    # Adafruit/Blinka last — it can disturb lgpio inputs; buttons are reclaimed after init.
    {
        "driver": "adafruit_st7735r",
        "width": 128,
        "height": 160,
        "dc": SPI_DISPLAY_DC,
        "rst": SPI_DISPLAY_RST,
        "rotate": 90,
        "x_offset": 0,
        "y_offset": 0,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 2_000_000,
    },
    {
        "driver": "adafruit_st7735r",
        "width": 128,
        "height": 160,
        "dc": SPI_DISPLAY_DC,
        "rst": -1,
        "rotate": 90,
        "x_offset": 0,
        "y_offset": 0,
        "port": SPI_DISPLAY_PORT,
        "device": SPI_DISPLAY_DEVICE,
        "bus_speed_hz": 1_000_000,
    },
]

_I2C_CANDIDATES: list[dict[str, Any]] = [
    {"driver": "sh1106", "bus": 1, "address": 0x3C, "width": 128, "height": 64},
    {"driver": "sh1106", "bus": 1, "address": 0x3D, "width": 128, "height": 64},
    {"driver": "ssd1306", "bus": 1, "address": 0x3C, "width": 128, "height": 64},
    {"driver": "ssd1306", "bus": 1, "address": 0x3D, "width": 128, "height": 64},
    {"driver": "sh1106", "bus": 2, "address": 0x3C, "width": 128, "height": 64},
]


def _load_saved_config() -> dict[str, Any] | None:
    if not DISPLAY_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(DISPLAY_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _save_config(cfg: dict[str, Any]) -> None:
    DISPLAY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DISPLAY_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _open_spi(cfg: dict[str, Any]) -> Any:
    if cfg.get("driver") == "adafruit_st7735r":
        return _open_spi_adafruit(cfg)

    from luma.core.interface.serial import spi  # type: ignore[import-not-found]
    from luma.lcd.device import ili9341, st7735, st7789  # type: ignore[import-not-found]

    spi_kwargs: dict[str, Any] = {
        "port": int(cfg.get("port", 0)),
        "device": int(cfg.get("device", 0)),
        "gpio_DC": int(cfg["dc"]),
        "bus_speed_hz": int(cfg.get("bus_speed_hz", 1_000_000)),
    }
    rst = int(cfg.get("rst", -1))
    if rst >= 0:
        spi_kwargs["gpio_RST"] = rst
    serial = spi(**spi_kwargs)
    driver = cfg["driver"]
    w, h = int(cfg["width"]), int(cfg["height"])
    rotate = int(cfg.get("rotate", 0))
    bgr = bool(cfg.get("bgr", False))
    if driver == "st7789":
        return st7789(serial, width=w, height=h, rotate=rotate)
    if driver == "ili9341":
        return ili9341(serial, width=w, height=h, rotate=rotate)
    if driver == "st7735":
        from luma.core.framebuffer import full_frame  # type: ignore[import-not-found]

        return st7735(
            serial,
            width=w,
            height=h,
            rotate=rotate,
            bgr=bgr,
            h_offset=int(cfg.get("h_offset", 0)),
            v_offset=int(cfg.get("v_offset", 0)),
            framebuffer=full_frame(),
        )
    raise ValueError(f"unknown spi driver {driver}")


class _AdafruitST7735:
    def __init__(self, cfg: dict[str, Any]) -> None:
        import board  # type: ignore[import-not-found]
        import digitalio  # type: ignore[import-not-found]
        from adafruit_rgb_display import st7735 as adafruit_st7735  # type: ignore[import-not-found]

        def _pin(bcm: int):
            attr = f"D{bcm}"
            if not hasattr(board, attr):
                raise ValueError(f"board pin {attr} not available")
            return getattr(board, attr)

        # UI framebuffer size (landscape) vs physical panel size (portrait 128x160).
        self.width = int(cfg["width"])
        self.height = int(cfg["height"])
        panel_w = int(cfg.get("panel_width", 128))
        panel_h = int(cfg.get("panel_height", 160))
        rot = int(cfg.get("rotate", 90))

        spi = board.SPI()
        cs_name = "CE0" if int(cfg.get("device", 0)) == 0 else "CE1"
        cs = digitalio.DigitalInOut(getattr(board, cs_name))
        dc = digitalio.DigitalInOut(_pin(int(cfg["dc"])))
        rst_val = int(cfg.get("rst", -1))
        rst = digitalio.DigitalInOut(_pin(rst_val)) if rst_val >= 0 else None

        self._swap_rb = bool(cfg.get("swap_rb", False))
        self._disp = adafruit_st7735.ST7735R(
            spi,
            cs=cs,
            dc=dc,
            rst=rst,
            baudrate=int(cfg.get("bus_speed_hz", 2_000_000)),
            width=panel_w,
            height=panel_h,
            rotation=rot,
            x_offset=int(cfg.get("x_offset", 0)),
            y_offset=int(cfg.get("y_offset", 0)),
        )

    def display(self, image) -> None:
        from PIL import Image

        target = image.convert("RGB")
        if target.size != (self.width, self.height):
            target = target.resize((self.width, self.height), Image.NEAREST)
        if self._swap_rb:
            r, g, b = target.split()
            target = Image.merge("RGB", (b, g, r))
        self._disp.image(target)

    def clear(self) -> None:
        from PIL import Image

        self.display(Image.new("RGB", (self.width, self.height), (0, 0, 0)))


def _open_spi_adafruit(cfg: dict[str, Any]) -> Any:
    return _AdafruitST7735(cfg)


def _open_i2c(cfg: dict[str, Any]) -> Any:
    from luma.core.interface.serial import i2c  # type: ignore[import-not-found]
    from luma.oled.device import ssd1306  # type: ignore[import-not-found]
    from luma.oled.device import sh1106  # type: ignore[import-not-found]

    serial = i2c(port=int(cfg["bus"]), address=int(cfg["address"]))
    w, h = int(cfg["width"]), int(cfg["height"])
    if cfg["driver"] == "ssd1306":
        return ssd1306(serial, width=w, height=h)
    return sh1106(serial, width=w, height=h)


def _open_framebuffer(cfg: dict[str, Any]) -> "_FbWriter":
    return _FbWriter(int(cfg.get("device", 0)))


class _FbWriter:
    """Write RGB565 frames to a Linux framebuffer (fbtft panels)."""

    def __init__(self, fb_num: int = 0) -> None:
        from PIL import Image

        path = Path(f"/dev/fb{fb_num}")
        if not path.exists():
            raise FileNotFoundError(path)
        import subprocess

        w, h = 240, 240
        try:
            out = subprocess.check_output(["fbset", "-fb", str(path)], text=True)
            for line in out.splitlines():
                if line.strip().startswith("geometry"):
                    parts = line.split()
                    w, h = int(parts[1]), int(parts[2])
        except Exception:
            pass
        self.width = w
        self.height = h
        self._path = path
        self._clear_img = Image.new("RGB", (w, h), (0, 0, 0))

    @staticmethod
    def _rgb565_bytes(img) -> bytes:
        buf = bytearray(img.size[0] * img.size[1] * 2)
        i = 0
        for r, g, b in img.getdata():
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf[i] = v & 0xFF
            buf[i + 1] = (v >> 8) & 0xFF
            i += 2
        return bytes(buf)

    def display(self, image) -> None:
        from PIL import Image

        img = image.convert("RGB").resize((self.width, self.height))
        with self._path.open("wb") as f:
            f.write(self._rgb565_bytes(img))

    def clear(self) -> None:
        self.display(self._clear_img)


def probe_display(*, save: bool = True) -> dict[str, Any] | None:
    """Try saved config first, then SPI (ST7735R), I²C, framebuffer last."""
    saved = _load_saved_config()
    if saved and saved.get("interface") == "spi":
        if int(saved.get("dc", -1)) != SPI_DISPLAY_DC or int(saved.get("rst", -1)) != SPI_DISPLAY_RST:
            log.warning("saved display dc/rst mismatch — reprobing")
            saved = None
    if saved:
        try:
            iface = saved.get("interface")
            if iface == "spi":
                dev = _open_spi(saved)
            elif iface == "fb":
                dev = _open_framebuffer(saved)
            else:
                dev = _open_i2c(saved)
            _test_device(dev, saved)
            _close_device(dev)
            return saved
        except Exception as e:
            log.warning("saved display config failed (%s) — reprobing", e)

    for cfg in _SPI_CANDIDATES:
        full = {"interface": "spi", **cfg}
        try:
            dev = _open_spi(full)
            _test_device(dev, full)
            _close_device(dev)
            log.info(
                "display probe OK: spi %s %dx%d dc=%s rst=%s bgr=%s",
                cfg["driver"],
                cfg["width"],
                cfg["height"],
                cfg["dc"],
                cfg["rst"],
                cfg.get("bgr", False),
            )
            if save:
                _save_config(full)
            return full
        except Exception:
            continue

    for cfg in _I2C_CANDIDATES:
        full = {"interface": "i2c", **cfg}
        try:
            dev = _open_i2c(full)
            _test_device(dev, full)
            _close_device(dev)
            log.info("display probe OK: i2c %s @ 0x%02x", cfg["driver"], cfg["address"])
            if save:
                _save_config(full)
            return full
        except Exception:
            continue

    for fb in (0, 1):
        if Path(f"/dev/fb{fb}").exists():
            cfg = {"interface": "fb", "device": fb, "width": 240, "height": 240}
            try:
                dev = _open_framebuffer(cfg)
                _test_device(dev, cfg)
                _close_device(dev)
                log.info("display probe OK: framebuffer /dev/fb%d", fb)
                if save:
                    _save_config(cfg)
                return cfg
            except Exception:
                pass

    return None


def _close_device(device: Any) -> None:
    """Release SPI/GPIO handles after probe (only one client may own the bus)."""
    try:
        if hasattr(device, "cleanup"):
            device.cleanup()
    except Exception:
        pass
    try:
        iface = getattr(device, "_interface", None) or getattr(device, "interface", None)
        if iface is not None and hasattr(iface, "cleanup"):
            iface.cleanup()
    except Exception:
        pass
    try:
        if hasattr(device, "_disp") and hasattr(device._disp, "cleanup"):
            device._disp.cleanup()
    except Exception:
        pass


def _test_device(device: Any, cfg: dict[str, Any]) -> None:
    from PIL import Image, ImageDraw

    w, h = int(cfg["width"]), int(cfg["height"])
    mode = "RGB" if cfg.get("interface") in ("spi", "fb") else "1"
    img = Image.new(mode, (w, h), (0, 255, 0) if mode == "RGB" else 0)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(255, 255, 255) if mode == "RGB" else 255)
    d.text((4, 4), "UPRIGHT", fill=(0, 0, 0) if mode == "RGB" else 255)
    device.display(img)
    time.sleep(0.15)


class Display:
    """Unified display API used by the FSM (replaces OLED-only path)."""

    def __init__(self, *, dry_run: bool = False, autoprobe: bool = True) -> None:
        self._device = None
        self._cfg: dict[str, Any] | None = None
        self._dry_run = dry_run
        self._last_activity = time.time()
        self._last_show = 0.0
        self._blanked = False
        self.width = OLED_WIDTH
        self.height = OLED_HEIGHT

        if dry_run:
            return

        if autoprobe and not _load_saved_config():
            self._cfg = probe_display(save=True)
        else:
            self._cfg = _load_saved_config()
            if self._cfg is None and autoprobe:
                self._cfg = probe_display(save=True)

        if self._cfg:
            try:
                iface = self._cfg.get("interface")
                if iface == "spi":
                    self._force_backlight()
                    self._device = _open_spi(self._cfg)
                elif iface == "fb":
                    self._device = _open_framebuffer(self._cfg)
                else:
                    self._device = _open_i2c(self._cfg)
                self.width = int(getattr(self._device, "width", self._cfg["width"]))
                self.height = int(getattr(self._device, "height", self._cfg["height"]))
                log.info(
                    "display: %s %dx%d (%s) rotate=%s",
                    self._cfg.get("driver"),
                    self.width,
                    self.height,
                    self._cfg.get("interface"),
                    self._cfg.get("rotate", 0),
                )
            except Exception as e:
                log.error("display init failed (%s)", e)
                self._device = None
        else:
            log.error("no display found — running headless")

    def _force_backlight(self) -> None:
        """Best-effort TFT backlight enable (no-op if BL pin not wired)."""
        if SPI_DISPLAY_BL < 0:
            return
        try:
            from .gpio_lgpio import claim_output, write

            claim_output(SPI_DISPLAY_BL, initial=1)
            write(SPI_DISPLAY_BL, 1)
            log.info("display backlight forced on via GPIO %s", SPI_DISPLAY_BL)
        except Exception as e:
            log.debug("display backlight pin unavailable: %s", e)

    @property
    def color(self) -> bool:
        """True when the panel expects RGB frames (SPI TFT or fbtft framebuffer)."""
        return bool(
            self._cfg and self._cfg.get("interface") in ("spi", "fb")
        )

    def new_frame(self):
        from PIL import Image

        if self.color:
            return Image.new("RGB", (self.width, self.height), (0, 0, 0))
        return Image.new("1", (self.width, self.height), 0)

    def note_activity(self) -> None:
        """Reset display sleep timer (button press, menu use, etc.)."""
        self._last_activity = time.time()

    def wake(self) -> bool:
        """Mark panel awake after blanking; caller should repaint."""
        self.note_activity()
        if not self._blanked:
            return False
        self._blanked = False
        return True

    def _blank_timeout_s(self) -> float:
        minutes = float(getattr(TUNABLES, "display_blank_minutes", 0) or 0)
        if minutes <= 0:
            return 0.0
        return minutes * 60.0

    def show(self, image) -> None:
        if self._device is None:
            if self._dry_run:
                log.debug("display frame (dry-run) %dx%d", self.width, self.height)
            return
        self.note_activity()
        out = image
        if self.color and image.mode != "RGB":
            out = image.convert("RGB")
        if image.size != (self.width, self.height):
            from PIL import Image

            out = image.resize((self.width, self.height))
        self._last_show = time.time()
        self._blanked = False
        with _DISPLAY_LOCK:
            self._device.display(out)

    def auto_blank_tick(self) -> None:
        timeout = self._blank_timeout_s()
        if timeout <= 0 or self._blanked or self._device is None:
            return
        if time.time() - self._last_activity > timeout:
            try:
                self._device.clear()
            except Exception:
                pass
            self._blanked = True
            log.debug("display blanked after %.0fs idle", timeout)

    @property
    def is_blanked(self) -> bool:
        return self._blanked

    def clear(self) -> None:
        if self._device is not None:
            self._device.clear()
        self._blanked = True


# Backwards compatibility
OLED = Display

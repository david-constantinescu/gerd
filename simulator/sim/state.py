"""Shared in-memory state for the virtual device.

A single :class:`SimDevice` instance is the bridge between the browser bench /
HTTP API (which write inputs and read outputs) and the simulated HAL threads
(which read the inputs and produce firmware events + display frames). All access
is thread-safe — the firmware runs in its own threads while Flask serves
requests concurrently.
"""

from __future__ import annotations

import collections
import io
import math
import queue
import threading
import time
from typing import Any

from PIL import Image, ImageDraw

# The real Pi panel: 160x128 RGB SPI TFT (ST7735R) — see data/display.default.json.
PANEL_W = 160
PANEL_H = 128


class SimDevice:
    """Holds every input the UI can set and every output the firmware produces."""

    def __init__(self) -> None:
        self.start_time = time.time()

        # --- inputs consumed by simulated HAL threads -----------------------
        # Each item: (button, pattern) e.g. ("a", "single").
        self.button_q: queue.Queue[tuple[str, str]] = queue.Queue()
        # Each item: "cw" | "ccw" | "click".
        self.encoder_q: queue.Queue[str] = queue.Queue()

        # Sensor values polled by the simulated IMU / power threads.
        self.pitch = 4.0          # forward lean, degrees (0 = perfectly upright)
        self.roll = 0.0           # sideways lean, degrees
        self.imu_hz = 5.0         # updated by patched imu.set_rate()
        self.battery_pct = 87
        self.battery_low = False

        # --- display output -------------------------------------------------
        self._frame: Image.Image | None = None
        self._frame_jpeg: bytes | None = None
        self.frame_count = 0
        self._frame_cv = threading.Condition()

        # --- actuators / logs (outputs surfaced in the UI) ------------------
        self.motor_events: collections.deque[dict[str, Any]] = collections.deque(maxlen=24)
        self.audio_events: collections.deque[dict[str, Any]] = collections.deque(maxlen=24)
        self.log_lines: collections.deque[str] = collections.deque(maxlen=500)

        # --- camera (frames pushed from the browser webcam) -----------------
        self._camera_img: Image.Image | None = None
        self._camera_ts = 0.0
        self._camera_lock = threading.Lock()

        # --- live references, populated once the firmware boots --------------
        self.manager: Any = None          # upright.modes.manager.ModeManager
        self.bus: Any = None              # upright.events.EventBus
        self.booted = threading.Event()

    # ----------------------------------------------------------------- inputs
    def press(self, button: str, pattern: str = "single") -> None:
        button = "a" if button.lower() in ("a", "up", "top") else "b"
        if pattern not in ("single", "double", "triple"):
            pattern = "single"
        self.button_q.put((button, pattern))

    def encoder(self, action: str) -> None:
        if action in ("cw", "ccw", "click"):
            self.encoder_q.put(action)

    def set_posture(self, pitch: float | None = None, roll: float | None = None) -> None:
        if pitch is not None:
            self.pitch = max(-45.0, min(120.0, float(pitch)))
        if roll is not None:
            self.roll = max(-90.0, min(90.0, float(roll)))

    def accel(self) -> tuple[float, float, float]:
        """Synthesize a gravity vector matching the current pitch/roll."""
        p = math.radians(self.pitch)
        r = math.radians(self.roll)
        ax = math.sin(p)
        ay = math.sin(r)
        az = max(0.05, math.cos(p) * math.cos(r))
        return ax, ay, az

    def set_battery(self, pct: int | None = None, low: bool | None = None) -> None:
        if pct is not None:
            self.battery_pct = max(0, min(100, int(pct)))
        if low is not None:
            self.battery_low = bool(low)

    # ----------------------------------------------------------------- camera
    def set_camera_frame(self, img: Image.Image) -> None:
        with self._camera_lock:
            self._camera_img = img.convert("RGB")
            self._camera_ts = time.time()

    def camera_active(self) -> bool:
        # Bench users often upload a still, then navigate the menu before capture.
        return time.time() - self._camera_ts < 60.0

    def get_camera_frame(self, width: int, height: int) -> Image.Image:
        """Return the latest webcam frame, or a synthetic placeholder."""
        with self._camera_lock:
            img = self._camera_img
        if img is None:
            img = self._placeholder_camera()
        img = img.convert("RGB")
        iw, ih = img.size
        # Center-crop to aspect (like a real UVC frame); letterbox bars confused TFLite.
        scale = max(width / iw, height / ih)
        tw = max(1, int(iw * scale))
        th = max(1, int(ih * scale))
        resized = img.resize((tw, th), Image.Resampling.LANCZOS)
        left = max(0, (tw - width) // 2)
        top = max(0, (th - height) // 2)
        return resized.crop((left, top, left + width, top + height))

    @staticmethod
    def _placeholder_camera() -> Image.Image:
        img = Image.new("RGB", (320, 240), (24, 28, 34))
        d = ImageDraw.Draw(img)
        for y in range(0, 240, 12):
            shade = 30 + (y % 48)
            d.line((0, y, 320, y), fill=(shade, shade, shade + 6))
        d.text((96, 110), "SIM CAMERA", fill=(150, 200, 255))
        d.text((78, 126), "(enable webcam)", fill=(120, 130, 150))
        return img

    # ---------------------------------------------------------------- display
    def set_frame(self, img: Image.Image) -> None:
        rgb = img.convert("RGB") if img.mode != "RGB" else img.copy()
        with self._frame_cv:
            self._frame = rgb
            self._frame_jpeg = None
            self.frame_count += 1
            self._frame_cv.notify_all()

    def frame_png(self, scale: int = 1) -> bytes | None:
        with self._frame_cv:
            img = self._frame
        if img is None:
            return None
        if scale > 1:
            img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def frame_jpeg(self) -> bytes | None:
        with self._frame_cv:
            if self._frame is None:
                return None
            if self._frame_jpeg is None:
                up = self._frame.resize(
                    (self._frame.width * 3, self._frame.height * 3), Image.NEAREST
                )
                buf = io.BytesIO()
                up.save(buf, "JPEG", quality=85)
                self._frame_jpeg = buf.getvalue()
            return self._frame_jpeg

    def wait_frame(self, last_count: int, timeout: float = 1.0) -> int:
        with self._frame_cv:
            if self.frame_count == last_count:
                self._frame_cv.wait(timeout)
            return self.frame_count

    # -------------------------------------------------------------- actuators
    def add_motor_event(self, pattern: str) -> None:
        self.motor_events.appendleft({"pattern": pattern, "ts": time.time()})

    def add_audio_event(self, name: str) -> None:
        self.audio_events.appendleft({"name": name, "ts": time.time()})

    def add_log(self, line: str) -> None:
        self.log_lines.appendleft(line)

    # ------------------------------------------------------------------ state
    def snapshot(self) -> dict[str, Any]:
        """The JSON blob returned by GET /api/state."""
        fsm: dict[str, Any] = {}
        m = self.manager
        if m is not None:
            try:
                fsm = {
                    "state": m.ctx.state.value,
                    "menu_open": bool(m.menu.open),
                    "menu_screen": m.menu.screen,
                    "menu_index": m.menu.index,
                    "battery_pct": getattr(m.ctx, "battery_pct", None),
                    "ctx_pitch": round(getattr(m.ctx, "pitch", 0.0), 1),
                    "ctx_roll": round(getattr(m.ctx, "roll", 0.0), 1),
                    "food_result": dict(getattr(m.ctx, "food_result", None) or {}),
                    "net_mode": (getattr(m, "_net_info", None) or {}).get("mode"),
                }
            except Exception:
                pass
        return {
            "booted": self.booted.is_set(),
            "uptime_s": round(time.time() - self.start_time, 1),
            "frame_count": self.frame_count,
            "fsm": fsm,
            "wifi": {
                "mode": getattr(self, "wifi_mode", "offline"),
                "client_ssid": getattr(self, "wifi_client_ssid", None),
                "client_ip": getattr(self, "wifi_client_ip", None),
            },
            "inputs": {
                "pitch": round(self.pitch, 1),
                "roll": round(self.roll, 1),
                "battery_pct": self.battery_pct,
                "battery_low": self.battery_low,
                "imu_hz": self.imu_hz,
            },
            "camera_active": self.camera_active(),
            "motor": list(self.motor_events)[:8],
            "audio": list(self.audio_events)[:8],
            "log": list(self.log_lines)[:40],
        }

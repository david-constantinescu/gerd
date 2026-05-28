"""OV9712 USB UVC camera. Powered off until needed.

We capture frames to ``/tmp/upright_frame.jpg`` via ``fswebcam`` or ``v4l2-ctl``
(opencv if installed for live preview). Returns a PIL ``Image`` for display and
TFLite preprocessing.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PILImage

log = logging.getLogger("hal.camera")

_TMP_PATH = Path("/tmp/upright_frame.jpg")
_DEFAULT_DEVICE = "/dev/video0"
_PREVIEW_INTERVAL_S = 0.35


def orient_frame(img: PILImage.Image) -> PILImage.Image:
    """Apply user-facing orientation (USB cams on the band are mounted upside-down)."""
    from ..config import TUNABLES

    if getattr(TUNABLES, "camera_rotate_180", True):
        return img.rotate(180)
    return img


def _capture_v4l2(device: str, width: int, height: int) -> bool:
    """MJPEG grab via v4l2-ctl (works when fswebcam fails on some UVC cams)."""
    v4l2 = shutil.which("v4l2-ctl")
    if v4l2 is None or not Path(device).exists():
        return False
    try:
        subprocess.run(
            [
                v4l2,
                f"--device={device}",
                f"--set-fmt-video=width={width},height={height},pixelformat=MJPG",
                "--stream-mmap",
                "--stream-count=1",
                f"--stream-to={_TMP_PATH}",
            ],
            check=True,
            timeout=8.0,
            capture_output=True,
        )
        return _TMP_PATH.is_file() and _TMP_PATH.stat().st_size > 0
    except Exception as e:
        log.debug("v4l2-ctl capture failed: %s", e)
        return False


def _capture_opencv(
    device: str, width: int, height: int
) -> PILImage.Image | None:
    try:
        import cv2  # type: ignore[import-not-found]
        from PIL import Image
    except ImportError:
        return None

    if not hasattr(_capture_opencv, "_caps"):
        _capture_opencv._caps = {}  # type: ignore[attr-defined]

    caps: dict = _capture_opencv._caps  # type: ignore[attr-defined]
    cap = caps.get(device)
    if cap is None or not cap.isOpened():
        idx = 0
        if device.startswith("/dev/video"):
            try:
                idx = int(device.replace("/dev/video", ""))
            except ValueError:
                idx = 0
        cap = cv2.VideoCapture(idx)
        if width and height:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        caps[device] = cap

    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def capture(
    width: int = 640,
    height: int = 480,
    device: str = _DEFAULT_DEVICE,
    *,
    prefer_opencv: bool = False,
) -> PILImage.Image | None:
    """Grab one frame. Returns ``None`` if no camera is reachable."""
    if not Path(device).exists():
        log.warning("camera device %s missing — is the USB camera plugged in?", device)
        return None

    if prefer_opencv:
        img = _capture_opencv(device, width, height)
        if img is not None:
            return orient_frame(img)

    fswebcam = shutil.which("fswebcam")
    if fswebcam is not None:
        try:
            subprocess.run(
                [
                    fswebcam,
                    "-d",
                    device,
                    "-q",
                    "--no-banner",
                    "-r",
                    f"{width}x{height}",
                    str(_TMP_PATH),
                ],
                check=True,
                timeout=8.0,
            )
        except Exception as e:
            log.warning("fswebcam failed (%s) — trying v4l2-ctl", e)
            if not _capture_v4l2(device, width, height):
                return None
    elif not _capture_v4l2(device, width, height):
        if prefer_opencv:
            return None
        log.warning("no fswebcam or v4l2-ctl — capture skipped")
        return None

    from PIL import Image

    return orient_frame(Image.open(_TMP_PATH).convert("RGB"))


def capture_with_warmup(retries: int = 2) -> PILImage.Image | None:
    """Some UVC sensors auto-expose on the second frame. Retry once."""
    for _ in range(retries):
        img = capture()
        if img is not None:
            return img
        time.sleep(0.2)
    return None


class CameraPreview:
    """Background live viewfinder for the food-photo screen (~3 fps)."""

    def __init__(self, *, interval_s: float = _PREVIEW_INTERVAL_S) -> None:
        self._interval_s = interval_s
        self._lock = threading.Lock()
        self._frame: PILImage.Image | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="hal.camera.preview", daemon=True
        )
        self._thread.start()
        log.info("camera live preview started")

    def stop(self) -> None:
        self._stop.set()
        th = self._thread
        if th is not None:
            th.join(timeout=2.0)
        self._thread = None
        with self._lock:
            self._frame = None
        log.info("camera live preview stopped")

    def latest(self) -> PILImage.Image | None:
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def _loop(self) -> None:
        while not self._stop.is_set():
            img = capture(
                width=320,
                height=240,
                prefer_opencv=True,
            )
            if img is None:
                img = capture(width=320, height=240)
            if img is not None:
                with self._lock:
                    self._frame = img
            self._stop.wait(self._interval_s)

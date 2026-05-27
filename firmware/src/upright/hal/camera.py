"""OV9712 USB UVC camera. Powered off until needed.

We capture a single frame to ``/tmp/upright_frame.jpg`` via ``fswebcam`` (or
``opencv-python`` if installed) and return a PIL ``Image`` ready for the
TFLite preprocessor.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PILImage

log = logging.getLogger("hal.camera")

_TMP_PATH = Path("/tmp/upright_frame.jpg")
_DEFAULT_DEVICE = "/dev/video0"


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


def capture(
    width: int = 640,
    height: int = 480,
    device: str = _DEFAULT_DEVICE,
) -> PILImage.Image | None:
    """Grab one frame. Returns ``None`` if no camera is reachable."""
    if not Path(device).exists():
        log.warning("camera device %s missing — is the USB camera plugged in?", device)
        return None

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
        log.warning("no fswebcam or v4l2-ctl — capture skipped")
        return None

    from PIL import Image

    return Image.open(_TMP_PATH).convert("RGB")


def capture_with_warmup(retries: int = 2) -> PILImage.Image | None:
    """Some UVC sensors auto-expose on the second frame. Retry once."""
    for _ in range(retries):
        img = capture()
        if img is not None:
            return img
        time.sleep(0.2)
    return None

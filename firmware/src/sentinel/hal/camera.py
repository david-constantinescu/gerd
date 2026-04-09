"""OV9712 USB UVC camera. Powered off until needed.

We capture a single frame to ``/tmp/sentinel_frame.jpg`` via ``fswebcam`` (or
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

_TMP_PATH = Path("/tmp/sentinel_frame.jpg")


def capture(width: int = 640, height: int = 480) -> PILImage.Image | None:
    """Grab one frame. Returns ``None`` if no camera is reachable."""
    fswebcam = shutil.which("fswebcam")
    if fswebcam is None:
        log.warning("fswebcam not installed — capture skipped")
        return None
    try:
        subprocess.run(
            [
                fswebcam,
                "-q",
                "--no-banner",
                "-r",
                f"{width}x{height}",
                str(_TMP_PATH),
            ],
            check=True,
            timeout=5.0,
        )
    except Exception as e:
        log.error("fswebcam failed: %s", e)
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

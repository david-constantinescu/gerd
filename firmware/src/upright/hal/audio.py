"""WAV playback through MAX98357A I²S amplifier (via ``aplay``).

We pre-generate every voice line with Piper TTS at build time and ship them
under ``firmware/audio/``. This module just calls ``aplay`` — no runtime TTS,
so the Pi Zero 2 W stays cool and battery use stays predictable.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

from ..config import AUDIO_DIR

log = logging.getLogger("hal.audio")


class Audio:
    def __init__(self, *, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._aplay = shutil.which("aplay")
        if not dry_run and self._aplay is None:
            log.warning("aplay not found — voice alerts disabled")

    def play(self, name: str) -> None:
        path: Path = AUDIO_DIR / f"{name}.wav"
        if not path.exists():
            log.warning("missing wav: %s", path)
            return
        if self._dry_run or self._aplay is None:
            log.info("would play: %s", path.name)
            return
        try:
            subprocess.Popen(
                [self._aplay, "-q", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.error("aplay failed: %s", e)

    def play_async(self, name: str) -> None:
        threading.Thread(target=self.play, args=(name,), daemon=True).start()

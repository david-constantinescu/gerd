#!/usr/bin/env python3
"""Generate a 1 kHz beep + play it through the I²S amp.

Run after enabling I²S in /boot/config.txt and rebooting:
    dtparam=i2s=on
    dtoverlay=hifiberry-dac
"""

import math
import struct
import subprocess
import wave
from pathlib import Path

OUT = Path("/tmp/beep.wav")


def main() -> int:
    sample_rate = 44100
    duration = 0.5
    freq = 1000
    n = int(sample_rate * duration)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for i in range(n):
            v = int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / sample_rate))
            w.writeframes(struct.pack("<h", v))
    print(f"wrote {OUT}")
    subprocess.run(["aplay", "-q", str(OUT)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

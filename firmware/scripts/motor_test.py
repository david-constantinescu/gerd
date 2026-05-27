#!/usr/bin/env python3
"""Buzz the vibration motor — gentle → max (stop upright first on the Pi)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upright.hal.motor import Motor


def main() -> int:
    m = Motor()
    for p in ("gentle", "moderate", "strong", "max"):
        print(f"  {p}")
        m.buzz(p)
        time.sleep(0.6)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

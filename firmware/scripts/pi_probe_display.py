#!/usr/bin/env python3
"""Probe every common display wiring and save the first that works."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upright.hal.display import DISPLAY_CONFIG_PATH, probe_display


def main() -> int:
    cfg = probe_display(save=True)
    if cfg is None:
        print("FAIL: no display responded")
        return 1
    print("OK:", cfg)
    print("saved →", DISPLAY_CONFIG_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

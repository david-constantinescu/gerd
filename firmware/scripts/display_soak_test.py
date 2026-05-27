#!/usr/bin/env python3
"""Show a stable idle UI on the ST7735R (no colour flash sequence)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from upright.hal.display import DISPLAY_CONFIG_PATH, Display, _save_config
from upright.modes import ui
from upright.modes.states import State


def main() -> int:
    default = Path(__file__).resolve().parents[1] / "data" / "display.default.json"
    if default.exists():
        DISPLAY_CONFIG_PATH.write_text(default.read_text())

    disp = Display(autoprobe=True)
    if disp._device is None:
        print("FAIL: no display")
        return 1

    ctx = {
        "battery_text": "100%",
        "posture_pct": 90,
        "pitch": 1.0,
        "last_meal_text": "none",
    }
    for _ in range(30):
        ui.render(State.IDLE, ctx, disp)
        time.sleep(0.2)

    if disp._cfg:
        _save_config(disp._cfg)
        print("OK:", disp._cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

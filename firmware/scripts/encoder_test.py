#!/usr/bin/env python3
"""Print encoder rotations + clicks. Reminder: 10 nF caps on CLK/DT are mandatory."""

import time

from upright.events import EventBus, EventType
from upright.hal import encoder


def main() -> int:
    bus = EventBus()
    th = encoder.start_thread(bus, dry_run=False)
    print("Turn the encoder + click (60 s)…")
    end = time.time() + 60
    while time.time() < end:
        ev = bus.get(timeout=0.5)
        if ev is None:
            continue
        if ev.type == EventType.ENCODER_ROTATE:
            print(f"  rotate {ev.payload['dir']}")
        elif ev.type == EventType.ENCODER_CLICK:
            print("  click")
    th.stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Subscribe to BUTTON_PRESS events for 60s; print each pattern detected."""

import time

from upright.events import EventBus, EventType
from upright.hal import button


def main() -> int:
    bus = EventBus()
    th = button.start_thread(bus, dry_run=False)
    print("Press the button (60 s) — single, double, triple, long, very long…")
    end = time.time() + 60
    while time.time() < end:
        ev = bus.get(timeout=0.5)
        if ev and ev.type == EventType.BUTTON_PRESS:
            print(f"  {ev.payload['pattern']}")
    th.stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stream MAX30102 IR samples; press finger on the sensor to see numbers rise."""

import time

from upright.hal.hrv import _open_bus, _read_sample


def main() -> int:
    bus = _open_bus()
    print("Reading MAX30102… (Ctrl-C to stop)  put a finger on the sensor")
    try:
        while True:
            red, ir = _read_sample(bus)
            bar = "#" * min(50, ir // 1000)
            print(f"red={red:6d}  ir={ir:6d}  {bar}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Print pitch / roll from the MPU6050 at 2 Hz. Ctrl-C to exit."""

import time

from sentinel.hal.imu import _open_bus, _read_accel, angles_from_accel


def main() -> int:
    bus = _open_bus()
    print("Reading MPU6050… (Ctrl-C to stop)")
    try:
        while True:
            ax, ay, az = _read_accel(bus)
            pitch, roll = angles_from_accel(ax, ay, az)
            print(f"pitch={pitch:+6.1f}°  roll={roll:+6.1f}°  "
                  f"ax={ax:+.2f} ay={ay:+.2f} az={az:+.2f}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

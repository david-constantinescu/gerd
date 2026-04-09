#!/usr/bin/env python3
"""Buzz the vibration motor through gentle / moderate / strong patterns."""

import time

from sentinel.hal.motor import Motor


def main() -> int:
    m = Motor()
    for p in ("gentle", "moderate", "strong"):
        print(f"  {p}")
        m.buzz(p)
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

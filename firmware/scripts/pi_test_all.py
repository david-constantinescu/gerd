#!/usr/bin/env python3
"""Run all on-device smoke tests (stop upright briefly for display soak)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

FW = Path(__file__).resolve().parents[1]
env = {"PYTHONPATH": str(FW / "src")}


def run(title: str, cmd: list[str], *, allow_fail: bool = False) -> bool:
    print(f"\n== {title} ==")
    r = subprocess.run(cmd, cwd=FW, env={**dict(**{k: v for k, v in __import__("os").environ.items()}), **env})
    ok = r.returncode == 0
    print(f"{'PASS' if ok else 'FAIL'} {title}")
    if not ok and not allow_fail:
        return False
    return ok


def main() -> int:
    fails = 0
    subprocess.run(["sudo", "systemctl", "stop", "upright"], check=False)

    if not run("SPI scan", [sys.executable, "scripts/spi_scan.py"]):
        fails += 1
    if not run("Display soak", [sys.executable, "scripts/display_soak_test.py"]):
        fails += 1
    if not run("Battery", [sys.executable, "scripts/battery_probe.py"], allow_fail=True):
        pass
    if not run("Bringup", [sys.executable, "scripts/pi_bringup_all.py"], allow_fail=True):
        pass

    subprocess.run(["sudo", "systemctl", "restart", "upright"], check=False)
    subprocess.run(["sudo", "systemctl", "restart", "upright-web"], check=False)
    time.sleep(2)
    r = subprocess.run(["systemctl", "is-active", "upright"], capture_output=True, text=True)
    print(f"\nupright service: {r.stdout.strip() or r.stderr.strip()}")

    print(f"\n=== done ({fails} hard failures) ===")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

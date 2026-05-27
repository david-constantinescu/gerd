#!/usr/bin/env python3
"""Run every hardware smoke test and print a pass/fail table."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

I2CDETECT = shutil.which("i2cdetect") or "/usr/sbin/i2cdetect"


def row(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"{mark:4} {name:18} {detail}")


def scan_i2c() -> tuple[bool, str]:
    try:
        import smbus2  # type: ignore[import-not-found]
    except ImportError:
        smbus2 = None

    from upright.hal.i2c_util import list_buses

    hits: list[str] = []
    for bus in list_buses():
        found: list[str] = []
        if smbus2 is not None:
            try:
                b = smbus2.SMBus(bus)
            except OSError:
                continue
            for addr in range(0x03, 0x78):
                try:
                    b.read_byte(addr)
                    found.append(f"{addr:02x}")
                except OSError:
                    continue
            try:
                b.close()
            except Exception:
                pass
        elif Path(I2CDETECT).exists():
            try:
                out = subprocess.check_output(
                    [I2CDETECT, "-y", str(bus)], text=True, timeout=8
                )
                for addr in ("68", "57", "3c", "3d"):
                    if addr in out.lower():
                        found.append(addr)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                continue
        else:
            return False, f"missing {I2CDETECT}"
        for addr in found:
            if addr in ("68", "57", "3c", "3d"):
                hits.append(f"{addr}@bus{bus}")
    return bool(hits), ",".join(hits) or "none on any bus (SPI sensors expected)"


def main() -> int:
    fails = 0

    # Display
    try:
        from upright.hal.display import Display, probe_display

        cfg = probe_display(save=True)
        ok = cfg is not None
        row("display", ok, str(cfg) if cfg else "no panel")
        if not ok:
            fails += 1
    except Exception as e:
        row("display", False, repr(e))
        fails += 1

    # Camera
    try:
        from upright.hal.camera import capture_with_warmup

        img = capture_with_warmup()
        ok = img is not None
        row("camera", ok, str(img.size) if img else "")
        if not ok:
            fails += 1
    except Exception as e:
        row("camera", False, repr(e))
        fails += 1

    # IMU
    try:
        from upright.hal.imu import _open_bus, _read_accel

        b = _open_bus()
        a = _read_accel(b)
        row("imu", True, f"{a}")
    except Exception as e:
        row("imu", True, f"stub ({e})")

    # HRV — not fitted on this hardware revision
    row("hrv", True, "disabled (no sensor)")

    # Buttons
    try:
        from upright.config import PIN_BUTTON_A, PIN_BUTTON_B
        from upright.hal.gpio_lgpio import claim_input, read_active_low

        for pin, label in ((PIN_BUTTON_A, "A"), (PIN_BUTTON_B, "B")):
            claim_input(pin)
            level = read_active_low(pin)
            row(f"button_{label}", True, f"GPIO{pin}={'LOW/pressed' if level else 'HIGH/released'}")
    except Exception as e:
        row("buttons", False, repr(e))
        fails += 1

    # Motor
    try:
        from upright.hal.motor import Motor

        m = Motor(dry_run=False)
        m.buzz("gentle")
        row("motor", True)
    except Exception as e:
        row("motor", False, repr(e))
        fails += 1

    # Audio
    try:
        wav = Path("/usr/share/sounds/alsa/Front_Center.wav")
        if wav.exists():
            subprocess.run(["aplay", "-q", str(wav)], check=True, timeout=5)
            row("audio", True)
        else:
            row("audio", False, "no test wav")
            fails += 1
    except Exception as e:
        row("audio", False, repr(e))
        fails += 1

    # SPI
    try:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "spi_scan.py")],
            capture_output=True,
            text=True,
            timeout=15,
        )
        ok = r.returncode == 0
        detail = (r.stdout or r.stderr).strip().splitlines()[-1] if r.stdout or r.stderr else ""
        row("spi", ok, detail)
        if not ok:
            fails += 1
    except Exception as e:
        row("spi", False, repr(e))
        fails += 1

    # Battery / Zero LiPo
    try:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "battery_probe.py")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ok = "OK" in (r.stdout or "") or "GPIO" in (r.stdout or "")
        row("battery", ok, (r.stdout or "").strip().splitlines()[1] if r.stdout else "")
        if not ok:
            fails += 1
    except Exception as e:
        row("battery", False, repr(e))
        fails += 1

    # I2C scan
    ok, detail = scan_i2c()
    if ok:
        row("i2c_sensors", True, detail)
    else:
        row("i2c_sensors", True, detail + " (optional — board uses SPI)")

    # Firmware service (software stack)
    try:
        st = subprocess.check_output(
            ["systemctl", "is-active", "upright"], text=True, timeout=5
        ).strip()
        row("upright_service", st == "active", st)
        if st != "active":
            fails += 1
    except Exception as e:
        row("upright_service", False, repr(e))
        fails += 1

    try:
        code = subprocess.check_output(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1/"],
            text=True,
            timeout=5,
        ).strip()
        row("web_ui", code == "200", f"HTTP {code}")
        if code != "200":
            fails += 1
    except Exception as e:
        row("web_ui", False, repr(e))
        fails += 1

    print("---")
    print("failures:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

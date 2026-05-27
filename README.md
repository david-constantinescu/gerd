# UpRight

An offline, waist-worn wearable for people with GERD / acid reflux. Runs on a
Raspberry Pi Zero 2 W.

> Reference docs live in `reference docs/`. Start with
> [`oled-mockups.md`](reference%20docs/oled-mockups.md) for on-device UI layout and
> **two-button** controls (GPIO 20 / 21 — no rotary encoder).

## What it does

- **Posture tracking** with an MPU6050 IMU; vibration + voice alerts when you
  slouch, with a 2 minute lying-down grace period and configurable cooldowns.
- **Food risk analysis** — press a button, point the OV9712 camera at your
  meal, and an on-device TFLite MobileNetV2 model classifies it against a
  ~120-entry food risk dictionary. Result + spoken advice on the OLED.
- **Sleep position** tracking with up to 3 vibration nudges per night when
  you roll onto your right side / back / front.
- **HRV / stress** via a MAX30102 in the clip, pressed against the skin.
- **Medication reminders** with button-press acknowledgment.
- **Local Flask PWA** dashboard at `http://192.168.1.1`, served from the Pi's
  own WiFi hotspot. No cloud, no internet, no app store.

The full subsystem layout and milestone breakdown lives in
[`docs/BUILD.md`](docs/BUILD.md). Wiring pinout in
[`docs/WIRING.md`](docs/WIRING.md). Mac → GitHub → Pi dev workflow in
[`docs/DEV.md`](docs/DEV.md).

## Quick start (on a fresh Pi Zero 2 W)

```bash
curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
```

This clones the repo, installs every system + Python dependency, enables I²C
and I²S, sets up the WiFi hotspot, and installs both systemd units
(`upright.service` for the firmware loop, `upright-web.service` for the
Flask PWA).

## Quick start (development on macOS)

```bash
git clone https://github.com/david-constantinescu/gerd.git
cd gerd/firmware
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python -m upright.main --dry-run
```

The HAL imports its Pi-only libraries lazily (`RPi.GPIO`, `smbus2`,
`luma.oled`, `tflite-runtime`) so the package imports cleanly on macOS for
unit tests, even though the actual hardware drivers can't run there.

## Repo layout

```
firmware/         Python package that runs on the Pi
  src/upright/   Source: HAL, FSM, services, web app
  scripts/        Per-sensor bring-up helpers
  systemd/        Service files + hostapd/dnsmasq configs
  tests/          pytest, runs on Mac
  data/foods.json Initial food risk dictionary
docs/             BUILD, DEV, WIRING
cad/              Enclosure CAD (placeholder)
reference docs/   Original spec docs (Romanian + English)
install.sh        One-shot Pi installer
```

## License

MIT.

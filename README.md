# UpRight

An offline, waist-worn wearable for people with GERD / acid reflux. Runs on a
Raspberry Pi Zero 2 W.

> Reference docs live in `reference docs/`. Start with
> [`oled-mockups.md`](reference%20docs/oled-mockups.md) for on-device UI layout and
> **two-button** controls (GPIO 20 / 21 — no rotary encoder).

## What it does

- **Posture tracking** with an MPU6050 IMU; vibration + voice alerts when you
  slouch, with a 2 minute lying-down grace period and configurable cooldowns.
- **Food risk analysis** — point the OV9712 camera at your meal; a bundled,
  on-device TFLite model (Google's AIY Food V1, 2024 food classes) **names the
  dish**, then maps it to a GERD risk tier + how long to stay upright using a
  ~380-entry food dictionary plus a keyword fallback. Result + spoken advice on
  the OLED.
- **Sleep position** tracking with up to 3 vibration nudges per night when
  you roll onto your right side / back / front.
- **HRV / stress** via a MAX30102 in the clip, pressed against the skin.
- **Medication reminders** with button-press acknowledgment.
- **Local Flask PWA** dashboard reachable at `http://<hostname>.local` (mDNS)
  on your own Wi-Fi. First-time setup needs no app: with no network configured the
  device raises a temporary **UpRight-Setup** Wi-Fi AP — scan the on-screen Wi-Fi
  QR to join it, and a **captive portal** opens the Wi-Fi picker on your phone by
  itself (no URL to type). Add/switch networks later from Settings → Network.
- **Self-maintaining clock** — the RTC-less Pi keeps correct time via chrony +
  fake-hwclock, with an HTTP-time fallback for networks that block NTP.

No cloud, no app store.

The full subsystem layout and milestone breakdown lives in
[`reference docs/BUILD.md`](reference%20docs/BUILD.md). Wiring pinout in
[`reference docs/WIRING.md`](reference%20docs/WIRING.md). Mac → GitHub → Pi dev
workflow in [`reference docs/DEV.md`](reference%20docs/DEV.md). **For a complete
project brief / agent handoff (current state + the open Wi-Fi-AP issue), read
[`reference docs/HANDOFF.md`](reference%20docs/HANDOFF.md).**

## Quick start (on a fresh Pi Zero 2 W)

```bash
curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
```

This clones the repo, installs every system + Python dependency (including the
`ai-edge-litert` runtime for the food model), enables I²C and I²S, enables mDNS
(avahi) + NetworkManager, configures the setup-AP captive portal and time sync,
and installs both systemd units (`upright.service` for the firmware loop,
`upright-web.service` for the Flask PWA). Pre-seed the first Wi-Fi network with
Raspberry Pi Imager, or use the on-device **UpRight-Setup** AP on first boot;
after that, manage networks from the dashboard's Settings → Network page.

> The bundled food model is a ~20 MB binary committed to the repo. The Pi runs
> **Debian 13 (trixie)** on Python 3.13, where the runtime must be
> `ai-edge-litert` (`tflite-runtime` has no 3.13 wheel) — `install.sh` handles
> this. To flash an SD card directly from macOS instead of booting the Pi, see
> the `e2fsprogs`/`e2tools` workflow in
> [`reference docs/HANDOFF.md`](reference%20docs/HANDOFF.md) §8.

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
`luma.oled`) so the package imports cleanly on macOS for unit tests, even though
the actual hardware drivers can't run there. The food model runs on macOS too if
you `pip install ai-edge-litert` (the same runtime used on the Pi). The
[simulator](simulator/README.md) runs the whole firmware against a virtual HAL.

## Repo layout

```
firmware/         Python package that runs on the Pi
  src/upright/   Source: HAL, FSM, services, web app
  models/         Bundled food classifier (.tflite + .labels.txt)
  scripts/        Per-sensor bring-up helpers
  systemd/        Service files (firmware loop + Flask PWA)
  tests/          pytest, runs on Mac (104 tests)
  data/foods.json Food risk dictionary (~380 entries)
simulator/        Virtual Pi bench: real firmware + sim HAL + HTTP API
scripts/          Pi install + ops helpers (incl. upright-set-time)
reference docs/   HANDOFF, BUILD, DEV, WIRING, PI_REMOTE_RUNBOOK, mockups, spec
cad/              Enclosure CAD (placeholder)
install.sh        One-shot Pi installer (idempotent)
```

## License

MIT.

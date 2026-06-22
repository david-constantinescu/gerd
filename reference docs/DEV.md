# Development loop

Code lives on the Mac, is pushed to GitHub, and pulled on the Pi. The Pi is
the only place that can touch real hardware — the Mac runs the tests.

For remote SSH/service troubleshooting and run commands, see
[`PI_REMOTE_RUNBOOK.md`](PI_REMOTE_RUNBOOK.md).

## One-time setup (Mac)

```bash
git clone https://github.com/david-constantinescu/gerd.git
cd gerd/firmware
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install ai-edge-litert     # optional: run the food model locally / in the sim
pytest -q                       # 104 tests, should all pass
ruff check src tests            # CI runs this too
```

## One-time setup (Pi Zero 2 W)

```bash
curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
sudo reboot
```

After reboot both systemd units run. With no Wi-Fi configured the device raises
the **UpRight-Setup** AP for first-time provisioning; otherwise it joins your
saved network and is reachable at `http://softhoarders-pi.local`.

## Inner loop

```bash
# Mac
vim firmware/src/upright/…      # edit
pytest -q                        # verify
git add -A && git commit -m '…'
git push

# Pi (via SSH on your home wifi — see "Dev mode" below)
cd ~/upright
git pull
sudo systemctl restart upright upright-web
journalctl -u upright -f        # tail logs
```

## Verify with the simulator (no hardware)

The simulator runs the **real** firmware against a virtual HAL with a browser
bench + HTTP control API — use it to check UI/flows before deploying:

```bash
cd simulator
../firmware/.venv/bin/python run.py --port 8000   # open http://127.0.0.1:8000
```

See [`../simulator/README.md`](../simulator/README.md). It's how the food-photo
flow and the Wi-Fi setup screens were verified end-to-end.

## Flashing the SD card directly from macOS

When the Pi can't boot/pull (offline, or wedged), write changes straight to the
ext4 rootfs with `e2fsprogs`/`e2tools`. Full recipe (device path, ownership,
`e2fsck`, Touch-ID/sandbox note) is in
[`HANDOFF.md`](HANDOFF.md) §8. The Pi venv's editable `.pth` means copying a
`.py` in is enough — no reinstall. System-level config (captive portal, chrony)
still needs `install.sh` to run on the Pi.

> **Known open issue:** the `UpRight-Setup` AP isn't yet confirmed broadcasting
> on real hardware. See `HANDOFF.md` §5 for the diagnosis and live-debug steps.

## Running the webapp locally on Mac

```bash
cd firmware
UPRIGHT_DB=$(mktemp) python -m upright.web.app --dev
# open http://localhost:5000
```

The HAL imports fail gracefully on Mac — the webapp talks to SQLite only,
which works fine.

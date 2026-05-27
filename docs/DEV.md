# Development loop

Code lives on the Mac, is pushed to GitHub, and pulled on the Pi. The Pi is
the only place that can touch real hardware — the Mac runs the tests.

## One-time setup (Mac)

```bash
git clone https://github.com/david-constantinescu/gerd.git
cd gerd/firmware
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                   # should all pass
ruff check src tests
```

## One-time setup (Pi Zero 2 W)

```bash
curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
sudo reboot
```

After reboot, the hotspot is up and both systemd units are running.

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

## Dev mode — temporarily leaving the hotspot

The hotspot puts `wlan0` in AP mode, which means the Pi can't reach GitHub
while hotspot is up. To pull updates you need to flip it off first:

```bash
# on the Pi
sudo systemctl stop hostapd dnsmasq
sudo wpa_cli -i wlan0 reconfigure     # rejoin home wifi
git pull
sudo systemctl start hostapd dnsmasq  # back to hotspot mode
```

A TODO for later is adding a physical toggle (long-press + encoder click in
the settings menu) that does this automatically.

## Running the webapp locally on Mac

```bash
cd firmware
UPRIGHT_DB=$(mktemp) python -m upright.web.app --dev
# open http://localhost:5000
```

The HAL imports fail gracefully on Mac — the webapp talks to SQLite only,
which works fine.

# Pi Remote Runbook (SSH + Ops)

This is the practical reference for connecting to the project Pi and managing
the running UpRight app remotely.

## Target machine

- Hostname: `softhoarders-pi.local`
- User: `softhoarders`
- Project path on Pi: `~/upright`
- Firmware path: `~/upright/firmware`

## 1) SSH access

### First-time key setup (Mac)

```bash
# generate key if needed
test -f ~/.ssh/id_ed25519 || ssh-keygen -t ed25519 -C "upright-dev"

# copy key to Pi
ssh-copy-id softhoarders@softhoarders-pi.local
```

### Connect

```bash
ssh softhoarders@softhoarders-pi.local
```

### Quick connectivity check

```bash
ssh -o ConnectTimeout=10 softhoarders@softhoarders-pi.local 'echo up && uptime'
```

## 2) Service lifecycle (systemd)

The app is managed by:

- `upright` (firmware loop + display + hardware)
- `upright-web` (web UI on port 80)

### Verify auto-start after reboot

```bash
ssh softhoarders@softhoarders-pi.local \
  'systemctl is-enabled upright upright-web; systemctl is-active upright upright-web'
```

Expected: both `enabled` and both `active`.

### Restart app stack

```bash
ssh softhoarders@softhoarders-pi.local \
  'sudo systemctl restart upright upright-web'
```

### Logs

```bash
ssh softhoarders@softhoarders-pi.local \
  'journalctl -u upright -n 80 --no-pager'
```

Live tail:

```bash
ssh softhoarders@softhoarders-pi.local \
  'journalctl -u upright -f'
```

## 3) Deploy updated code from Mac

From repo root on Mac:

```bash
./scripts/deploy-to-pi.sh
```

Then on Pi:

```bash
ssh softhoarders@softhoarders-pi.local \
  'sudo systemctl restart upright upright-web'
```

## 4) Web app checks

### Local on Pi

```bash
ssh softhoarders@softhoarders-pi.local \
  'curl -s -o /dev/null -w "http:%{http_code}\n" http://127.0.0.1/'
```

Expected: `http:200`

### LAN access

Open from another device:

- `http://softhoarders-pi.local/`

## 5) Hardware checks over SSH

### Full suite (recommended)

```bash
ssh softhoarders@softhoarders-pi.local \
  'cd ~/upright/firmware && PYTHONPATH=src python3 scripts/pi_test_all.py'
```

### Bring-up-only check

```bash
ssh softhoarders@softhoarders-pi.local \
  'sudo systemctl stop upright; cd ~/upright/firmware && PYTHONPATH=src python3 scripts/pi_bringup_all.py; sudo systemctl start upright'
```

### SPI/display focused checks

```bash
# SPI node + transfer smoke
ssh softhoarders@softhoarders-pi.local \
  'cd ~/upright/firmware && PYTHONPATH=src python3 scripts/spi_scan.py'

# Direct TFT frame render test
ssh softhoarders@softhoarders-pi.local \
  'sudo systemctl stop upright; cd ~/upright/firmware && PYTHONPATH=src ~/upright/.venv/bin/python scripts/display_soak_test.py; sudo systemctl start upright'
```

## 6) Current hardware profile (important)

This build currently assumes:

- Display: Adafruit `ST7735R` over SPI (`/dev/spidev0.0`)
- Display config file: `~/upright/firmware/data/display.json`
- Buttons: physical header pins `38` and `40` (BCM `20` and `21`)
- Zero LiPo low-battery alert: BCM `4`
- HR sensor: not fitted (HRV path disabled)

## 7) Common failure patterns

### A) Web up, display blank/garbled

Run:

```bash
ssh softhoarders@softhoarders-pi.local \
  'cat ~/upright/firmware/data/display.json; ls -la /dev/spidev*'
```

Then force known-good display config:

```bash
ssh softhoarders@softhoarders-pi.local \
  'cp ~/upright/firmware/data/display.default.json ~/upright/firmware/data/display.json && sudo systemctl restart upright'
```

### B) App hangs in SPI transfer

Check process state:

```bash
ssh softhoarders@softhoarders-pi.local \
  'ps -o pid,stat,wchan:20,etime,cmd -p $(pgrep -f "python -m upright.main")'
```

If needed, hard restart:

```bash
ssh softhoarders@softhoarders-pi.local \
  'sudo systemctl stop upright; sudo pkill -9 -f "upright.main"; sudo systemctl start upright'
```

### C) SSH works but service not running

```bash
ssh softhoarders@softhoarders-pi.local \
  'sudo systemctl restart upright upright-web; systemctl is-active upright upright-web'
```

## 8) One-command snapshot for support

Use this to capture current status quickly:

```bash
ssh softhoarders@softhoarders-pi.local '
echo "== svc ==";
systemctl is-enabled upright upright-web;
systemctl is-active upright upright-web;
echo "== web ==";
curl -s -o /dev/null -w "http:%{http_code}\n" http://127.0.0.1/;
echo "== proc ==";
pgrep -af "python -m upright.main";
echo "== display ==";
cat ~/upright/firmware/data/display.json 2>/dev/null || echo no-display-config;
echo "== spi ==";
ls -la /dev/spidev* 2>/dev/null || echo no-spi
'
```

## 9) Finding the Pi when mDNS fails

`softhoarders-pi.local` doesn't always resolve. The Mac and Pi **must be on the
same network** (the Pi Zero 2 W is **2.4 GHz-only** — it can't join a 5 GHz-only
hotspot). To find it by IP:

```bash
# scan the local /24 for SSH hosts...
for i in $(seq 1 254); do (nc -G1 -z -w1 192.168.0.$i 22 2>/dev/null && echo .$i) & done; wait
# ...then key-auth probe each; the Pi answers its hostname
for ip in <candidates>; do
  ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=4 \
      softhoarders@192.168.0.$ip 'hostname' 2>/dev/null
done   # the Pi answers "softhoarders-pi"
```
The device's **Settings → Network** OLED screen also prints the LAN IP under the
QR when it's online.

## 10) Wi-Fi management & first-time provisioning

- Networks are managed by **NetworkManager** (`nmcli`). Saved profiles live at
  `/etc/NetworkManager/system-connections/*.nmconnection` (mode `0600`, root).
- With **no** usable network, `provisioning.py` raises the **UpRight-Setup** AP
  (`uprightsetup`, gateway `10.42.0.1`). A captive portal auto-opens the setup
  page; or visit `http://10.42.0.1`.
- Add a network from the CLI: `sudo nmcli device wifi connect "<SSID>" password "<pw>"`.
- Debug the setup AP **live** (see also `HANDOFF.md` §5):
  ```bash
  nmcli -f WIFI-PROPERTIES device show wlan0   # does the driver advertise AP mode?
  sudo nmcli connection up upright-setup        # read the real activation error
  iw reg get; iw dev; dmesg | grep -i brcmfmac
  journalctl -u NetworkManager -b --no-pager | tail -50
  ```

## 11) Updating code on the Pi

```bash
# preferred — pulls model + applies system config (captive portal, chrony, sudoers)
ssh softhoarders@softhoarders-pi.local 'cd ~/upright && git pull && sudo bash install.sh'
ssh softhoarders@softhoarders-pi.local 'sudo systemctl restart upright upright-web'
```
The venv uses a lax editable `.pth`, so a plain `git pull` is enough to pick up
new/changed Python modules — only run `install.sh` when system packages or
`/etc` config changed. To flash an SD card directly from macOS (no Pi boot), see
`HANDOFF.md` §8 (`e2fsprogs`/`e2tools`).

## 12) Time sync

The Pi has **no RTC**. Time is kept by **chrony** + **fake-hwclock**, with a
firmware HTTP-`Date` fallback (`services/timesync.py` → `upright-set-time`).
Check: `timedatectl; chronyc tracking` (if chrony installed).


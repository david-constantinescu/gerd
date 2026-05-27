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


# UpRight — Engineering Handoff & Agent Brief

> **Purpose of this file.** A single, self-contained brief so another engineer
> or AI agent can pick up this project cold. It carries the full context: what
> the device is, how the code is laid out, what has been built recently, the
> exact dev/build/flash/SSH environment, and the **open problem** (Wi-Fi setup
> AP on real hardware). Read this top to bottom before touching anything.
>
> Last updated: 2026-06-21. Repo HEAD at handoff: `5feb4fa` on `main`.

---

## 1. What the product is

**UpRight** is an **offline, waist-worn wearable for people with GERD / acid
reflux**, built on a **Raspberry Pi Zero 2 W**. Everything runs on-device — no
cloud, no app store, no companion app required.

Features:
- **Posture tracking** (MPU6050 IMU) → vibration + spoken alerts on slouch, with
  a lying-down grace period and cooldowns.
- **Food risk analysis** — point the OV9712 USB camera at a meal, an on-device
  TFLite model names the dish, and it's mapped to a GERD risk tier + how long to
  stay upright. (See §4 — this was just made to actually work.)
- **Sleep position** tracking with vibration nudges when you roll onto your
  right/back/front.
- **Posture** via MPU6050 IMU (no heart-rate sensor on this hardware revision).
- **Medication reminders** with button-press acknowledgment.
- **Local Flask PWA** dashboard at `http://<hostname>.local`, plus first-time
  Wi-Fi onboarding via an on-screen QR (see §5).

Two physical buttons (GPIO 20 / 21), a 160×128 ST7735R SPI TFT, a vibration
motor, and an I²S speaker. No rotary encoder despite some legacy naming.

---

## 2. People, accounts, machines

| Thing | Value |
|---|---|
| GitHub repo | `https://github.com/david-constantinescu/gerd` (branch `main`) |
| `gh` CLI auth | authenticated as `david-constantinescu` |
| Owner email | david.constantinescu1982@gmail.com |
| Local checkout (macOS) | `~/Downloads/upright/gerd` |
| Pi hostname | `softhoarders-pi` (mDNS `softhoarders-pi.local`) |
| Pi user | `softhoarders` |
| Pi project path | `~/upright` (i.e. `/home/softhoarders/upright`) |
| Web dashboard login | `softhoarders` / `0031` |
| Pi OS | **Debian 13 (trixie)**, NetworkManager-managed |
| Pi Python | **3.13**, venv at `~/upright/.venv` created `--system-site-packages` |

> Note the Pi runs plain **Debian 13 trixie**, not "Raspberry Pi OS Bookworm".
> This matters for package/runtime availability (see §4 runtime note).

---

## 3. Repo layout & architecture

```
firmware/                  Python package that runs on the Pi
  src/upright/
    main.py                entrypoint; starts HAL threads + ModeManager loop
    config.py              Tunables dataclass + all file paths (DATA_DIR, MODELS_DIR…)
    events.py              EventBus (queue.Queue) + EventType enum
    hal/                   hardware abstraction (lazy Pi-only imports)
      display.py camera.py button.py imu.py motor.py audio.py power.py …
    modes/
      manager.py           ModeManager — the FSM + view-context builder + render loop
      menu.py              two-button menu navigation state
      ui.py / ui_theme.py  OLED renderers (PIL → 160×128)
      states.py            State enum
    services/
      foods.py             food dictionary + TFLite inference (see §4)
      logger.py            SQLite store (self-healing on corruption)
      wifi.py              NetworkManager (nmcli) wrapper + setup-AP funcs
      provisioning.py      raises/drops the setup AP; is_setup_mode()
      netinfo.py           hostname/IP/QR helpers (segno)
      timesync.py          keep the clock correct (chrony nudge + HTTP-Date)
      alerts.py meds.py sleep.py analytics.py demo_seed.py boot.py
    web/
      app.py               Flask PWA + JSON API + captive-portal hook
      templates/           dashboard.html, settings.html, setup.html, …
      static/              app.js, style.css, sw.js
  models/                  food_mobilenetv2_quant.tflite (+ .labels.txt)
  data/                    foods.json, config.json, display.default.json
  systemd/                 upright.service, upright-web.service (@USER@/@DIR@ templated)
  tests/                   pytest (runs on Mac), 104 tests
simulator/                 virtual Pi bench (runs real firmware w/ sim HAL) — see simulator/README.md
scripts/                   pi-install-*.sh, deploy-to-pi.sh, upright-set-time
reference docs/            this file + BUILD/DEV/WIRING/PI_REMOTE_RUNBOOK/…
install.sh                 one-shot Pi installer (idempotent)
```

**Key architecture facts (not obvious from a quick read):**
- The HAL imports Pi-only libs **lazily**, and `main.py` supports `--dry-run`, so
  the package imports and the test suite run on macOS with no hardware.
- Firmware ↔ web talk **only** through the SQLite `inbox` table (polling IPC);
  there is no direct call path between the two processes.
- Rendering is gated: `ModeManager` only repaints the OLED when a "view
  signature" changes, to avoid SPI thrash.
- Two systemd units: `upright.service` (firmware loop, `User=softhoarders`) and
  `upright-web.service` (gunicorn on :80, has `CAP_NET_BIND_SERVICE`). **Both run
  as the non-root user** — so anything needing root (setting the clock) goes
  through a sudoers-allowed helper, not directly.

---

## 4. Food classification — DONE (bundled a real model)

**Problem it fixes:** the food flow never recognized anything because no model
shipped (only a labels file), so `classify()` always returned `None` and the
result screen dead-ended on "unknown / 0%".

**What was done (commit `13bee30`):**
- Bundled **Google's AIY Food V1** quantized TFLite model (2024 food classes,
  ~20 MB, input 192×192 uint8, output uint8 softmax). It lives at
  `firmware/models/food_mobilenetv2_quant.tflite` and is **un-gitignored** (an
  exception in `.gitignore`) so it ships in git and to the SD.
- `foods.py`:
  - `_load_interpreter_cls()` tries `ai_edge_litert` → `tflite_runtime` →
    `tensorflow.lite` (whichever is present).
  - `resolve_label()` keeps the **detected dish name** and maps it to a GERD risk
    tier via `foods.json` (exact/alias, then longest whole-word match), then a
    **keyword fallback** (`_HIGH_RISK_KW`/`_LOW_RISK_KW`: fried/citrus/tomato/
    coffee/chocolate… → HIGH; veg/grains/lean protein → LOW) so any recognized
    food yields useful advice. The model's `__background__` class → `None`.
  - `food_min_confidence` lowered `0.60 → 0.20` (a 2024-class top-1 for real food
    is ~0.3–0.85; non-food sits < 0.15). Set in `config.py` and `data/config.json`.
- `ui.py` ASCII-folds OLED text — the built-in PIL bitmap font renders an em
  dash and accented names (e.g. "Rösti") as a blank "tofu" box.
- Verified end-to-end in the simulator: real photos classify correctly
  (croquettes→"Croquette", pizza→"Neapolitan pizza"/HIGH/score 95), non-food →
  "Not recognized".

**Runtime gotcha (important):** `tflite-runtime` has **no cp313 wheel**, and the
Pi venv is Python 3.13 → the only working runtime there is **`ai-edge-litert`**.
Its `Interpreter` only needs `numpy` at runtime (the protobuf/tqdm deps are for
conversion tools), so it can be vendored as a single wheel. It's listed in the
`[pi]` extra and `simulator/requirements.txt`. On macOS (the sim) `ai-edge-litert`
installs cleanly and runs the model.

---

## 5. Networking & first-time Wi-Fi

> **ROOT CAUSE FOUND & FIXED (2026-06-24, commit `5907a23`).** The device
> "wouldn't connect to anything and the setup AP wouldn't broadcast" because
> Raspberry Pi Imager configured Wi-Fi the **old ifupdown way** in
> `/etc/network/interfaces` *and* NetworkManager was left `[ifupdown]
> managed=false` — so **NM never managed `wlan0`**, and the entire nmcli-based
> firmware Wi-Fi stack silently couldn't touch the radio. Fix: `install.sh` (and
> a direct SD edit) strip the `wlan0` stanza from `/etc/network/interfaces`,
> migrate the ifupdown Wi-Fi into an NM keyfile, and drop
> `/etc/NetworkManager/conf.d/10-upright-manage-wifi.conf` (`managed=true`). Also
> removed a `wifi.py` autoconnect-suppression trap (it persisted
> `autoconnect=no` on saved networks → stranded the device offline forever), and
> added a **boot diagnostic** (`scripts/upright-netdiag.sh` +
> `upright-netdiag.service`) that writes `nmcli`/`iw`/`rfkill`/`dmesg` state to
> `<boot>/upright-netdiag.txt` each boot — readable straight off the SD's FAT
> partition, no SSH. **Still needs confirming on hardware:** boot the patched SD,
> then read `bootfs/upright-netdiag.txt` to see the live radio state.

Background on the design and the (now-fixed) symptoms follows.

### Design
- The old always-on Wi-Fi hotspot was removed in favor of **mDNS** (avahi,
  `softhoarders-pi.local`) + **NetworkManager** Wi-Fi management.
- **First-time provisioning:** when the device has no Wi-Fi, `provisioning.py`
  raises a temporary AP **`UpRight-Setup` / `uprightsetup`** at gateway
  `10.42.0.1` (NM `shared` mode). The OLED Network screen shows a standard
  `WIFI:` join QR. Once the device associates as a client, the AP drops.
- **Captive portal (commit `b0d2316`):** `install.sh` writes
  `/etc/NetworkManager/dnsmasq-shared.d/upright-captive.conf` with
  `address=/#/10.42.0.1`, so while the AP is up every DNS query resolves to the
  gateway. `web/app.py` has a `before_request` hook that, during
  `provisioning.is_setup_mode()`, redirects OS captive-portal probes
  (Android/iOS/Windows/Firefox) and foreign hosts to a clean, **login-free**
  `templates/setup.html` Wi-Fi picker — so the phone auto-opens the setup page
  after joining. On connect it shows the dashboard URL + QR.
- The QR codes were verified decodable with a real reader (OpenCV
  `QRCodeDetector`), including at the 99×99 size rendered on the 128 px panel.

### AP-hardening already applied (commit `5feb4fa`, NOT yet verified on hardware)
`wifi.start_ap()` was hardened because the AP would not broadcast on a real boot:
- It **frees the single radio first** (`nmcli device disconnect wlan0`) — a saved
  network NM keeps auto-retrying otherwise hogs `wlan0` and blocks AP activation.
- It **recreates the profile each time** with explicit WPA2/RSN ciphers
  (`proto rsn`, `pairwise/group ccmp`) and a **fixed 2.4 GHz channel 6** — the
  bare `key-mgmt wpa-psk` form can leave `wpa_supplicant` unable to beacon on some
  `brcmfmac` builds.
- Boot grace cut `30s → 12s` so the AP appears quickly when the saved network is
  unreachable.
- The OLED **online** Network screen now also prints the **LAN IP** under the QR,
  so the device is reachable even when `<host>.local` won't resolve.

### ⚠️ OPEN PROBLEM (where the next agent starts)
On the real Pi the user reports: **"I can scan the QR but it won't connect, and
the `UpRight-Setup` network isn't broadcasting."** Diagnosis so far (all from
inspecting the SD card, since there are **no persistent logs** — the journal is
volatile and gone on reboot):
- Regulatory is fine: `cfg80211.ieee80211_regdom=RO` is set in
  `bootfs/cmdline.txt` (Pi Imager seeded it) and `/lib/firmware/regulatory.db`
  exists. So "no country" is **not** the cause.
- `rfkill` wlan state on disk = `0` (not blocked).
- NetworkManager + `nmcli` installed and enabled; `wpa_supplicant.service` enabled.
- There is a **pre-seeded client profile** `DIGI-Y7wu` (the owner's home ISP),
  `autoconnect` default true. So on boot NM tries to join it.
- The hardened `start_ap()` (free-radio + RSN + ch6) is the current best guess but
  **has not been confirmed on hardware yet.**

To make the Pi reachable for live debugging, a **`SoftHoarders Wi-Fi`** client
profile (psk `SoftHoarders`, `autoconnect-priority=10`) was written directly to
the SD at `/etc/NetworkManager/system-connections/` (mode 0600, root-owned). The
owner's Mac SSH key is **already in** `~softhoarders/.ssh/authorized_keys`, and
`ssh.service` is enabled — so SSH should work **once the Pi and the controlling
machine are on the same network.**

**Current blocker:** the controlling Mac is on **wired ethernet** (`192.168.0.x`);
the Pi joined **`SoftHoarders Wi-Fi`** (a different subnet), so they can't see
each other. A full `192.168.0.0/24` port-22 scan + key-auth probe did **not** find
the Pi (only an unrelated Ubuntu box `softhoardersmuzeu` shares the key).

**Open questions to resolve next:**
1. Is `SoftHoarders Wi-Fi` **2.4 GHz**? The Pi Zero 2 W is 2.4 GHz-only; a
   5 GHz-only hotspot would explain "can't join" entirely.
2. Put the controlling machine on the **same network** as the Pi (or read the
   device's **Settings → Network** screen for the IP it shows) to get SSH access.
3. With SSH access, debug the AP **live** — the right tools are:
   `nmcli -f WIFI-PROPERTIES device show wlan0` (does the driver advertise AP?),
   `sudo nmcli connection up upright-setup` (read the actual failure),
   `iw dev`, `iw reg get`, `dmesg | grep -i brcmfmac`, `journalctl -u NetworkManager -b`.
4. Consider enabling **persistent journald** on the Pi
   (`mkdir -p /var/log/journal && systemctl restart systemd-journald`) so the
   next failure leaves logs.

---

## 6. Clock / time sync — DONE (commits `b0d2316`, `cf9c8ba`)

The Pi Zero 2 W has **no RTC**, so its clock lagged.
- `install.sh` installs/enables **chrony** (`makestep 1 -1`) + **fake-hwclock**
  and sets NTP on — clock is disciplined continuously and survives reboots.
- `services/timesync.py` (started from `main.py`): forces a chrony step on
  boot/network-up and, on networks that block NTP (UDP 123), sets the clock from
  an **HTTPS `Date` header** via the narrow sudo helper
  `scripts/upright-set-time` (allowed in `/etc/sudoers.d/upright-timesync`). It
  runs even when chrony isn't installed, as long as the helper is present — so a
  hand-flashed board still self-corrects.

---

## 7. Dev / build / test (macOS)

```bash
cd ~/Downloads/upright/gerd/firmware
python3 -m venv .venv && source .venv/bin/activate   # already exists in the checkout
pip install -e ".[dev]"          # + `ai-edge-litert` to run the food model locally
.venv/bin/python -m pytest -q    # 104 tests, must stay green
.venv/bin/ruff check src tests   # CI runs this too — must be clean
python -m upright.main --dry-run # run the firmware off-Pi
```

**Simulator** (runs the *real* firmware with a simulated HAL + browser bench +
HTTP control API — the best way to verify UI/flows without hardware):
```bash
cd ~/Downloads/upright/gerd/simulator
../firmware/.venv/bin/python run.py --port 8000   # open http://127.0.0.1:8000
```
Drive it over HTTP: `POST /api/button {button,pattern}`, `/api/posture`,
`/api/camera/frame` (raw JPEG), `/api/command {command}`; read `/api/state`,
`/screen.png`. See `simulator/README.md`.

CI = `ruff check firmware/src firmware/tests` + `pytest`. Keep both green.

---

## 8. Deploying to the Pi

There are **two** deploy paths. Prefer the first.

### A. On the Pi (recommended — applies system config too)
```bash
cd ~/upright && git pull && sudo bash install.sh && sudo reboot
```
This pulls code + the bundled model, installs the `ai-edge-litert` runtime, and
applies the system-level pieces (captive-portal dnsmasq config, chrony,
sudoers + time helper). The food model and the timesync HTTP fallback work from
code alone, but **the captive portal and chrony only fully activate after
`install.sh` runs on the Pi.**

### B. Flash the SD card from macOS (offline, no Pi boot needed)
The Pi rootfs is **ext4**, which macOS can't mount — use `e2fsprogs`/`e2tools`.

```bash
# tools (installed via Homebrew):
export PATH="/usr/local/opt/e2fsprogs/sbin:/usr/local/opt/e2fsprogs/bin:$PATH"
#   e2fsck, debugfs live there; e2cp / e2mkdir / e2ls live in /usr/local/bin

SD=/dev/disk8s2          # ext4 rootfs (the Linux partition; check `diskutil list`)
                         # bootfs (FAT) auto-mounts at /Volumes/bootfs — edit directly

# sudo on this Mac needs Touch ID, which only surfaces when the Bash sandbox is
# OFF. In Claude Code: run Bash with dangerouslyDisableSandbox: true.

sudo e2fsck -fy "$SD"                                   # ALWAYS before & after writing
# read:  sudo debugfs -R "cat /path" "$SD"   (batch many: debugfs -f cmds.txt "$SD")
# write: sudo e2cp -O 1000 -G 1000 -P 0644 local "$SD:/home/softhoarders/upright/…"
#        (use -O 0 -G 0 for root-owned files under /etc, /usr/local/sbin)
# mkdir: sudo e2mkdir "$SD:/path/to/dir"
sudo e2fsck -fn "$SD"; sync; diskutil eject disk8       # finish clean, then eject
```

Things already vendored onto the SD this way (since the Pi was offline / to avoid
re-running install): the food **model**, the **`ai_edge_litert`** runtime
(cp313/aarch64 wheel extracted into `…/.venv/lib/python3.13/site-packages/`),
**`segno`**, the captive-portal/chrony/sudoers config, the `upright-set-time`
helper, and the `SoftHoarders Wi-Fi` NM profile. Verify writes by md5-comparing
files read back with `e2cp` against the repo.

> Editable install: the Pi venv uses a lax `.pth` pointing at
> `~/upright/firmware/src`, so **new Python modules are importable without a
> reinstall** — copying a `.py` file in is enough.

---

## 9. Connecting to the Pi (SSH + finding it on the LAN)

```bash
ssh softhoarders@softhoarders-pi.local         # if mDNS resolves
# the Mac's key is already in the Pi's authorized_keys
```
If mDNS doesn't resolve (common on some networks), find it by IP. **Both machines
must be on the same network/subnet.**
```bash
# scan the local /24 for SSH, then key-auth probe to find the Pi by hostname:
for i in $(seq 1 254); do (nc -G1 -z -w1 192.168.0.$i 22 2>/dev/null && echo .$i) & done; wait
for ip in <candidates>; do
  ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=4 \
      softhoarders@192.168.0.$ip 'hostname' 2>/dev/null
done   # the Pi answers "softhoarders-pi"
```
See `PI_REMOTE_RUNBOOK.md` for service/ops commands once connected.

---

## 10. Status summary & prioritized next steps

**Done & on `main`:** real food classifier + runtime, mDNS, captive-portal Wi-Fi
setup page, clock sync, AP hardening. 104 tests pass, ruff clean. Model + runtime
+ config flashed to the SD; `SoftHoarders Wi-Fi` + SSH key in place.

**Not yet verified on hardware:** the `UpRight-Setup` AP actually broadcasting,
and the food model running on-device (both need a booted, reachable Pi).

**Do next, in order:**
1. **Get SSH on the Pi.** Put the controlling machine on the **same network** the
   Pi joined (`SoftHoarders Wi-Fi`), or use the IP shown on the device's
   Settings → Network screen. Confirm 2.4 GHz (the Pi is 2.4 GHz-only).
2. **Verify the food flow on-device:** trigger a food photo, confirm
   `ai_edge_litert` loads and a dish is recognized. (`journalctl -u upright -f`.)
3. **Fix the setup AP live** using the §5 commands; confirm `UpRight-Setup`
   beacons and a phone can join + auto-open the portal. Update `wifi.start_ap()`
   based on the real `nmcli`/`dmesg` error and add a regression test.
4. **Enable persistent journald** so future failures are debuggable.
5. Push every change to `main`; keep `pytest` + `ruff` green.

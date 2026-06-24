#!/usr/bin/env bash
# UpRight — one-shot installer for Raspberry Pi OS Lite (bookworm or later).
#
# Run once on a fresh Pi Zero 2 W:
#
#   curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
#
# What this does:
#   1. installs system packages (i2c-tools, fswebcam, avahi-daemon, etc.)
#   2. enables I²C and I²S in /boot/config.txt
#   3. clones or updates the repo into /home/$USER/upright
#   4. creates a venv, installs the Python package with Pi extras
#   5. enables mDNS (avahi) so the device is reachable at <hostname>.local
#   6. installs and enables the two systemd units (upright + upright-web)
#
# Wi-Fi: with no network configured, the device raises a temporary "UpRight-Setup"
# access point — scan the Wi-Fi QR on its screen to join, open http://10.42.0.1,
# and pick your network. (You can also pre-seed Wi-Fi with Raspberry Pi Imager.)
# Afterwards add/switch networks from the dashboard → Settings → Network.
#
# Idempotent — safe to re-run after a `git pull` to pick up updates.

set -euo pipefail

REPO_URL="${UPRIGHT_REPO_URL:-https://github.com/david-constantinescu/gerd.git}"
INSTALL_USER="${SUDO_USER:-$USER}"
INSTALL_HOME="$(eval echo ~"$INSTALL_USER")"
INSTALL_DIR="${UPRIGHT_DIR:-$INSTALL_HOME/upright}"
BRANCH="${UPRIGHT_BRANCH:-main}"

log() { printf '\033[1;34m[upright]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[upright]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[upright]\033[0m %s\n' "$*" >&2; exit 1; }

need_root() {
  if [[ $EUID -ne 0 ]]; then
    log "re-executing under sudo…"
    exec sudo -E bash "$0" "$@"
  fi
}

need_root "$@"

if ! command -v apt-get >/dev/null 2>&1; then
  die "this installer only supports Raspberry Pi OS / Debian."
fi

# -------------------------------------------------- 1. clone / update repo (need scripts before hardware stack)
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends git ca-certificates

# -------------------------------------------------- 2. clone / update repo
if [[ -d $INSTALL_DIR/.git ]]; then
  log "updating existing checkout at $INSTALL_DIR"
  sudo -u "$INSTALL_USER" git -C "$INSTALL_DIR" fetch --quiet origin
  sudo -u "$INSTALL_USER" git -C "$INSTALL_DIR" checkout --quiet "$BRANCH"
  sudo -u "$INSTALL_USER" git -C "$INSTALL_DIR" pull --quiet --ff-only origin "$BRANCH"
else
  log "cloning $REPO_URL → $INSTALL_DIR"
  sudo -u "$INSTALL_USER" git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi
chown -R "$INSTALL_USER":"$INSTALL_USER" "$INSTALL_DIR"

# -------------------------------------------------- 3. hardware stack (apt, buses, venv, systemd)
if [[ -f $INSTALL_DIR/scripts/pi-install-hardware-stack.sh ]]; then
  chmod +x "$INSTALL_DIR/scripts/pi-install-hardware-stack.sh"
  INSTALL_USER="$INSTALL_USER" INSTALL_DIR="$INSTALL_DIR" \
    bash "$INSTALL_DIR/scripts/pi-install-hardware-stack.sh"
  HW_STACK_RAN=1
else
  HW_STACK_RAN=0
  log "installing minimal packages (hardware script missing)…"
  apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip python3-dev \
    python3-pil python3-numpy python3-smbus2 python3-spidev python3-rpi-lgpio python3-luma.oled \
    i2c-tools v4l-utils alsa-utils fswebcam avahi-daemon network-manager build-essential
fi

if [[ ${HW_STACK_RAN:-0} -eq 0 ]]; then
  log "creating python venv"
  sudo -u "$INSTALL_USER" python3 -m venv --system-site-packages "$INSTALL_DIR/.venv"
  sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip wheel
  sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q \
    -e "$INSTALL_DIR/firmware[pi]" || {
      sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q \
        flask gunicorn pillow numpy smbus2 spidev luma.oled luma.lcd watchdog
      sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q \
        -e "$INSTALL_DIR/firmware" --no-deps
    }
fi

# -------------------------------------------------- 4. local-network access (mDNS)
# The dashboard binds 0.0.0.0:80 and is reachable at http://<hostname>.local
# once avahi advertises it. Networks are managed by NetworkManager (Bookworm
# default) — add/switch Wi-Fi from the dashboard → Settings → Network.
log "enabling mDNS (avahi) + NetworkManager"
systemctl enable --now avahi-daemon 2>/dev/null || warn "avahi-daemon not enabled (install it: apt install avahi-daemon)"
systemctl enable --now NetworkManager 2>/dev/null || true

# CRITICAL: hand wlan0 to NetworkManager. Raspberry Pi Imager / some Debian
# images configure Wi-Fi the old `ifupdown` way in /etc/network/interfaces and
# leave NetworkManager `managed=false`, so NM never controls the radio — the
# entire nmcli-based Wi-Fi stack (setup AP + Settings → Network) silently can't
# touch wlan0. Migrate any ifupdown wlan config into an NM keyfile and let NM
# manage the device.
log "handing wlan0 to NetworkManager (migrating any ifupdown Wi-Fi)"
if [[ -f /etc/network/interfaces ]] && grep -qE '^\s*(auto|allow-hotplug|iface)\s+wlan0' /etc/network/interfaces; then
  ssid=$(grep -E '^\s*wpa-ssid' /etc/network/interfaces | head -1 | sed -E 's/^\s*wpa-ssid\s+"?([^"]*)"?\s*$/\1/')
  psk=$(grep -E '^\s*wpa-psk' /etc/network/interfaces | head -1 | sed -E 's/^\s*wpa-psk\s+"?([^"]*)"?\s*$/\1/')
  # strip wlan0 stanza so ifupdown stops claiming the radio
  awk 'BEGIN{skip=0}
       /^[[:space:]]*(auto|allow-hotplug|iface)[[:space:]]+wlan0/{skip=1; next}
       /^[[:space:]]*(auto|allow-hotplug|iface)[[:space:]]+/{skip=0}
       skip==1 && /^[[:space:]]+/ {next}
       {skip=0; print}' /etc/network/interfaces > /etc/network/interfaces.upright && \
    mv /etc/network/interfaces.upright /etc/network/interfaces
  if [[ -n "${ssid:-}" ]] && ! nmcli -t -f NAME connection show 2>/dev/null | grep -qxF "$ssid"; then
    log "  migrating ifupdown Wi-Fi '$ssid' to a NetworkManager profile"
    nmcli connection add type wifi con-name "$ssid" ssid "$ssid" \
      wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$psk" connection.autoconnect yes 2>/dev/null || \
      warn "  could not migrate '$ssid' — add it from Settings → Network"
  fi
fi
# Force NM to manage all devices (overrides [ifupdown] managed=false).
install -d -m 0755 /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/10-upright-manage-wifi.conf <<EOF
# UpRight: NetworkManager must own wlan0 for the setup AP + Wi-Fi UI to work.
[ifupdown]
managed=true
[device]
wifi.scan-rand-mac-address=no
EOF
systemctl reload-or-restart NetworkManager 2>/dev/null || true

# Captive portal for the setup AP: make NetworkManager's shared-mode dnsmasq
# resolve every domain to the gateway, so a phone that joins "UpRight-Setup"
# auto-pops its sign-in page straight onto the Wi-Fi picker (no URL to type).
# Only affects shared (AP) connections — normal client Wi-Fi DNS is untouched.
log "configuring setup-AP captive portal (dnsmasq DNS redirect)"
install -d -m 0755 /etc/NetworkManager/dnsmasq-shared.d
cat > /etc/NetworkManager/dnsmasq-shared.d/upright-captive.conf <<EOF
# UpRight setup AP captive portal — resolve all names to the gateway.
address=/#/10.42.0.1
EOF

# -------------------------------------------------- 4b. keep the clock correct
# The Pi Zero 2 W has no RTC: without active time sync the clock starts at the
# last-saved value and drifts/lags. chrony disciplines it continuously whenever
# online (stepping immediately, even when far off); fake-hwclock preserves it
# across reboots so it never jumps back to 1970.
log "setting up time sync (chrony + fake-hwclock)"
apt-get install -y --no-install-recommends chrony fake-hwclock 2>/dev/null || \
  warn "could not install chrony/fake-hwclock — check apt"
install -d -m 0755 /etc/chrony/conf.d
cat > /etc/chrony/conf.d/upright.conf <<EOF
# Step the clock immediately whenever it is wrong (no RTC on the Pi Zero).
makestep 1 -1
pool pool.ntp.org iburst
EOF
systemctl enable --now chrony 2>/dev/null || systemctl enable --now chronyd 2>/dev/null || true
systemctl enable --now fake-hwclock 2>/dev/null || true
timedatectl set-ntp true 2>/dev/null || true

# Let the (non-root) firmware nudge a resync when the network comes up, and set
# the clock from an HTTP Date header on networks that block NTP (UDP 123).
if [[ -f $INSTALL_DIR/scripts/upright-set-time ]]; then
  install -m 0755 "$INSTALL_DIR/scripts/upright-set-time" /usr/local/sbin/upright-set-time
  cat > /etc/sudoers.d/upright-timesync <<EOF
$INSTALL_USER ALL=(root) NOPASSWD: /usr/local/sbin/upright-set-time, /usr/bin/chronyc -a makestep, /usr/bin/chronyc makestep
EOF
  chmod 0440 /etc/sudoers.d/upright-timesync
fi

# Boot-time Wi-Fi diagnostic → writes <boot>/upright-netdiag.txt each boot so the
# real NetworkManager/radio state can be read off the SD's boot partition from
# any computer (no SSH needed) when networking misbehaves.
if [[ -f $INSTALL_DIR/scripts/upright-netdiag.sh ]]; then
  log "installing boot Wi-Fi diagnostic (upright-netdiag)"
  install -m 0755 "$INSTALL_DIR/scripts/upright-netdiag.sh" /usr/local/sbin/upright-netdiag
  install -m 0644 "$INSTALL_DIR/firmware/systemd/upright-netdiag.service" \
    /etc/systemd/system/upright-netdiag.service
  systemctl daemon-reload
  systemctl enable upright-netdiag.service 2>/dev/null || true
fi

# -------------------------------------------------- 5. systemd units (if hardware stack did not already install them)
if [[ ${HW_STACK_RAN:-0} -eq 0 ]]; then
  log "installing systemd units"
  install -m 0644 "$INSTALL_DIR/firmware/systemd/upright.service"     /etc/systemd/system/upright.service
  install -m 0644 "$INSTALL_DIR/firmware/systemd/upright-web.service" /etc/systemd/system/upright-web.service
  sed -i "s|@USER@|$INSTALL_USER|g; s|@DIR@|$INSTALL_DIR|g" \
    /etc/systemd/system/upright.service \
    /etc/systemd/system/upright-web.service
  systemctl daemon-reload
fi
systemctl enable --now upright.service upright-web.service 2>/dev/null || true

if [[ "${UPRIGHT_INSTALL_TAILSCALE:-0}" == "1" ]] && [[ -f $INSTALL_DIR/scripts/pi-install-tailscale.sh ]]; then
  log "installing Tailscale (UPRIGHT_INSTALL_TAILSCALE=1)…"
  chmod +x "$INSTALL_DIR/scripts/pi-install-tailscale.sh"
  TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}" TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-upright-pi}" \
    bash "$INSTALL_DIR/scripts/pi-install-tailscale.sh" || warn "Tailscale install failed — run scripts/pi-install-tailscale.sh manually"
fi

log "done!"
log ""
log "Next steps:"
log "  • reboot once so I²C / I²S come up: sudo reboot"
log "  • FIRST-TIME Wi-Fi: scan the 'UpRight-Setup' QR on the device screen to"
log "    join it, open http://10.42.0.1, and choose your network"
log "  • after that, open  http://$(hostname).local  on the same Wi-Fi"
log "    (or use the device's IP — check with: hostname -I)"
log "  • add/switch Wi-Fi later from the dashboard → Settings → Network"
log "  • remote access: see reference docs/TAILSCALE.md (optional)"
log "  • follow logs:  journalctl -u upright -f"

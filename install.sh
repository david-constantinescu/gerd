#!/usr/bin/env bash
# UpRight — one-shot installer for Raspberry Pi OS Lite (bookworm or later).
#
# Run once on a fresh Pi Zero 2 W:
#
#   curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
#
# What this does:
#   1. installs system packages (i2c-tools, hostapd, dnsmasq, fswebcam, etc.)
#   2. enables I²C and I²S in /boot/config.txt
#   3. clones or updates the repo into /home/$USER/upright
#   4. creates a venv, installs the Python package with Pi extras
#   5. lays down hostapd + dnsmasq configs for the UpRight-AP hotspot
#   6. installs and enables the two systemd units (upright + upright-web)
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
    i2c-tools v4l-utils alsa-utils fswebcam hostapd dnsmasq iptables build-essential
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

# -------------------------------------------------- 4. hotspot configs
log "writing hostapd + dnsmasq configs for UpRight-AP"
cat > /etc/hostapd/hostapd.conf <<EOF
interface=wlan0
driver=nl80211
ssid=UpRight-AP
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=upright123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
sed -i 's|#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd 2>/dev/null || true

cat > /etc/dnsmasq.d/upright.conf <<'EOF'
interface=wlan0
dhcp-range=192.168.1.50,192.168.1.150,255.255.255.0,24h
address=/#/192.168.1.1
EOF

# Static IP for wlan0
if ! grep -q "interface wlan0" /etc/dhcpcd.conf 2>/dev/null; then
  cat >> /etc/dhcpcd.conf <<'EOF'

# UpRight hotspot
interface wlan0
static ip_address=192.168.1.1/24
nohook wpa_supplicant
EOF
fi

systemctl unmask hostapd 2>/dev/null || true

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

log "done!"
log ""
log "Next steps:"
log "  • reboot once so I²C / I²S come up: sudo reboot"
log "  • join 'UpRight-AP' wifi (password: upright123)"
log "  • open http://192.168.1.1 in your phone browser"
log "  • follow logs:  journalctl -u upright -f"

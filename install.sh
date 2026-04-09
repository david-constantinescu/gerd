#!/usr/bin/env bash
# Reflux Sentinel — one-shot installer for Raspberry Pi OS Lite (bookworm or later).
#
# Run once on a fresh Pi Zero 2 W:
#
#   curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
#
# What this does:
#   1. installs system packages (i2c-tools, hostapd, dnsmasq, fswebcam, etc.)
#   2. enables I²C and I²S in /boot/config.txt
#   3. clones or updates the repo into /home/$USER/reflux-sentinel
#   4. creates a venv, installs the Python package with Pi extras
#   5. lays down hostapd + dnsmasq configs for the Sentinel-AP hotspot
#   6. installs and enables the two systemd units (sentinel + sentinel-web)
#
# Idempotent — safe to re-run after a `git pull` to pick up updates.

set -euo pipefail

REPO_URL="${SENTINEL_REPO_URL:-https://github.com/david-constantinescu/gerd.git}"
INSTALL_USER="${SUDO_USER:-$USER}"
INSTALL_HOME="$(eval echo ~"$INSTALL_USER")"
INSTALL_DIR="${SENTINEL_DIR:-$INSTALL_HOME/reflux-sentinel}"
BRANCH="${SENTINEL_BRANCH:-main}"

log() { printf '\033[1;34m[sentinel]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[sentinel]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[sentinel]\033[0m %s\n' "$*" >&2; exit 1; }

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

# -------------------------------------------------- 1. system packages
log "installing system packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  git ca-certificates \
  python3 python3-venv python3-pip python3-dev \
  i2c-tools libatlas-base-dev \
  alsa-utils fswebcam \
  hostapd dnsmasq iptables \
  build-essential

# -------------------------------------------------- 2. enable I²C / I²S
CFG=/boot/firmware/config.txt
[[ -f $CFG ]] || CFG=/boot/config.txt
log "enabling I²C and I²S in $CFG"
grep -q '^dtparam=i2c_arm=on' "$CFG" || echo 'dtparam=i2c_arm=on' >> "$CFG"
grep -q '^dtparam=i2s=on'     "$CFG" || echo 'dtparam=i2s=on'     >> "$CFG"
grep -q '^dtoverlay=hifiberry-dac' "$CFG" || echo 'dtoverlay=hifiberry-dac' >> "$CFG"
modprobe i2c-dev || true

# -------------------------------------------------- 3. clone / update repo
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

# -------------------------------------------------- 4. python venv + package
log "creating python venv"
sudo -u "$INSTALL_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip wheel
log "installing reflux-sentinel with Pi extras (this takes a minute)"
sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet \
  -e "$INSTALL_DIR/firmware[pi]" || {
    warn "tflite-runtime wheel may be missing for this arch — continuing without it."
    sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet \
      flask gunicorn pillow numpy smbus2 RPi.GPIO 'luma.oled' watchdog
    sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet \
      -e "$INSTALL_DIR/firmware" --no-deps
}

# -------------------------------------------------- 5. hotspot configs
log "writing hostapd + dnsmasq configs for Sentinel-AP"
cat > /etc/hostapd/hostapd.conf <<EOF
interface=wlan0
driver=nl80211
ssid=Sentinel-AP
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=sentinel123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
sed -i 's|#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd 2>/dev/null || true

cat > /etc/dnsmasq.d/sentinel.conf <<'EOF'
interface=wlan0
dhcp-range=192.168.1.50,192.168.1.150,255.255.255.0,24h
address=/#/192.168.1.1
EOF

# Static IP for wlan0
if ! grep -q "interface wlan0" /etc/dhcpcd.conf 2>/dev/null; then
  cat >> /etc/dhcpcd.conf <<'EOF'

# Reflux Sentinel hotspot
interface wlan0
static ip_address=192.168.1.1/24
nohook wpa_supplicant
EOF
fi

systemctl unmask hostapd 2>/dev/null || true

# -------------------------------------------------- 6. systemd units
log "installing systemd units"
install -m 0644 "$INSTALL_DIR/firmware/systemd/sentinel.service"     /etc/systemd/system/sentinel.service
install -m 0644 "$INSTALL_DIR/firmware/systemd/sentinel-web.service" /etc/systemd/system/sentinel-web.service

# Substitute user + install dir into unit files
sed -i "s|@USER@|$INSTALL_USER|g; s|@DIR@|$INSTALL_DIR|g" \
  /etc/systemd/system/sentinel.service \
  /etc/systemd/system/sentinel-web.service

systemctl daemon-reload
systemctl enable --now sentinel.service
systemctl enable --now sentinel-web.service

log "done!"
log ""
log "Next steps:"
log "  • reboot once so I²C / I²S come up: sudo reboot"
log "  • join 'Sentinel-AP' wifi (password: sentinel123)"
log "  • open http://192.168.1.1 in your phone browser"
log "  • follow logs:  journalctl -u sentinel -f"

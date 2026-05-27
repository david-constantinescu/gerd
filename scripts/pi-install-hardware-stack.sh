#!/usr/bin/env bash
# Install every system + Python dependency UpRight might need on a Pi.
# Safe to re-run. Run on the Pi as root:
#   sudo bash scripts/pi-install-hardware-stack.sh
#
# Enables buses (I²C, SPI, I²S), kernel modules, apt packages, and a venv
# with Pi HAL libraries. Display kernel overlays are written to a separate
# file — enable ONE panel overlay there, then reboot.

set -euo pipefail

INSTALL_USER="${INSTALL_USER:-${SUDO_USER:-$USER}}"
INSTALL_HOME="$(eval echo ~"$INSTALL_USER")"
INSTALL_DIR="${INSTALL_DIR:-$INSTALL_HOME/upright}"

log() { printf '\033[1;34m[upright-hw]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[upright-hw]\033[0m %s\n' "$*" >&2; }

if [[ $EUID -ne 0 ]]; then
  exec sudo INSTALL_USER="$INSTALL_USER" INSTALL_DIR="$INSTALL_DIR" bash "$0" "$@"
fi

export DEBIAN_FRONTEND=noninteractive

log "apt update"
apt-get update -qq

log "installing system packages (I²C, SPI, camera, audio, GPIO, web)…"
apt-get install -y --no-install-recommends \
  git ca-certificates curl \
  python3 python3-venv python3-pip python3-dev python3-setuptools \
  python3-pil python3-numpy python3-flask \
  python3-smbus2 python3-spidev \
  python3-rpi-lgpio python3-libgpiod \
  python3-luma.core python3-luma.oled python3-luma.lcd \
  i2c-tools \
  v4l-utils fswebcam \
  alsa-utils \
  gpiod \
  hostapd dnsmasq iptables \
  build-essential \
  libjpeg62-turbo-dev zlib1g-dev libopenjp2-7 \
  2>&1 | tail -5

# Optional camera stack (ignore if unavailable on this OS image)
apt-get install -y --no-install-recommends libcamera-apps rpicam-apps 2>/dev/null || true

CFG=/boot/firmware/config.txt
[[ -f $CFG ]] || CFG=/boot/config.txt
OVERLAY_FILE=/boot/firmware/upright-display.conf
[[ -d /boot/firmware ]] || OVERLAY_FILE=/boot/config/upright-display.conf

log "enabling I²C, SPI, I²S in $CFG"
ensure_line() { grep -qF "$1" "$CFG" 2>/dev/null || echo "$1" >> "$CFG"; }
sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' "$CFG" 2>/dev/null || true
sed -i 's/^#dtparam=i2s=on/dtparam=i2s=on/' "$CFG" 2>/dev/null || true
ensure_line 'dtparam=i2c_arm=on'
ensure_line 'dtparam=spi=on'
ensure_line 'dtoverlay=spi0-1cs'
ensure_line 'dtparam=i2s=on'
ensure_line 'dtoverlay=hifiberry-dac'

if ! grep -q 'upright-display.conf' "$CFG" 2>/dev/null; then
  echo "include upright-display.conf" >> "$CFG"
fi

log "writing display overlay options → $OVERLAY_FILE"
cat > "$OVERLAY_FILE" <<'EOF'
# UpRight display — Adafruit ST7735R uses userspace SPI (luma.lcd), NOT fbtft.
# Keep all kernel TFT overlays DISABLED or they grab SPI and break /dev/spidev*.

# --- DO NOT enable fbtft for ST7735R ---
#dtoverlay=fbtft,spi0-0,st7789v,width=240,height=240,reset_pin=25,dc_pin=24,rotate=90

# --- Only enable a kernel overlay if luma SPI fails (uncommon) ---
#dtoverlay=st7735,width=128,height=160,rotate=0
EOF

log "kernel modules at boot"
echo -e "i2c-dev\nspidev" > /etc/modules-load.d/upright.conf
modprobe i2c-dev 2>/dev/null || true
modprobe spidev 2>/dev/null || true

log "adding $INSTALL_USER to i2c, spi, gpio, video, render"
for g in i2c spi gpio video render input; do
  getent group "$g" >/dev/null && usermod -aG "$g" "$INSTALL_USER" || true
done

if [[ -d $INSTALL_DIR/firmware ]]; then
  log "python venv at $INSTALL_DIR/.venv (system-site-packages for apt libs)"
  sudo -u "$INSTALL_USER" python3 -m venv --system-site-packages "$INSTALL_DIR/.venv" 2>/dev/null \
    || sudo -u "$INSTALL_USER" python3 -m venv "$INSTALL_DIR/.venv"
  sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q --upgrade pip wheel

  log "pip: Pi HAL + optional display/camera libs"
  sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q \
    flask gunicorn pillow numpy smbus2 spidev watchdog \
    luma.oled luma.lcd luma.core \
    2>/dev/null || true

  sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q \
    -e "$INSTALL_DIR/firmware[pi]" 2>/dev/null || {
    warn "editable [pi] install failed — installing package without tflite"
    sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q \
      -e "$INSTALL_DIR/firmware" --no-deps
  }

  # tflite is optional
  sudo -u "$INSTALL_USER" "$INSTALL_DIR/.venv/bin/pip" install -q tflite-runtime 2>/dev/null \
    || warn "tflite-runtime not available for this Python — food ML disabled"
fi

log "systemd units"
if [[ -f $INSTALL_DIR/firmware/systemd/upright.service ]]; then
  install -m 0644 "$INSTALL_DIR/firmware/systemd/upright.service" /etc/systemd/system/upright.service
  install -m 0644 "$INSTALL_DIR/firmware/systemd/upright-web.service" /etc/systemd/system/upright-web.service
  sed -i "s|@USER@|$INSTALL_USER|g; s|@DIR@|$INSTALL_DIR|g" \
    /etc/systemd/system/upright.service /etc/systemd/system/upright-web.service
  # Prefer venv if present
  PY="$INSTALL_DIR/.venv/bin/python"
  GUN="/usr/bin/gunicorn"
  [[ -x $INSTALL_DIR/.venv/bin/gunicorn ]] && GUN="$INSTALL_DIR/.venv/bin/gunicorn"
  cat > /etc/systemd/system/upright.service <<EOF
[Unit]
Description=UpRight firmware loop
After=network.target

[Service]
Type=simple
User=$INSTALL_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR/firmware/src
ExecStart=$PY -m upright.main
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  cat > /etc/systemd/system/upright-web.service <<EOF
[Unit]
Description=UpRight Flask PWA
After=network.target upright.service

[Service]
Type=simple
User=$INSTALL_USER
WorkingDirectory=$INSTALL_DIR
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=$GUN -b 0.0.0.0:80 -w 2 --chdir $INSTALL_DIR/firmware/src upright.web.app:app
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable upright upright-web 2>/dev/null || true
fi

log "done — reboot recommended: sudo reboot"
log "If using an SPI TFT: edit $OVERLAY_FILE, uncomment ONE overlay, reboot."

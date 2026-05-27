#!/usr/bin/env bash
# One-time Pi setup — run ON THE PI with sudo (password required once):
#
#   ssh softhoarders@softhoarders-pi.local
#   cd ~/upright && sudo bash scripts/pi-enable-hardware.sh && sudo reboot
#
# Enables I2C + SPI + I2S (MAX98357A), installs system tools, then reboots.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0"
  exit 1
fi

CFG=/boot/firmware/config.txt
[[ -f $CFG ]] || CFG=/boot/config.txt
OVERLAY=/boot/firmware/upright-display.conf
[[ -f $OVERLAY ]] || OVERLAY=/boot/config/upright-display.conf

echo "[upright] enabling I2C + SPI in $CFG (I2S disabled for GPIO20/21 buttons)"
grep -q '^dtparam=i2c_arm=on' "$CFG" || echo 'dtparam=i2c_arm=on' >> "$CFG"
grep -q '^dtparam=spi=on'     "$CFG" || echo 'dtparam=spi=on'     >> "$CFG"
grep -q '^dtoverlay=spi0-1cs' "$CFG" || echo 'dtoverlay=spi0-1cs' >> "$CFG"
# Disable I2S/HifiBerry overlays — these claim GPIO20/21 used by buttons.
sed -i '/^dtparam=i2s=on/s/^/# disabled for buttons: /' "$CFG" || true
sed -i '/^dtoverlay=hifiberry-dac/s/^/# disabled for buttons: /' "$CFG" || true

# Bit-bang I²C for MPU6050 on GPIO 27/28 (does not touch SPI display pins 10/11).
MPU_OVERLAY='dtoverlay=i2c-gpio,i2c_gpio_sda=27,i2c_gpio_scl=3,i2c_gpio_delay_us=2'
if grep -q 'i2c-gpio' "$CFG" 2>/dev/null; then
  if grep -q 'i2c_gpio_sda=10' "$CFG" 2>/dev/null; then
    echo "[upright] replacing old i2c-gpio overlay (was on SPI pins 10/11)"
    sed -i '/i2c-gpio/s/^/# removed SPI conflict: /' "$CFG"
  fi
fi
if ! grep -q 'i2c_gpio_sda=27' "$CFG" 2>/dev/null; then
  if [ "${USE_KERNEL_MPU_I2C:-0}" = "1" ]; then
    echo "[upright] enabling MPU6050 kernel I²C on GPIO 27 (SDA) / 28 (SCL)"
    echo "dtoverlay=$MPU_OVERLAY" >> "$CFG"
  else
    echo "[upright] MPU6050 uses firmware bit-bang on GPIO 27/28 (no kernel i2c-gpio overlay)"
  fi
fi

if [[ -f $OVERLAY ]]; then
  echo "[upright] disabling fbtft kernel display overlays (ST7735R uses userspace SPI)"
  sed -i 's/^dtoverlay=fbtft/#dtoverlay=fbtft/' "$OVERLAY" || true
fi

echo "[upright] installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  i2c-tools fswebcam alsa-utils python3-pil python3-numpy \
  python3-spidev python3-luma.lcd python3-luma.core

modprobe i2c-dev 2>/dev/null || true
modprobe spidev 2>/dev/null || true
echo -e "i2c-dev\nspidev" > /etc/modules-load.d/upright-i2c.conf

echo "[upright] done — reboot required: sudo reboot"

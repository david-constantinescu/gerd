#!/usr/bin/env bash
# Run on the Pi (or via: ssh pi 'bash -s' < scripts/pi-hardware-audit.sh)
# Inventory USB + GPIO + I2C and smoke-test each subsystem.

set -uo pipefail

REPO="${UPRIGHT_DIR:-$HOME/upright}"
FW="$REPO/firmware"
export PYTHONPATH="$FW/src"
I2CDETECT="${I2CDETECT:-/usr/sbin/i2cdetect}"

pass=0
fail=0
skip=0

ok()   { echo "  OK   $*"; pass=$((pass+1)); }
bad()  { echo "  FAIL $*"; fail=$((fail+1)); }
skip() { echo "  SKIP $*"; skip=$((skip+1)); }

echo "========== UpRight hardware audit =========="
echo "Host: $(hostname) | $(tr -d '\0' </proc/device-tree/model 2>/dev/null)"
echo ""

echo "== USB =="
if command -v lsusb >/dev/null; then
  lsusb
  lsusb | grep -qi webcam && ok "USB webcam present" || skip "no USB webcam"
else
  skip "lsusb not installed"
fi
echo ""

echo "== Camera =="
if [ -e /dev/video0 ]; then
  ok "/dev/video0 exists"
  if v4l2-ctl --device=/dev/video0 --stream-mmap --stream-count=1 \
      --stream-to=/tmp/upright_audit.jpg 2>/dev/null \
      && [ -s /tmp/upright_audit.jpg ]; then
    ok "captured test frame ($(wc -c </tmp/upright_audit.jpg) bytes)"
  elif command -v fswebcam >/dev/null; then
    fswebcam -q --no-banner -r 640x480 /tmp/upright_audit.jpg \
      && ok "fswebcam capture" || bad "fswebcam capture failed"
  else
    bad "cannot capture (install fswebcam: sudo apt install fswebcam)"
  fi
else
  bad "no /dev/video0"
fi
echo ""

echo "== Display (Adafruit ST7735R / SPI) =="
if compgen -G "/dev/spidev*" >/dev/null; then
  for dev in /dev/spidev*; do ok "SPI $dev"; done
else
  bad "no /dev/spidev* — enable SPI and disable fbtft overlays, then reboot"
fi
if [ -e /dev/fb0 ]; then
  skip "/dev/fb0 present (kernel fbtft — disable for ST7735R userspace SPI)"
fi
timeout 10 python3 "$FW/scripts/pi_probe_display.py" 2>/dev/null && ok "display probe" || bad "display probe"
timeout 8 python3 "$FW/scripts/oled_hello.py" 2>/dev/null && ok "display hello" || bad "display hello"
echo ""

echo "== SPI scan =="
timeout 10 python3 "$FW/scripts/spi_scan.py" 2>/dev/null | sed 's/^/  /' || bad "spi scan"
echo ""

echo "== I2C =="
if compgen -G "/dev/i2c-*" >/dev/null; then
  for dev in /dev/i2c-*; do
    bus="${dev##*-}"
    ok "$dev present"
    if [ -x "$I2CDETECT" ] || [ -f "$I2CDETECT" ]; then
      echo "  i2cdetect -y $bus:"
      "$I2CDETECT" -y "$bus" | sed 's/^/    /'
    else
      bad "i2cdetect not found (install i2c-tools)"
    fi
  done
  found_sensor=0
  if [ -f "$I2CDETECT" ] || [ -x "$I2CDETECT" ]; then
    for addr in 68:MPU6050 57:MAX30102 3c:OLED; do
      hex="${addr%%:*}"; name="${addr##*:}"
      hit=0
      for dev in /dev/i2c-*; do
        bus="${dev##*-}"
        if "$I2CDETECT" -y "$bus" 2>/dev/null | grep -qE "[[:space:]]${hex}[[:space:]]"; then
          ok "0x$hex $name on bus $bus"
          found_sensor=1
          hit=1
          break
        fi
      done
      [ "$hit" -eq 1 ] || bad "0x$hex $name not seen"
    done
  fi
  if timeout 3 python3 "$FW/scripts/imu_dump.py" 2>/dev/null | head -3 | sed 's/^/    /'; then
    ok "IMU read"
  else
    bad "IMU read (firmware uses stub if missing)"
  fi
  if timeout 3 python3 "$FW/scripts/hrv_dump.py" 2>/dev/null | head -3 | sed 's/^/    /'; then
    ok "HRV read"
  else
    bad "HRV read (firmware uses stub if missing)"
  fi
else
  bad "no /dev/i2c-* — run: sudo raspi-config nonint do_i2c 0 && sudo reboot"
fi
echo ""

echo "== GPIO (BCM) =="
for n in $(seq 0 27); do
  state=$(pinctrl get "$n" 2>/dev/null | head -1 || echo "?")
  echo "  GPIO$n: $state"
done
echo "  (Named: 4=LiPo 5=motor 20=btnA 21=btnB 8/10/11/24/25=SPI display 18/19/21=I2S)"
echo ""

echo "== SPI / serial / PWM =="
if compgen -G "/dev/spidev*" >/dev/null; then
  for dev in /dev/spidev*; do
    echo "  SPI dev: $dev"
  done
else
  echo "  no /dev/spidev* nodes"
fi
for pattern in /dev/ttyAMA* /dev/ttyS*; do
  [ -e "$pattern" ] || continue
  echo "  UART: $pattern"
done
if ! compgen -G "/dev/ttyAMA*" >/dev/null && ! compgen -G "/dev/ttyS*" >/dev/null; then
  echo "  no UART character devices"
fi
if compgen -G "/sys/class/pwm/pwmchip*/device" >/dev/null; then
  for chip in /sys/class/pwm/pwmchip*; do
    [ -d "$chip" ] && echo "  PWM: $chip"
  done
else
  echo "  no PWM controllers exposed"
fi
echo ""

echo "== Battery / power =="
if timeout 5 python3 "$FW/scripts/battery_probe.py" 2>/dev/null; then
  ok "battery probe ran"
else
  bad "battery probe"
fi
echo ""

echo "== GPIO actuators =="
if timeout 8 python3 "$FW/scripts/motor_test.py" 2>/dev/null; then
  ok "motor patterns ran"
else
  bad "motor test"
fi
echo "  (Button/encoder: run manually — press/rotate during test)"
echo ""

echo "== Services =="
systemctl is-active upright >/dev/null 2>&1 && ok "upright.service active" || bad "upright.service"
systemctl is-active upright-web >/dev/null 2>&1 && ok "upright-web.service active" || bad "upright-web.service"
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/ 2>/dev/null || echo 000)
[ "$code" = "200" ] && ok "web UI HTTP $code" || bad "web UI HTTP $code"
echo ""

echo "== Audio =="
aplay -l 2>/dev/null | sed 's/^/  /'
if aplay -l 2>/dev/null | grep -qi hifiberry; then
  ok "I2S amp (hifiberry) detected"
elif aplay -l 2>/dev/null | grep -qi vc4hdmi; then
  skip "only HDMI audio — enable dtoverlay=hifiberry-dac for MAX98357A"
fi
if [ -f "$FW/audio/test.wav" ]; then
  aplay -q "$FW/audio/test.wav" 2>/dev/null && ok "test.wav playback" || bad "test.wav playback"
else
  skip "no firmware/audio/test.wav"
fi
echo ""

echo "========== Summary: $pass ok, $fail fail, $skip skipped =========="
[ "$fail" -eq 0 ] || exit 1

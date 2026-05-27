# Build & bring-up

## Bill of materials (summary)

| Role                | Part                                    |
|---------------------|-----------------------------------------|
| MCU                 | Raspberry Pi Zero 2 W                   |
| IMU                 | MPU6050 (GY-521)                        |
| HRV / pulse         | MAX30102                                |
| Display             | 1.3" SH1106 or SSD1306 128×64 OLED      |
| Audio amp           | MAX98357A I²S                           |
| Speaker             | 28–32 mm 8 Ω 1 W                        |
| Vibration motor     | 10 mm coin, 3 V                         |
| Motor driver        | 2N2222 + 1N4001 flyback diode           |
| Camera              | OV9712 USB UVC module                   |
| Input               | Tactile button + EC11 rotary encoder    |
| Power               | External 10 000 mAh USB-C power bank    |

See [`WIRING.md`](WIRING.md) for the exact pinout.

## Flashing the Pi

1. Raspberry Pi OS Lite (64-bit, bookworm or later).
2. In `rpi-imager` advanced options: enable SSH, set hostname `upright`,
   preload your home WiFi credentials.
3. Boot the Pi, SSH in, then:

```bash
curl -fsSL https://raw.githubusercontent.com/david-constantinescu/gerd/main/install.sh | bash
sudo reboot
```

## Bring-up order

Wire one sensor at a time, validate with the matching script, then move on.

```bash
# Sanity check — should list 0x3C (OLED), 0x68 (MPU6050), 0x57 (MAX30102)
python3 firmware/scripts/i2c_scan.py

# OLED
python3 firmware/scripts/oled_hello.py

# IMU
python3 firmware/scripts/imu_dump.py

# HRV
python3 firmware/scripts/hrv_dump.py

# Button (GPIO 4)
python3 firmware/scripts/button_test.py

# Encoder (GPIO 17/27/22) — 10 nF caps are MANDATORY on CLK/DT
python3 firmware/scripts/encoder_test.py

# Vibration motor (GPIO 5 via 2N2222)
python3 firmware/scripts/motor_test.py

# I²S audio amp
python3 firmware/scripts/play_test_wav.py

# USB camera
python3 firmware/scripts/camera_test.py
```

Once every script passes, start the full firmware loop:

```bash
sudo systemctl restart upright upright-web
journalctl -u upright -f
```

## Power

The device has no internal battery on purpose. A short coiled USB-C cable
connects it to a 10 000 mAh power bank in a nearby pocket, with an XT30
quick-swap connector so you can rotate banks without rebooting the Pi.

Expected runtime on a single 10 Ah bank:

| Mode                     | Draw        | Runtime   |
|--------------------------|-------------|-----------|
| IDLE, hotspot off        | ~130 mA     | ~65 h     |
| IDLE, hotspot on         | ~200 mA     | ~42 h     |
| SLEEPING (0.03 Hz IMU)   | ~80 mA      | ~106 h    |
| Food photo burst          | ~500 mA     | ~15 s / capture |

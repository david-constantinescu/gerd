# Wiring — Pi Zero 2 W pinout

The canonical source is `reference docs/reflux sentinel wiring diagram.pdf`.
Condensed version:

## I²C — MPU6050 (accelerometer / posture)

Bit-bang bus via device-tree overlay (not the header SDA/SCL on GPIO 2/3):

| Signal | Pi pin (BCM) | Notes                          |
|--------|--------------|--------------------------------|
| SDA    | GPIO **27**  | `dtoverlay=i2c-gpio,...sda=27` |
| SCL    | GPIO **28**  | `dtoverlay=i2c-gpio,...scl=28` |
| INT    | GPIO **13**  | optional; firmware polls IMU   |
| VCC    | 3V3          |                                |
| GND    | GND          |                                |

Run `sudo bash scripts/pi-enable-hardware.sh` once, then reboot. Expected
`i2cdetect` on the new bus: **`0x68`** (MPU6050).

## I²C bus (shared — MAX30102, OLED) — optional / not on this build

| Signal | Pi pin (BCM) | Notes                                    |
|--------|--------------|------------------------------------------|
| SDA    | GPIO 2       | pull-up already on every breakout        |
| SCL    | GPIO 3       |                                          |
| VCC    | 3V3          | all three devices are 3.3 V              |
| GND    | GND          |                                          |

Expected `i2cdetect -y 1` output: `0x3C`, `0x57`, `0x68`.

## I²S audio (MAX98357A)

| Signal | Pi pin (BCM) |
|--------|--------------|
| BCLK   | GPIO 18      |
| LRCLK  | GPIO 19      |
| DIN    | GPIO 21      |
| VIN    | 5V           |
| GND    | GND          |
| GAIN   | GND (9 dB)   |
| SD     | VIN          |

Enable I²S in `/boot/firmware/config.txt`:

```
dtparam=i2s=on
dtoverlay=hifiberry-dac
```

## Direct GPIO

| Device          | Pin (BCM) | Notes                                    |
|-----------------|-----------|------------------------------------------|
| Button A (back) | 20        | active low, internal pull-up             |
| Button B (menu) | 21        | active low, internal pull-up             |
| Vibration motor | 22        | physical pin 15 (motor IN)               |
| LiPo alert      | 4         | Pimoroni Zero LiPo (active low)          |

No rotary encoder on this build. UI controls: see `oled-mockups.md`.

## USB camera

OV9712 connects via USB OTG. Use a right-angle micro-USB adapter; power is
drawn through the OTG port when the firmware turns the camera on.

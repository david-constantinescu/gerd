# Wiring — Pi Zero 2 W pinout

The canonical source is `reference docs/reflux sentinel wiring diagram.pdf`.
Condensed version:

## I²C bus (shared — MPU6050, MAX30102, OLED)

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
| Vibration motor | 5         | via 2N2222 base + 1N4001 flyback diode   |
| LiPo alert      | 4         | Pimoroni Zero LiPo (active low)          |

No rotary encoder on this build. UI controls: see `oled-mockups.md`.

## USB camera

OV9712 connects via USB OTG. Use a right-angle micro-USB adapter; power is
drawn through the OTG port when the firmware turns the camera on.

"""Central configuration: pins, addresses, thresholds, file paths.

Values can be overridden at runtime by ``data/config.json`` (hot-reloaded by
``services.hotspot`` via watchdog when running on the Pi).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent
FIRMWARE_ROOT = PKG_ROOT.parent.parent  # firmware/
DATA_DIR = FIRMWARE_ROOT / "data"
AUDIO_DIR = FIRMWARE_ROOT / "audio"
MODELS_DIR = FIRMWARE_ROOT / "models"

DB_PATH = DATA_DIR / "upright.db"
CONFIG_PATH = DATA_DIR / "config.json"
FOODS_PATH = DATA_DIR / "foods.json"
TFLITE_MODEL_PATH = MODELS_DIR / "food_mobilenetv2_quant.tflite"


# --- Pins (BCM numbering) ---------------------------------------------------

PIN_BUTTON_A = 20  # physical header pin 38
PIN_BUTTON_B = 21  # physical header pin 40 — also Pi I2S DIN; see docs
PIN_LIPO_ALERT = 4  # Pimoroni Zero LiPo low-battery alert (active low)
PIN_MOTOR = 22  # physical header pin 15 (motor IN)
PIN_ENCODER_CLK = 17
PIN_ENCODER_DT = 27  # also MPU6050 SDA (bit-bang I²C) — encoder not fitted
PIN_ENCODER_SW = 22  # unused — encoder not fitted; shares BCM 22 with motor
# MPU6050 bit-bang I²C. SCL must NOT be GPIO 28 on Pi Zero 2 W (SDIO — "GPIO busy").
PIN_MPU6050_SDA = 27
PIN_MPU6050_SCL = 3  # header pin 5; was 28 in early docs (invalid on Zero 2 W)
PIN_MPU6050_INT = 13  # optional data-ready; polling used for now
# Legacy header I²C (unused on this build — sensors on GPIO 27/28).
PIN_I2C_SDA = 2
PIN_I2C_SCL = 3
PIN_I2S_BCLK = 18
PIN_I2S_LRC = 19
PIN_I2S_DIN = 21

# Prefer firmware bit-bang on GPIO 27/28 (see hal/i2c_bitbang.py). Kernel overlay optional.
MPU_I2C_GPIO_OVERLAY = "i2c-gpio,i2c_gpio_sda=27,i2c_gpio_scl=3,i2c_gpio_delay_us=5"
USE_KERNEL_MPU_I2C = False
# MOSI=10, SCLK=11, CE0=8 — CS handled by spidev; DC/RST below.

SPI_DISPLAY_PORT = 0
SPI_DISPLAY_DEVICE = 0
SPI_DISPLAY_DC = 25
SPI_DISPLAY_RST = 24
SPI_DISPLAY_BL = -1  # leave to display driver; set a GPIO number only if needed
SPI_DISPLAY_WIDTH = 128
SPI_DISPLAY_HEIGHT = 128
SPI_DISPLAY_H_OFFSET = 0
SPI_DISPLAY_V_OFFSET = 0


# --- I2C addresses ---------------------------------------------------------

I2C_ADDR_MPU6050 = 0x68
I2C_ADDR_MAX30102 = 0x57
I2C_ADDR_OLED = 0x3C  # SH1106 modules sometimes use 0x3D


# --- OLED ------------------------------------------------------------------

OLED_WIDTH = 128
OLED_HEIGHT = 64
# Legacy constant; display blanking uses Tunables.display_blank_minutes at runtime.
OLED_AUTO_BLANK_SECONDS = 0

# SPI TFT: minimum seconds between full-frame paints (reduces visible scan “wave”).
DISPLAY_MIN_REFRESH_SECONDS = 120.0
# Watch-face pitch/posture line can refresh more often.
DISPLAY_PITCH_REFRESH_SECONDS = 1.0


# --- Tunables (overridable via config.json) --------------------------------


@dataclass
class Tunables:
    # Posture — tuned for GERD (see reference docs/posture-detection.md)
    # Daytime: trunk slouch ~12°+; post-meal: stricter ~8°; lying flat ~55°+ is worst.
    pitch_alert_deg: float = 12.0
    pitch_alert_strict_deg: float = 8.0  # POST_MEAL slouch
    pitch_sustained_seconds: float = 45.0
    lying_flat_deg: float = 55.0  # torso near horizontal (post-meal reflux risk)
    lying_sustained_seconds: float = 20.0  # after lying_grace_seconds
    posture_sample_hz_idle: float = 2.0
    posture_sample_hz_post_meal: float = 5.0
    posture_sample_hz_sleep: float = 0.03  # one sample every ~33s

    # Posture score mapping (display + slouch logic)
    posture_deadzone_deg: float = 5.0
    posture_pct_slope: float = 1.5  # gentler fall-off than legacy 3.0
    imu_smooth_alpha: float = 0.18  # EMA weight for new accel samples (lower = smoother)
    pitch_display_alpha: float = 0.25  # extra UI smoothing in the mode manager

    # Alerts
    alert_cooldown_seconds: float = 300.0
    lying_grace_seconds: float = 120.0
    voice_alerts_enabled: bool = True
    haptic_alerts_enabled: bool = True

    # Meal window
    post_meal_default_hours: float = 2.5

    # Sleep
    sleep_window_start: str = "23:00"
    sleep_window_end: str = "07:00"
    sleep_pre_stillness_minutes: float = 10.0
    sleep_max_nudges: int = 3
    sleep_nudge_gap_seconds: float = 300.0
    wear_side: str = "left"  # left | right | center

    # Camera / TFLite
    food_min_confidence: float = 0.60

    # Hotspot
    hotspot_ssid: str = "UpRight-AP"
    hotspot_password: str = "upright123"  # change on first boot
    hotspot_ip: str = "192.168.1.1"
    hotspot_schedule_on: str = "07:00"
    hotspot_schedule_off: str = "23:00"
    hotspot_mode: str = "always"  # always | scheduled | manual

    # UI
    language: str = "en"
    demo_mode: bool = False  # synthetic week dataset; see services.demo_seed
    display_blank_minutes: float = 15.0  # blank TFT after inactivity; any button wakes
    button_double_gap_s: float = 0.40  # pause after last release before classifying tap
    button_multi_tap_window_s: float = 0.60  # wait this long for a 2nd tap before single

    # Web control panel (change on first boot in production)
    web_username: str = "softhoarders"
    web_password: str = "0031"

    @classmethod
    def load(cls, path: Path | None = None) -> Tunables:
        p = path or CONFIG_PATH
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return cls()
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in valid})

    def save(self, path: Path | None = None) -> None:
        p = path or CONFIG_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2))


# Singleton — mutated in place by reload_tunables so existing `from .config
# import TUNABLES` references stay valid after a settings change.
TUNABLES: Tunables = Tunables()


def reload_tunables() -> Tunables:
    """Re-read ``config.json`` from disk into the module-level singleton."""
    fresh = Tunables.load()
    for f in fields(Tunables):
        setattr(TUNABLES, f.name, getattr(fresh, f.name))
    return TUNABLES

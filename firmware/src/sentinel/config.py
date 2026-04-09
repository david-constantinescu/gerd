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

DB_PATH = DATA_DIR / "sentinel.db"
CONFIG_PATH = DATA_DIR / "config.json"
FOODS_PATH = DATA_DIR / "foods.json"
TFLITE_MODEL_PATH = MODELS_DIR / "food_mobilenetv2_quant.tflite"


# --- Pins (BCM numbering) ---------------------------------------------------

PIN_BUTTON = 4
PIN_MOTOR = 5
PIN_ENCODER_CLK = 17
PIN_ENCODER_DT = 27
PIN_ENCODER_SW = 22
PIN_I2C_SDA = 2
PIN_I2C_SCL = 3
PIN_I2S_BCLK = 18
PIN_I2S_LRC = 19
PIN_I2S_DIN = 21


# --- I2C addresses ---------------------------------------------------------

I2C_ADDR_MPU6050 = 0x68
I2C_ADDR_MAX30102 = 0x57
I2C_ADDR_OLED = 0x3C  # SH1106 modules sometimes use 0x3D


# --- OLED ------------------------------------------------------------------

OLED_WIDTH = 128
OLED_HEIGHT = 64
OLED_AUTO_BLANK_SECONDS = 10


# --- Tunables (overridable via config.json) --------------------------------


@dataclass
class Tunables:
    # Posture
    pitch_alert_deg: float = 15.0
    pitch_alert_strict_deg: float = 10.0  # POST_MEAL
    pitch_sustained_seconds: float = 60.0
    posture_sample_hz_idle: float = 2.0
    posture_sample_hz_post_meal: float = 5.0
    posture_sample_hz_sleep: float = 0.03  # one sample every ~33s

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
    hotspot_ssid: str = "Sentinel-AP"
    hotspot_password: str = "sentinel123"  # change on first boot
    hotspot_ip: str = "192.168.1.1"
    hotspot_schedule_on: str = "07:00"
    hotspot_schedule_off: str = "23:00"
    hotspot_mode: str = "always"  # always | scheduled | manual

    # UI
    language: str = "en"

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

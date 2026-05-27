# Posture detection — GERD rationale

Waist-worn **MPU6050 accelerometer** (not gyro-only). Pitch = forward/back trunk
tilt from calibrated upright; roll = side tilt for sleep position.

## What matters for reflux

| Risk | Why | Device signal |
|------|-----|----------------|
| **Slouch / trunk flexion** | Compresses abdomen, weakens gravity assist | `\|pitch\|` > ~12° (8° post-meal) |
| **Lying flat after eating** | Reflux episodes rise sharply vs upright | `\|pitch\|` ≥ ~55° for sustained period |
| **Right-side sleep** | Higher esophageal acid exposure vs left | Roll → sleep tracker nudges |
| **Stay upright post-meal** | Clinical guidance: 2–3 h after meals | POST_MEAL state + stricter thresholds |

Sources: postprandial reflux studies (upright vs recumbent), left vs right
lateral decubitus pH monitoring, lifestyle guidance on slouching and head-of-bed
elevation (~30° / 6–8 in for night, not pillow-only).

## Default thresholds (`config.json`)

| Tunable | Default | Meaning |
|---------|---------|---------|
| `pitch_alert_deg` | 12° | Daytime slouch alert |
| `pitch_alert_strict_deg` | 8° | Post-meal slouch |
| `lying_flat_deg` | 55° | Torso near horizontal |
| `lying_grace_seconds` | 120 s | Brief lie-down OK after meal |
| `lying_sustained_seconds` | 20 s | Alert after grace if still flat |
| `pitch_sustained_seconds` | 45 s | Slouch must persist before alert |
| `posture_deadzone_deg` | 5° | Ignore small sensor wobble |

## Calibration

Stand naturally upright → Calibrate → capture baseline pitch. Mounting on
left/right hip is handled for **sleep roll** via `wear_side`; pitch baseline
covers clip orientation for slouch.

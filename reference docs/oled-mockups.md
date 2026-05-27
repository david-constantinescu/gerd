# UpRight OLED UI mockups (128×64 logical)

Source: `oled menus.pdf`. The on-device TFT renders this layout scaled to **160×128** landscape.

## Controls (two buttons only)

| Button | GPIO | Default |
|--------|------|---------|
| **Top** | 20 | **Tap:** next option (wraps to top) · **Double-tap:** back / dismiss |
| **Bottom** | 21 | **Tap:** confirm highlighted · **Double-tap:** log symptom |

Control legend is shown on the **main menu** only; other screens have no button hints.

No rotary encoder is connected.

## Watch face (home)

```
┌────────────────────────────┐
│ 14:32    ●GOOD    ♥ 68bpm │
│ ─────────────────────────  │
│ Posture: ████████░░        │
│ Pitch: -3.2°          82%  │
│ Last meal: 1h 24m ago      │
│ Upright ✓                  │
└────────────────────────────┘
```

## Main menu (top tap from watch, or navigate from another screen)

```
┌────────────────────────────┐
│ ≡ MAIN MENU                │
│ ─────────────────────────  │
│ ▶ Log Meal                 │
│   Log Symptom              │
│   Medication               │
│   Settings                 │
│   Sleep Mode               │
│   About                    │
└────────────────────────────┘
```

**In menu:** top tap = next · top double = back · bottom tap = select · bottom double = log symptom.

## Quick reference

| Screen | Top tap | Top double | Bottom tap | Bottom double |
|--------|---------|------------|------------|---------------|
| Watch | Open main menu | — | — | Log symptom |
| Main menu | Next | Close / back | Select | Log symptom |
| Lists / yes-no | Next | Back | Select | — |
| Food photo | Next | Back | Select (capture) | Capture |
| Calibrate | — | Exit | — | Capture step |
| Med reminder | Next | Back | Acknowledge | Acknowledge |

Menus auto-close after **30 s** idle (returns to watch face).

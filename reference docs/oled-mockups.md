# UpRight OLED UI mockups (128×64 logical)

Source: `oled menus.pdf`. The on-device TFT renders this layout scaled to **160×128** landscape.

## Controls (two buttons only)

| Button | GPIO | Default |
|--------|------|---------|
| **Top** | 20 | **Tap:** next option down · **Double-tap:** back / close submenu |
| **Bottom** | 21 | **Tap:** select highlighted option · **Double-tap:** open highlighted branch (from main menu) or open main menu from watch |

Non-default actions show on-screen as `top:` / `bottom:` hints only when needed (e.g. food photo: `bottom: capture`).

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

## Main menu (bottom double-tap from watch)

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

**In menu:** top tap = next · top double = back · bottom tap = select · bottom double = open highlighted item.

## Quick reference

| Screen | Top tap | Top double | Bottom tap | Bottom double |
|--------|---------|------------|------------|---------------|
| Watch | — | — | — | Open main menu |
| Main menu | Next | Close / back | Select | Open branch |
| Lists / yes-no | Next | Back | Select | — |
| Food photo | Next | Back | Select (capture) | Capture |
| Calibrate | — | Exit | — | Capture step |
| Med reminder | Next | Back | Acknowledge | Acknowledge |

Menus auto-close after **30 s** idle (returns to watch face).

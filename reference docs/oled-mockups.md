# UpRight OLED UI mockups (128×64 logical)

Source: `oled menus.pdf`. The on-device TFT renders this layout scaled to **160×128** landscape.

## Controls (two buttons only)

| Button | GPIO | Role (replaces encoder + back in PDF) |
|--------|------|----------------------------------------|
| **A** (top) | 20 | **Tap:** previous item · **Hold (~2.2s):** back / close |
| **B** (bottom) | 21 | **Tap:** next item · **Hold (~1.8s):** select / confirm |

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
│ Hold A = meal   B = menu   │
└────────────────────────────┘
```

## Main menu (B short from watch)

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

**In menu:** B short = next · A short = previous (A on first item closes menu) · B long = open highlighted item.

## Quick reference

| Screen | A short | A long | B short | B long |
|--------|---------|--------|---------|--------|
| Watch | — | Log meal → confirm | Open menu | — |
| Main menu | Prev / close | Close menu | Next item | Select |
| Yes/No, lists | Back | — | Next option | Confirm |
| Food photo | Skip | — | — | Capture |
| Med reminder | — | — | — | Acknowledge |

Menus auto-close after **30 s** idle (returns to watch face).

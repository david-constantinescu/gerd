"""OLED / ST7735R screen renderers, one per FSM state."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from .states import State

# ST7735R colour palette
_C_BG = (8, 16, 32)
_C_FG = (240, 240, 255)
_C_ACCENT = (80, 220, 120)
_C_WARN = (255, 180, 60)


def _bar_mono(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, frac: float) -> None:
    frac = max(0.0, min(1.0, frac))
    d.rectangle((x, y, x + w, y + h), outline=1)
    fill = int(w * frac)
    if fill > 0:
        d.rectangle((x + 1, y + 1, x + fill, y + h - 1), fill=1)


def _bar_rgb(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, frac: float) -> None:
    frac = max(0.0, min(1.0, frac))
    d.rectangle((x, y, x + w, y + h), outline=_C_FG)
    fill = int(w * frac)
    if fill > 0:
        d.rectangle((x + 1, y + 1, x + fill, y + h - 1), fill=_C_ACCENT)


def draw_idle_mono(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    bat = ctx.get("battery_text", "--")
    posture = ctx.get("posture_pct", 0.0)
    pitch = ctx.get("pitch", 0.0)
    last_meal = ctx.get("last_meal_text", "—")
    d.text((0, 0), f"{now}  Bat {bat}", fill=1)
    d.text((0, 12), "Posture:", fill=1)
    _bar_mono(d, 56, 12, 60, 8, posture / 100.0)
    d.text((0, 24), f"Pitch: {pitch:+.1f}", fill=1)
    d.text((0, 36), f"Meal: {last_meal}", fill=1)
    d.text((0, 52), "A=meal B=symptom", fill=1)


def draw_idle_rgb(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    bat = ctx.get("battery_text", "--")
    posture = ctx.get("posture_pct", 0.0)
    pitch = ctx.get("pitch", 0.0)
    last_meal = ctx.get("last_meal_text", "—")
    d.text((4, 4), f"{now}", fill=_C_FG)
    d.text((70, 4), f"Bat {bat}", fill=_C_ACCENT)
    d.text((4, 22), "Posture", fill=_C_FG)
    _bar_rgb(d, 4, 36, 118, 10, posture / 100.0)
    d.text((4, 52), f"Pitch {pitch:+.1f} deg", fill=_C_FG)
    d.text((4, 68), f"Meal {last_meal}", fill=_C_FG)
    d.text((4, 96), "A meal  B symptom", fill=_C_WARN)


def draw_alert_rgb(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    pitch = ctx.get("pitch", 0.0)
    posture = ctx.get("posture_pct", 0.0)
    d.text((4, 4), f"{now} SLOUCH", fill=_C_WARN)
    _bar_rgb(d, 4, 28, 118, 12, posture / 100.0)
    d.text((4, 48), f"Pitch {pitch:+.1f}", fill=_C_FG)
    d.text((4, 68), "Straighten up!", fill=_C_WARN)


def draw_post_meal_rgb(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    remaining = ctx.get("remaining", "0:00")
    frac = ctx.get("progress", 0.0)
    d.text((4, 4), f"{now} POST-MEAL", fill=_C_ACCENT)
    d.text((4, 28), f"Stay up {remaining}", fill=_C_FG)
    _bar_rgb(d, 4, 48, 118, 10, frac)


def draw_booting_rgb(d: ImageDraw.ImageDraw, _ctx: dict) -> None:
    d.text((8, 48), "UPRIGHT", fill=_C_FG)
    d.text((8, 68), "starting...", fill=_C_ACCENT)


def draw_idle(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    draw_idle_mono(d, ctx)


def draw_alert(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    level = ctx.get("level", 1)
    pitch = ctx.get("pitch", 0.0)
    posture = ctx.get("posture_pct", 0.0)
    d.text((0, 0), f"{now}  SLOUCH  lvl{level}", fill=1)
    d.text((0, 12), "Posture:", fill=1)
    _bar_mono(d, 56, 12, 60, 8, posture / 100.0)
    d.text((0, 24), f"Pitch: {pitch:+.1f}° lean!", fill=1)
    d.text((0, 40), "Straighten up", fill=1)
    _bar_mono(d, 0, 54, 120, 8, level / 3.0)


def draw_post_meal(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    remaining = ctx.get("remaining", "0:00")
    frac = ctx.get("progress", 0.0)
    meal_at = ctx.get("meal_at_text", "—")
    d.text((0, 0), f"{now}  GOOD", fill=1)
    d.text((0, 14), f"Stay upright: {remaining}", fill=1)
    _bar_mono(d, 0, 28, 120, 8, frac)
    d.text((0, 42), f"Meal at {meal_at}", fill=1)


def draw_food_result(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    name = ctx.get("name", "?")
    risk = ctx.get("risk", "?")
    advice = ctx.get("advice", "")
    d.text((0, 0), "FOOD ANALYSIS", fill=1)
    d.text((0, 14), f"Detected: {name}", fill=1)
    d.text((0, 26), f"Risk: {risk}", fill=1)
    d.text((0, 40), advice[:21], fill=1)
    d.text((0, 52), "Confirm   Retry", fill=1)


def draw_sleep(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    pos = ctx.get("position", "—")
    score = ctx.get("score", 0)
    d.text((0, 0), "SLEEP MODE", fill=1)
    d.text((0, 16), f"Position: {pos.upper()}", fill=1)
    d.text((0, 30), f"Score: {score}/100", fill=1)
    d.text((0, 50), "Goodnight", fill=1)


def draw_calibrating(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    step = ctx.get("step", "Stand upright")
    d.text((0, 0), "CALIBRATE", fill=1)
    d.text((0, 16), step, fill=1)
    d.text((0, 40), "click to capture", fill=1)


def draw_booting(d: ImageDraw.ImageDraw, _ctx: dict) -> None:
    d.text((0, 0), "UPRIGHT", fill=1)
    d.text((0, 16), "booting…", fill=1)
    d.text((0, 50), "v0.1", fill=1)


_RGB_DRAWERS = {
    State.BOOTING: draw_booting_rgb,
    State.IDLE: draw_idle_rgb,
    State.POST_MEAL: draw_post_meal_rgb,
    State.CALIBRATING: draw_calibrating,
    State.ONBOARDING: draw_calibrating,
    State.FOOD_PHOTO: draw_food_result,
    State.PRE_SLEEP: draw_sleep,
    State.SLEEPING: draw_sleep,
}

_DRAWERS = {
    State.BOOTING: draw_booting,
    State.ONBOARDING: draw_calibrating,
    State.IDLE: draw_idle,
    State.POST_MEAL: draw_post_meal,
    State.FOOD_PHOTO: draw_food_result,
    State.PRE_SLEEP: draw_sleep,
    State.SLEEPING: draw_sleep,
    State.CALIBRATING: draw_calibrating,
}


def render(state: State, ctx: dict, oled) -> None:
    color = getattr(oled, "color", False)
    w, h = oled.width, oled.height

    if color:
        img = Image.new("RGB", (w, h), _C_BG)
        d = ImageDraw.Draw(img)
        if state == State.IDLE and ctx.get("alert_active"):
            draw_alert_rgb(d, ctx)
        else:
            drawer = _RGB_DRAWERS.get(state, draw_booting_rgb)
            drawer(d, ctx)
        oled.show(img)
        return

    base_w, base_h = 128, 64
    mono = Image.new("1", (base_w, base_h), 0)
    d = ImageDraw.Draw(mono)
    drawer = _DRAWERS.get(state, draw_booting)
    if state == State.IDLE and ctx.get("alert_active"):
        draw_alert(d, ctx)
    else:
        drawer(d, ctx)
    if (w, h) != (base_w, base_h):
        scale = max(1, min(w // base_w, h // base_h))
        scaled = mono.resize((base_w * scale, base_h * scale), Image.NEAREST)
        canvas = Image.new("1", (w, h), 0)
        canvas.paste(scaled, ((w - scaled.width) // 2, (h - scaled.height) // 2))
        mono = canvas
    oled.show(mono)

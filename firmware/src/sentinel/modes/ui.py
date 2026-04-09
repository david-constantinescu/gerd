"""OLED screen renderers, one per FSM state.

Each ``draw_*`` function takes a context dict and a PIL image and draws into
it. Kept deliberately simple — no widget framework, just text + a few bars.
"""

from __future__ import annotations

from datetime import datetime

from PIL import ImageDraw

from .states import State


def _bar(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, frac: float) -> None:
    frac = max(0.0, min(1.0, frac))
    d.rectangle((x, y, x + w, y + h), outline=1)
    fill = int(w * frac)
    if fill > 0:
        d.rectangle((x + 1, y + 1, x + fill, y + h - 1), fill=1)


def draw_idle(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    bpm = ctx.get("bpm", "--")
    posture = ctx.get("posture_pct", 0.0)
    pitch = ctx.get("pitch", 0.0)
    last_meal = ctx.get("last_meal_text", "—")
    d.text((0, 0), f"{now}  GOOD  HR {bpm}", fill=1)
    d.text((0, 12), "Posture:", fill=1)
    _bar(d, 56, 12, 60, 8, posture / 100.0)
    d.text((0, 24), f"Pitch: {pitch:+.1f}°", fill=1)
    d.text((0, 36), f"Last meal: {last_meal}", fill=1)
    d.text((0, 52), "Upright OK   hold=meal", fill=1)


def draw_alert(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    level = ctx.get("level", 1)
    pitch = ctx.get("pitch", 0.0)
    posture = ctx.get("posture_pct", 0.0)
    d.text((0, 0), f"{now}  SLOUCH  lvl{level}", fill=1)
    d.text((0, 12), "Posture:", fill=1)
    _bar(d, 56, 12, 60, 8, posture / 100.0)
    d.text((0, 24), f"Pitch: {pitch:+.1f}° lean!", fill=1)
    d.text((0, 40), "Straighten up", fill=1)
    _bar(d, 0, 54, 120, 8, level / 3.0)


def draw_post_meal(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    now = datetime.now().strftime("%H:%M")
    remaining = ctx.get("remaining", "0:00")
    frac = ctx.get("progress", 0.0)
    meal_at = ctx.get("meal_at_text", "—")
    d.text((0, 0), f"{now}  GOOD", fill=1)
    d.text((0, 14), f"Stay upright: {remaining}", fill=1)
    _bar(d, 0, 28, 120, 8, frac)
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
    d.text((0, 0), "REFLUX SENTINEL", fill=1)
    d.text((0, 16), "booting…", fill=1)
    d.text((0, 50), "v0.1", fill=1)


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
    img = oled.new_frame()
    d = ImageDraw.Draw(img)
    drawer = _DRAWERS.get(state, draw_booting)
    if state == State.IDLE and ctx.get("alert_active"):
        draw_alert(d, ctx)
    else:
        drawer(d, ctx)
    oled.show(img)

"""TFT renderers — native resolution, mockup structure, pre-menu text clarity."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from . import menu as menu_mod
from . import ui_theme as theme
from .states import State

_SYMPTOM_TYPES = menu_mod.SYMPTOM_TYPES
_SYMPTOM_SEVERITIES = menu_mod.SYMPTOM_SEVERITIES
_MAIN_ITEMS = menu_mod.MAIN_ITEMS


def _wh(ctx: dict) -> tuple[int, int]:
    return int(ctx.get("_w", 160)), int(ctx.get("_h", 128))


def _posture_status(pct: float, alert: bool) -> str:
    if alert:
        return "SLOUCH"
    if pct >= 80:
        return "GOOD"
    if pct >= 50:
        return "OK"
    return "LOW"


def _draw_battery(d: ImageDraw.ImageDraw, ctx: dict, w: int) -> None:
    pct = int(ctx.get("battery_pct", 100))
    low = bool(ctx.get("battery_low", False))
    powered = bool(ctx.get("battery_powered", False))
    ok_green = bool(ctx.get("battery_ok_green", False))
    low_age = float(ctx.get("battery_low_age_s", 0.0))
    theme.battery_icon(
        d,
        max(4, w - 34),
        4,
        pct,
        low=low,
        powered=powered,
        ok_green=ok_green,
        low_age_s=low_age,
    )


def draw_watch_face(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    now = datetime.now().strftime("%H:%M")
    bpm = ctx.get("bpm", "--")
    posture = ctx.get("posture_pct", 0.0)
    pitch = ctx.get("pitch", 0.0)
    last_meal = ctx.get("last_meal_text", "-")
    alert = ctx.get("alert_active", False)
    level = ctx.get("level", 0)
    status = _posture_status(posture, alert)

    if alert:
        d.text((4, 4), f"{now}  {status}", fill=theme._C_WARN)
        d.text((72, 4), f"{bpm}bpm", fill=theme._C_ACCENT)
        _draw_battery(d, ctx, w)
        theme.hr(d, 20, w)
        d.text((4, 26), "Posture score", fill=theme._C_FG)
        theme.progress_bar(d, 4, 40, max(40, w - 8), 10, posture / 100.0)
        d.text((4, 56), f"Pitch {pitch:+.1f} deg", fill=theme._C_FG)
        d.text((max(4, w - 48), 56), f"{int(posture)}%", fill=theme._C_FG)
        d.text((4, 72), "Straighten up!", fill=theme._C_WARN)
        theme.progress_bar(d, 4, 90, max(40, w - 8), 8, level / 3.0)
        return

    d.text((4, 4), now, fill=theme._C_FG)
    d.text((66, 4), status, fill=theme._C_ACCENT)
    _draw_battery(d, ctx, w)
    if bpm != "--":
        d.text((max(4, w - 62), 18), f"{bpm} bpm", fill=theme._C_DIM)
    theme.hr(d, 20, w)
    d.text((4, 26), "Posture score", fill=theme._C_FG)
    theme.progress_bar(d, 4, 40, max(40, w - 8), 10, posture / 100.0)
    d.text((4, 56), f"Pitch {pitch:+.1f} deg", fill=theme._C_FG)
    d.text((max(4, w - 48), 56), f"{int(posture)}%", fill=theme._C_FG)
    d.text((4, 72), f"Meal {last_meal}", fill=theme._C_FG)
    d.text((4, 88), "Upright OK", fill=theme._C_FG)


def draw_post_meal_watch(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    now = datetime.now().strftime("%H:%M")
    posture = ctx.get("posture_pct", 0.0)
    remaining = ctx.get("remaining", "0:00")
    frac = ctx.get("progress", 0.0)
    meal_at = ctx.get("meal_at_text", "-")

    d.text((4, 4), f"{now}  POST-MEAL", fill=theme._C_ACCENT)
    _draw_battery(d, ctx, w)
    theme.hr(d, 20, w)
    d.text((4, 26), "Posture score", fill=theme._C_FG)
    theme.progress_bar(d, 4, 40, max(40, w - 8), 10, posture / 100.0)
    d.text((4, 56), f"Stay up {remaining}", fill=theme._C_FG)
    theme.progress_bar(d, 4, 72, max(40, w - 8), 10, frac)
    d.text((4, 90), f"Meal at {meal_at}", fill=theme._C_DIM)
    d.text((max(4, w - 48), 40), f"{int(posture)}%", fill=theme._C_FG)


def draw_main_menu(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "MAIN MENU", w)
    idx = int(ctx.get("menu_index", 0))
    y = 28
    for i, (label, _) in enumerate(_MAIN_ITEMS):
        prefix = "> " if i == idx else "  "
        theme.menu_row(d, y, f"{prefix}{label}", w=w, selected=(i == idx))
        y += 18
        if y > h - 24:
            break


def draw_meal_confirm(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "LOG MEAL", w)
    d.text((4, 28), "Log meal now?", fill=theme._C_FG)
    d.text((4, 44), f"Time: {datetime.now().strftime('%H:%M')}", fill=theme._C_DIM)
    idx = int(ctx.get("menu_index", 0))
    theme.menu_row(d, 64, "> Yes" if idx == 0 else "  Yes", w=w, selected=(idx == 0))
    theme.menu_row(d, 84, "> No" if idx == 1 else "  No", w=w, selected=(idx == 1))


def draw_food_photo_prompt(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "FOOD PHOTO", w)
    d.text((4, 32), "Point camera at food", fill=theme._C_FG)
    idx = int(ctx.get("menu_index", 0))
    theme.menu_row(d, 56, "> Capture", w=w, selected=(idx == 0))
    theme.menu_row(d, 76, "  Skip photo", w=w, selected=(idx == 1))
    theme.footer_hint(d, "bottom: capture", h)


def draw_food_analysing(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "ANALYSING", w)
    frac = float(ctx.get("analyse_progress", 0.5))
    theme.progress_bar(d, 4, 36, max(40, w - 8), 12, frac)
    d.text((4, 56), "Running model...", fill=theme._C_FG)
    d.text((4, 72), "Please wait", fill=theme._C_DIM)


def draw_food_preview(img: Image.Image, d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "PHOTO", w)
    preview = ctx.get("food_preview_image")
    if preview is None:
        d.text((4, 40), "No preview", fill=theme._C_DIM)
        return
    max_w = w - 16
    max_h = h - 36
    pw, ph = preview.size
    scale = min(max_w / pw, max_h / ph)
    tw = max(1, int(pw * scale))
    th = max(1, int(ph * scale))
    thumb = preview.resize((tw, th), Image.Resampling.LANCZOS)
    x = (w - tw) // 2
    y = 24
    img.paste(thumb, (x, y))


def draw_food_result(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    name = (ctx.get("name", "?") or "?")[:16]
    risk = ctx.get("risk", "?")
    advice = (ctx.get("advice", "") or "")[:24]
    theme.title_bar(d, "FOOD ANALYSIS", w)
    d.text((4, 28), f"Food: {name}", fill=theme._C_FG)
    d.text((4, 44), f"Risk: {risk}", fill=theme._C_ACCENT)
    d.text((4, 60), advice, fill=theme._C_FG)
    idx = int(ctx.get("menu_index", 0))
    theme.menu_row(d, 84, "> Confirm", w=w, selected=(idx == 0))


def draw_meal_saved(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    d.text((4, 24), "Meal logged", fill=theme._C_FG)
    d.text((4, 44), "Upright timer on", fill=theme._C_FG)
    window = ctx.get("meal_window_text", "2h 30m")
    d.text((4, 64), f"Stay up {window}", fill=theme._C_DIM)


def draw_symptom_severity(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "LOG SYMPTOM", w)
    d.text((4, 28), "Severity?", fill=theme._C_FG)
    idx = int(ctx.get("menu_index", 0))
    y = 48
    for i, label in enumerate(_SYMPTOM_SEVERITIES):
        theme.menu_row(
            d, y, f"> {label}" if i == idx else f"  {label}", w=w, selected=(i == idx)
        )
        y += 18
        if y > h - 20:
            break


def draw_symptom_type(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "SYMPTOM TYPE", w)
    idx = int(ctx.get("menu_index", 0))
    y = 28
    for i, label in enumerate(_SYMPTOM_TYPES):
        theme.menu_row(
            d, y, f"> {label}" if i == idx else f"  {label}", w=w, selected=(i == idx)
        )
        y += 18
        if y > h - 20:
            break


def draw_symptom_saved(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    sev = ctx.get("symptom_severity_label", "1 - Mild")
    typ = ctx.get("symptom_type_label", "Heartburn")
    d.text((4, 20), "Symptom logged", fill=theme._C_FG)
    d.text((4, 40), f"Sev: {sev}", fill=theme._C_FG)
    d.text((4, 56), f"Type: {typ}", fill=theme._C_FG)
    d.text((4, 72), datetime.now().strftime("%H:%M"), fill=theme._C_DIM)


def draw_med_reminder(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "MEDICATION", w)
    name = (ctx.get("menu_pending_med", "Medication") or "")[:18]
    when = ctx.get("menu_pending_med_time", "")
    d.text((4, 32), name, fill=theme._C_FG)
    d.text((4, 48), f"Due: {when}", fill=theme._C_DIM)


def draw_med_ack(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    name = (ctx.get("menu_pending_med", "") or "")[:18]
    d.text((4, 24), "Med acknowledged", fill=theme._C_FG)
    d.text((4, 44), name, fill=theme._C_FG)
    d.text((4, 60), datetime.now().strftime("Taken %H:%M"), fill=theme._C_DIM)


def draw_settings(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "SETTINGS", w)
    d.text((4, 32), "Edit on phone:", fill=theme._C_FG)
    d.text((4, 48), "192.168.1.1", fill=theme._C_ACCENT)


def draw_about(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "ABOUT", w)
    d.text((4, 32), "UPRIGHT", fill=theme._C_FG)
    d.text((4, 48), f"v{ctx.get('version', '0.1.0')}", fill=theme._C_DIM)
    d.text((4, 64), "GERD wearable", fill=theme._C_FG)


def draw_flash(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    msg = (ctx.get("menu_flash", "") or "")[:24]
    d.text((4, h // 2 - 6), msg, fill=theme._C_FG)


def draw_calibrating(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "CALIBRATE", w)
    step = (ctx.get("step", "Stand upright") or "")[:22]
    d.text((4, 32), step, fill=theme._C_FG)
    d.text((4, 48), "Hold still", fill=theme._C_DIM)
    theme.footer_hint(d, "bottom: capture", h)


def draw_booting(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    d.text((8, h // 2 - 20), "UPRIGHT", fill=theme._C_FG)
    d.text((8, h // 2), "starting...", fill=theme._C_ACCENT)


def draw_sleep(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    pre = ctx.get("fsm_state") == "pre_sleep"
    theme.title_bar(d, "PRE-SLEEP" if pre else "SLEEP MODE", w)
    pos = (ctx.get("position", "-") or "-").upper()
    elapsed = ctx.get("sleep_elapsed", "0m")
    nudges = int(ctx.get("sleep_nudges", 0))
    n_max = int(ctx.get("sleep_nudges_max", 3))
    score = int(ctx.get("sleep_score", 0))
    left_p = int(ctx.get("sleep_left_pct", 0))
    right_p = int(ctx.get("sleep_right_pct", 0))
    back_p = int(ctx.get("sleep_back_pct", 0))
    roll = ctx.get("roll", 0.0)
    wear = (ctx.get("sleep_wear_side", "left") or "left")[:6]
    cooldown = int(ctx.get("sleep_nudge_cooldown_s", 0))
    window = ctx.get("sleep_window", "")

    y = 24
    if pre:
        d.text((4, y), "Lie on LEFT side", fill=theme._C_ACCENT)
        y += 14
        d.text((4, y), f"Window {window}", fill=theme._C_DIM)
        y += 14
    d.text((4, y), f"Now: {pos}  ({elapsed})", fill=theme._C_FG)
    y += 14
    d.text((4, y), f"Score {score}%  Nudges {nudges}/{n_max}", fill=theme._C_FG)
    y += 14
    d.text((4, y), f"L{left_p} R{right_p} B{back_p}%", fill=theme._C_DIM)
    y += 14
    d.text((4, y), f"Roll {roll:+.0f}  clip:{wear}", fill=theme._C_DIM)
    if pos != "LEFT" and nudges < n_max and cooldown == 0:
        d.text((4, min(h - 14, y + 14)), "Nudge if not left", fill=theme._C_WARN)
    elif cooldown > 0:
        d.text((4, min(h - 14, y + 14)), f"Nudge in {cooldown}s", fill=theme._C_DIM)


_MENU_DRAWERS = {
    "main": draw_main_menu,
    "meal_confirm": draw_meal_confirm,
    "food_photo": draw_food_photo_prompt,
    "food_preview": None,  # handled in render()
    "food_analysing": draw_food_analysing,
    "food_result": draw_food_result,
    "meal_saved": draw_meal_saved,
    "symptom_severity": draw_symptom_severity,
    "symptom_type": draw_symptom_type,
    "symptom_saved": draw_symptom_saved,
    "med_prompt": draw_med_reminder,
    "med_ack": draw_med_ack,
    "settings": draw_settings,
    "about": draw_about,
    "flash": draw_flash,
}


def render(state: State, ctx: dict, oled) -> None:
    w = int(getattr(oled, "width", 160))
    h = int(getattr(oled, "height", 128))
    img, d = theme.new_frame(w, h)
    draw_ctx = {**ctx, "_w": w, "_h": h}

    if draw_ctx.get("display_demo"):
        theme.title_bar(d, "UPRIGHT", w)
        d.text((4, 32), "SYSTEM OK", fill=theme._C_FG)
        d.text((4, 48), "Display + web", fill=theme._C_ACCENT)
        oled.show(img)
        return

    screen = draw_ctx.get("menu_screen", "")
    if draw_ctx.get("menu_open") and screen == "food_preview":
        draw_food_preview(img, d, draw_ctx)
    elif draw_ctx.get("menu_open") and screen in _MENU_DRAWERS:
        drawer = _MENU_DRAWERS[screen]
        if drawer is not None:
            drawer(d, draw_ctx)
    elif state == State.BOOTING:
        draw_booting(d, draw_ctx)
    elif state == State.POST_MEAL:
        draw_post_meal_watch(d, draw_ctx)
    elif state == State.FOOD_PHOTO and draw_ctx.get("name"):
        draw_food_result(d, draw_ctx)
    elif state == State.FOOD_PHOTO:
        draw_food_analysing(d, draw_ctx)
    elif state in (State.CALIBRATING, State.ONBOARDING):
        draw_calibrating(d, draw_ctx)
    elif state in (State.PRE_SLEEP, State.SLEEPING):
        draw_ctx["fsm_state"] = state.value
        draw_sleep(d, draw_ctx)
    else:
        draw_watch_face(d, draw_ctx)

    oled.show(img)

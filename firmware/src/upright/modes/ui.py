"""TFT renderers — native resolution, mockup structure, pre-menu text clarity."""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from . import menu as menu_mod
from . import ui_theme as theme
from .menu import settings_items
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


def _draw_demo_badge(d: ImageDraw.ImageDraw, w: int) -> None:
    """Single D immediately left of the battery icon."""
    bat_x = max(4, w - 34)
    d.text((bat_x - 8, 4), "D", fill=theme._C_WARN)


def _draw_score_bar(
    d: ImageDraw.ImageDraw,
    y: int,
    w: int,
    pct: float,
    *,
    bar_h: int = 7,
) -> None:
    """Score label, inline bar, and % on one row."""
    pct = max(0.0, min(100.0, float(pct)))
    row_y = y
    d.text((4, row_y), "Score", fill=theme._C_DIM)
    pct_str = f"{int(pct)}%"
    pct_w = 28
    pct_x = w - 4 - pct_w
    bar_x = 38
    bar_w = max(12, pct_x - bar_x - 4)
    theme.progress_bar(d, bar_x, row_y + 1, bar_w, bar_h, pct / 100.0)
    d.text((pct_x, row_y), pct_str, fill=theme._C_FG)


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


def _watch_info_lines(ctx: dict) -> list[str]:
    """Compact status lines for the home / post-meal watch (max ~6)."""
    lines: list[str] = []
    last_meal = ctx.get("last_meal_text", "—")
    if last_meal != "—":
        lines.append(f"Meal {last_meal}")

    last_food = ctx.get("last_food_name", "—")
    if last_food and last_food != "—":
        risk = ctx.get("last_food_risk", "")
        food = f"Food {last_food[:12]}"
        if risk:
            food += f" {risk}"
        lines.append(food)
        score = int(ctx.get("last_food_score", 0) or 0)
        hours = float(ctx.get("food_upright_hours", 0) or 0)
        if score > 0:
            lines.append(f"Reflux {score}/100")
        if hours > 0:
            lines.append(f"Stay up {hours:.1f}h")

    med = ctx.get("med_line", "")
    if med:
        lines.append(med[:24])

    symptom = ctx.get("last_symptom_text", "")
    if symptom:
        lines.append(f"Symptom {symptom[:18]}")

    bpm = ctx.get("bpm", "--")
    if bpm != "--":
        rmssd = ctx.get("rmssd_text", "--")
        hrv = f"HR {bpm}"
        if rmssd != "--":
            hrv += f"  HRV {rmssd}"
        lines.append(hrv[:26])

    return lines[:5]


def draw_watch_face(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    now = datetime.now().strftime("%H:%M")
    date = ctx.get("date_text", "")
    wear = (ctx.get("wear_side", "left") or "left")[:5]
    posture = ctx.get("posture_pct", 0.0)
    pitch = ctx.get("pitch", 0.0)
    roll = ctx.get("roll", 0.0)
    alert = ctx.get("alert_active", False)
    level = ctx.get("level", 0)
    status = _posture_status(posture, alert)
    bar_w = max(40, w - 52)

    if alert:
        d.text((4, 4), f"{now} {status}", fill=theme._C_WARN)
        _draw_battery(d, ctx, w)
        theme.hr(d, 17, w)
        _draw_score_bar(d, 21, w, posture)
        d.text((4, 42), f"P {pitch:+.0f}° R {roll:+.0f}°", fill=theme._C_FG)
        d.text((4, 54), "Straighten up!", fill=theme._C_WARN)
        y = 66
        for line in _watch_info_lines(ctx)[:2]:
            d.text((4, y), line, fill=theme._C_DIM)
            y += 11
        theme.progress_bar(d, 4, h - 14, bar_w, 5, level / 3.0)
        return

    d.text((4, 4), now, fill=theme._C_FG)
    d.text((50, 4), status, fill=theme._C_ACCENT)
    if ctx.get("demo_mode"):
        _draw_demo_badge(d, w)
    _draw_battery(d, ctx, w)
    d.text((4, 16), f"{date}  {wear} side", fill=theme._C_DIM)
    week_avg = ctx.get("sleep_week_avg")
    if week_avg is not None:
        d.text((w - 52, 16), f"S{week_avg}", fill=theme._C_DIM)

    theme.hr(d, 28, w)

    _draw_score_bar(d, 32, w, posture)

    d.text((4, 46), f"P {pitch:+.0f}°  R {roll:+.0f}°", fill=theme._C_FG)

    y = 58
    for line in _watch_info_lines(ctx):
        if y > h - 12:
            break
        d.text((4, y), line, fill=theme._C_FG if y == 64 else theme._C_DIM)
        y += 11


def draw_post_meal_watch(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    now = datetime.now().strftime("%H:%M")
    posture = ctx.get("posture_pct", 0.0)
    remaining = ctx.get("remaining", "0:00")
    frac = ctx.get("progress", 0.0)
    meal_at = ctx.get("meal_at_text", "—")
    pitch = ctx.get("pitch", 0.0)

    d.text((4, 4), f"{now} POST-MEAL", fill=theme._C_ACCENT)
    _draw_battery(d, ctx, w)
    theme.hr(d, 18, w)

    d.text((4, 22), "Upright timer left", fill=theme._C_DIM)
    d.text((4, 34), remaining, fill=theme._C_FG)
    theme.progress_bar(d, 4, 48, max(40, w - 8), 7, min(1.0, frac))

    _draw_score_bar(d, 60, w, posture, bar_h=6)
    d.text((4, 80), f"Pitch {pitch:+.0f}°  ate {meal_at}", fill=theme._C_DIM)

    y = 92
    for line in _watch_info_lines(ctx)[:2]:
        if y > h - 10:
            break
        d.text((4, y), line, fill=theme._C_DIM)
        y += 11


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


def _paste_camera_thumb(
    img: Image.Image, preview, *, top: int, max_w: int, max_h: int
) -> None:
    w, h = _wh({"_w": img.width, "_h": img.height})
    pw, ph = preview.size
    scale = min(max_w / pw, max_h / ph)
    tw = max(1, int(pw * scale))
    th = max(1, int(ph * scale))
    thumb = preview.resize((tw, th), Image.Resampling.LANCZOS)
    x = (w - tw) // 2
    img.paste(thumb, (x, top))


def draw_food_photo_prompt(img: Image.Image, d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "FOOD PHOTO", w)
    live = ctx.get("food_live_preview_image")
    if live is not None:
        _paste_camera_thumb(img, live, top=22, max_w=w - 8, max_h=h - 58)
    else:
        d.text((4, 32), "Point camera at food", fill=theme._C_FG)
    idx = int(ctx.get("menu_index", 0))
    y0 = h - 44
    theme.menu_row(d, y0, "> Capture", w=w, selected=(idx == 0))
    theme.menu_row(d, y0 + 18, "  Skip photo", w=w, selected=(idx == 1))

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
    _paste_camera_thumb(img, preview, top=24, max_w=w - 16, max_h=h - 36)


def draw_food_result(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    name = (ctx.get("name", "?") or "?")[:16]
    risk = ctx.get("risk", "?")
    score = int(ctx.get("gerd_score", 0) or 0)
    hours = float(ctx.get("upright_hours", 0) or 0)
    advice = (ctx.get("advice", "") or "")[:22]
    theme.title_bar(d, "FOOD ANALYSIS", w)
    d.text((4, 26), name, fill=theme._C_FG)
    d.text((4, 42), f"{risk}  score {score}/100", fill=theme._C_ACCENT)
    if hours > 0:
        d.text((4, 56), f"Stay up {hours:.1f}h", fill=theme._C_FG)
    d.text((4, 70), advice, fill=theme._C_DIM)
    idx = int(ctx.get("menu_index", 0))
    theme.menu_row(d, 88, "> Confirm", w=w, selected=(idx == 0))
    theme.menu_row(d, 108, "> Retake photo", w=w, selected=(idx == 1))


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
    when = ctx.get("menu_pending_med_time", "")
    demo = bool(ctx.get("demo_mode"))
    brand = (ctx.get("menu_pending_med_brand", "") or "")[:18]
    dose = (ctx.get("menu_pending_med_dose", "") or "")[:16]
    name = (ctx.get("menu_pending_med", "Medication") or "")[:18]
    if demo and brand:
        d.text((4, 28), brand, fill=theme._C_FG)
        if dose:
            d.text((4, 42), dose, fill=theme._C_ACCENT)
        d.text((4, 56), f"Due {when}", fill=theme._C_DIM)
    else:
        d.text((4, 32), name, fill=theme._C_FG)
        d.text((4, 48), f"Due: {when}", fill=theme._C_DIM)


def draw_med_ack(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    name = (ctx.get("menu_pending_med", "") or "")[:18]
    d.text((4, 24), "Med acknowledged", fill=theme._C_FG)
    d.text((4, 44), name, fill=theme._C_FG)
    d.text((4, 60), datetime.now().strftime("Taken %H:%M"), fill=theme._C_DIM)


def draw_med_info(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "MEDICATION", w)
    d.text((4, 28), "Schedules on phone", fill=theme._C_FG)
    d.text((4, 44), "web dashboard", fill=theme._C_DIM)
    theme.menu_row(d, 64, "> Done", w=w, selected=True)


def draw_analytics(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "WEEK STATS", w)
    y = 26
    lines = ctx.get("analytics_lines") or ["No data yet"]
    for line in lines:
        if y > h - 28:
            break
        d.text((4, y), str(line)[:26], fill=theme._C_FG if y == 26 else theme._C_DIM)
        y += 12
    theme.menu_row(d, h - 22, "> Done", w=w, selected=True)


def draw_settings(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "SETTINGS", w)
    idx = int(ctx.get("menu_index", 0))
    y = 28
    items = settings_items()
    for i, (label, _) in enumerate(items):
        prefix = "> " if i == idx else "  "
        theme.menu_row(d, y, f"{prefix}{label}", w=w, selected=(i == idx))
        y += 18


def _draw_back_chip(d: ImageDraw.ImageDraw) -> None:
    """Small back button (top-left). Press a button to leave — see manager."""
    d.rectangle((2, 3, 20, 19), outline=theme._C_FG)
    d.line((14, 6, 8, 11), fill=theme._C_FG)
    d.line((8, 11, 14, 16), fill=theme._C_FG)


def draw_network(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    """Network screen.

    online → full-screen QR to open the dashboard.
    setup  → Wi-Fi-join QR for the temporary setup AP + a one-line hint.
    """
    w, h = _wh(ctx)
    qr = ctx.get("net_qr_image")
    img = ctx.get("_img")
    setup = ctx.get("net_mode") == "setup"

    if qr is not None and img is not None:
        qw, qh = qr.size
        top = 2 if setup else (h - qh) // 2
        img.paste(qr, (max(0, (w - qw) // 2), max(0, top)))
        _draw_back_chip(d)
        if setup:
            ip = (ctx.get("net_setup_url") or "http://10.42.0.1/")[7:].rstrip("/")
            d.text((4, h - 11), f"Join Wi-Fi, open {ip}", fill=theme._C_DIM)
        return

    # Fallback when QR generation is unavailable: show what to do as text.
    if setup:
        theme.title_bar(d, "WIFI SETUP", w)
        d.text((4, 34), f"Join: {ctx.get('net_setup_ssid') or 'UpRight-Setup'}", fill=theme._C_FG)
        d.text((4, 50), f"Pass: {ctx.get('net_setup_pass') or 'uprightsetup'}", fill=theme._C_DIM)
        d.text((4, 66), "Then open:", fill=theme._C_DIM)
        d.text((4, 80), str(ctx.get("net_setup_url") or "http://10.42.0.1/")[:24], fill=theme._C_FG)
    else:
        host = ctx.get("net_host") or "upright.local"
        theme.title_bar(d, "NETWORK", w)
        d.text((4, 40), "Open in a browser:", fill=theme._C_DIM)
        d.text((4, 56), str(ctx.get("net_url") or f"http://{host}/")[:24], fill=theme._C_FG)
    theme.menu_row(d, h - 14, "> Back", w=w, selected=True)


def draw_about(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    theme.title_bar(d, "ABOUT", w)
    d.text((4, 28), "UPRIGHT", fill=theme._C_FG)
    d.text((4, 44), f"v{ctx.get('version', '0.1.0')}", fill=theme._C_DIM)
    d.text((4, 60), "GERD wearable", fill=theme._C_FG)
    theme.menu_row(d, 84, "> Done", w=w, selected=True)


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

def draw_booting(d: ImageDraw.ImageDraw, ctx: dict) -> None:
    w, h = _wh(ctx)
    ver = ctx.get("version", "0.1.0")
    step = (ctx.get("boot_step") or "Starting")[:18]
    detail = (ctx.get("boot_detail") or "")[:26]
    devices = (ctx.get("boot_devices") or "")[:26]
    frac = max(0.0, min(1.0, float(ctx.get("boot_progress", 0.0))))
    pct = int(frac * 100)

    theme.title_bar(d, "UPRIGHT", w)
    d.text((4, 22), f"v{ver}", fill=theme._C_DIM)
    if ctx.get("demo_mode"):
        d.text((w - 36, 22), "DEMO", fill=theme._C_WARN)
    d.text((4, 36), step, fill=theme._C_FG)
    if detail:
        d.text((4, 50), detail, fill=theme._C_ACCENT)
    bar_y = 64 if detail else 52
    bar_w = max(40, w - 16)
    theme.progress_bar(d, 8, bar_y, bar_w, 9, frac)
    d.text((w - 34, bar_y + 1), f"{pct}%", fill=theme._C_FG)
    if devices:
        d.text((4, bar_y + 14), devices, fill=theme._C_DIM)


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
    y += 14
    week_avg = ctx.get("sleep_week_avg")
    if week_avg is not None:
        d.text((4, y), f"7d sleep avg {week_avg}/100", fill=theme._C_DIM)
        y += 12
    best = (ctx.get("sleep_best_line") or "")[:24]
    if best:
        d.text((4, y), best, fill=theme._C_DIM)
        y += 12
    if pos != "LEFT" and nudges < n_max and cooldown == 0:
        d.text((4, min(h - 14, y + 14)), "Nudge if not left", fill=theme._C_WARN)
    elif cooldown > 0:
        d.text((4, min(h - 14, y + 14)), f"Nudge in {cooldown}s", fill=theme._C_DIM)


_MENU_DRAWERS = {
    "main": draw_main_menu,
    "meal_confirm": draw_meal_confirm,
    "food_photo": None,
    "food_preview": None,
    "food_analysing": draw_food_analysing,
    "food_result": draw_food_result,
    "meal_saved": draw_meal_saved,
    "symptom_severity": draw_symptom_severity,
    "symptom_type": draw_symptom_type,
    "symptom_saved": draw_symptom_saved,
    "med_prompt": draw_med_reminder,
    "med_ack": draw_med_ack,
    "med_info": draw_med_info,
    "settings": draw_settings,
    "stats": draw_analytics,
    "network": draw_network,
    "about": draw_about,
    "flash": draw_flash,
}


def render(state: State, ctx: dict, oled) -> None:
    w = int(getattr(oled, "width", 160))
    h = int(getattr(oled, "height", 128))
    img, d = theme.new_frame(w, h)
    draw_ctx = {**ctx, "_w": w, "_h": h, "_img": img}

    if draw_ctx.get("display_demo"):
        theme.title_bar(d, "UPRIGHT", w)
        d.text((4, 32), "SYSTEM OK", fill=theme._C_FG)
        d.text((4, 48), "Display + web", fill=theme._C_ACCENT)
        oled.show(img)
        return

    screen = draw_ctx.get("menu_screen", "")
    if draw_ctx.get("menu_open") and screen == "food_preview":
        draw_food_preview(img, d, draw_ctx)
    elif draw_ctx.get("menu_open") and screen == "food_photo":
        draw_food_photo_prompt(img, d, draw_ctx)
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

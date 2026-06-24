"""Read-only analytics over SQLite — week summaries for web + OLED."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from .logger import Logger


def _since(days: int) -> float:
    return time.time() - days * 86400


def week_summary(db: Logger, days: int = 7) -> dict[str, Any]:
    since = _since(days)
    with db._lock:  # noqa: SLF001
        events = db._conn.execute(
            "SELECT ts, kind, payload FROM events WHERE ts >= ? ORDER BY ts",
            (since,),
        ).fetchall()
        sleep_rows = db._conn.execute(
            """SELECT night_of, duration_s, left_pct, right_pct, back_pct,
                      front_pct, score, nudges
               FROM sleep_log ORDER BY night_of DESC LIMIT ?""",
            (days,),
        ).fetchall()
        posture_avg = db._conn.execute(
            "SELECT AVG(ABS(pitch)) FROM posture_log WHERE ts >= ?",
            (since,),
        ).fetchone()

    meals = symptoms = waters = meds = food_photos = 0
    reflux_scores: list[int] = []
    per_day: dict[str, dict[str, int]] = {}

    for ts, kind, payload_raw in events:
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        bucket = per_day.setdefault(
            day, {"meals": 0, "symptoms": 0, "food": 0, "water": 0}
        )
        if kind == "meal":
            meals += 1
            bucket["meals"] += 1
        elif kind == "symptom":
            symptoms += 1
            bucket["symptoms"] += 1
        elif kind == "water":
            waters += 1
            bucket["water"] += 1
        elif kind == "med_acknowledged":
            meds += 1
        elif kind == "food_photo":
            food_photos += 1
            bucket["food"] += 1
            try:
                p = json.loads(payload_raw or "{}")
                if p.get("gerd_score") is not None:
                    reflux_scores.append(int(p["gerd_score"]))
            except (TypeError, ValueError):
                pass

    sleep_list = [
        {
            "night_of": r[0],
            "duration_h": round((r[1] or 0) / 3600, 1),
            "left_pct": r[2],
            "right_pct": r[3],
            "back_pct": r[4],
            "front_pct": r[5],
            "score": r[6],
            "nudges": r[7],
        }
        for r in sleep_rows
    ]
    scores = [s["score"] for s in sleep_list if s["score"] is not None]
    avg_sleep = round(sum(scores) / len(scores)) if scores else None
    best = max(sleep_list, key=lambda s: s["score"] or 0) if sleep_list else None
    avg_reflux = (
        round(sum(reflux_scores) / len(reflux_scores)) if reflux_scores else None
    )
    avg_pitch = round(float(posture_avg[0] or 0), 1) if posture_avg else None

    return {
        "days": days,
        "meals": meals,
        "symptoms": symptoms,
        "waters": waters,
        "meds_taken": meds,
        "food_photos": food_photos,
        "avg_sleep_score": avg_sleep,
        "best_sleep_night": best["night_of"] if best else None,
        "best_sleep_score": best["score"] if best else None,
        "avg_reflux_score": avg_reflux,
        "avg_pitch_abs": avg_pitch,
        "sleep_nights": sleep_list,
        "per_day": [
            {"date": d, **counts} for d, counts in sorted(per_day.items())
        ],
        "meal_symptom_links": meal_symptom_correlation(db, days=days),
    }


def meal_symptom_correlation(db: Logger, *, days: int = 7, window_h: float = 2.0) -> list[dict[str, Any]]:
    """Symptoms that occurred within ``window_h`` hours after a HIGH-risk meal/food."""
    since = _since(days)
    window_s = window_h * 3600.0
    with db._lock:  # noqa: SLF001
        events = db._conn.execute(
            "SELECT ts, kind, payload FROM events WHERE ts >= ? ORDER BY ts",
            (since,),
        ).fetchall()
    triggers: list[tuple[float, str, str]] = []
    links: list[dict[str, Any]] = []
    for ts, kind, payload_raw in events:
        try:
            p = json.loads(payload_raw or "{}")
        except json.JSONDecodeError:
            p = {}
        if kind in ("meal", "food_photo"):
            risk = str(p.get("risk", "")).upper()
            score = int(p.get("gerd_score", 0) or 0)
            if risk == "HIGH" or score >= 70:
                name = str(p.get("name") or p.get("notes") or "meal")
                triggers.append((ts, name, risk or f"score {score}"))
        elif kind == "symptom":
            for t_ts, food, risk in triggers:
                if 0 < ts - t_ts <= window_s:
                    links.append(
                        {
                            "food": food,
                            "food_risk": risk,
                            "symptom_type": p.get("type", "?"),
                            "severity": p.get("severity"),
                            "delay_min": int((ts - t_ts) // 60),
                            "meal_ts": t_ts,
                            "symptom_ts": ts,
                        }
                    )
                    break
    return links[-20:]


def oled_lines(summary: dict[str, Any]) -> list[str]:
    """Short lines for the 128px TFT stats screen."""
    lines: list[str] = []
    meals = summary.get("meals", 0)
    symptoms = summary.get("symptoms", 0)
    lines.append(f"7d: {meals} meals  {symptoms} symptoms")
    avg_sleep = summary.get("avg_sleep_score")
    if avg_sleep is not None:
        lines.append(f"Sleep avg {avg_sleep}/100")
    best = summary.get("best_sleep_night")
    best_sc = summary.get("best_sleep_score")
    if best and best_sc is not None:
        short = best[5:] if len(best) > 5 else best
        lines.append(f"Best {short} {best_sc}")
    avg_r = summary.get("avg_reflux_score")
    if avg_r is not None:
        lines.append(f"Avg reflux {avg_r}/100")
    nights = summary.get("sleep_nights") or []
    if nights:
        last = nights[0]
        lines.append(
            f"Last L{int(last.get('left_pct') or 0)}% "
            f"nudges {last.get('nudges', 0)}"
        )
    return lines[:6]

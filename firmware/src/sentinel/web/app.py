"""Flask PWA served at http://192.168.1.1.

Runs as its own systemd unit (``sentinel-web.service``) so a webapp crash
cannot kill the firmware loop. The two processes share only the SQLite file
at ``firmware/data/sentinel.db``.

The webapp never mutates device state directly — it writes "inbox" rows
into the DB and the firmware polls them in its main loop.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

from ..config import CONFIG_PATH, DB_PATH, FOODS_PATH, TUNABLES, Tunables, reload_tunables
from ..services import foods as foods_service
from ..services.logger import Logger

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)


def _db() -> Logger:
    return Logger()


# -------------------------------------------------- page routes


@app.route("/")
def dashboard():
    return render_template("dashboard.html", active="dashboard")


@app.route("/food-log")
def food_log():
    return render_template("food_log.html", active="food-log")


@app.route("/sleep")
def sleep_page():
    return render_template("sleep.html", active="sleep")


@app.route("/reports")
def reports():
    return render_template("reports.html", active="reports")


@app.route("/settings")
def settings():
    return render_template(
        "settings.html",
        active="settings",
        tunables=asdict(TUNABLES),
    )


# -------------------------------------------------- JSON API


@app.route("/api/live")
def api_live():
    db = _db()
    events = db.recent_events(limit=20)
    last_meal = db.last_meal()
    with db._lock:  # noqa: SLF001
        row = db._conn.execute(
            "SELECT ts, pitch, roll, state FROM posture_log ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    posture = (
        {"ts": row[0], "pitch": row[1], "roll": row[2], "state": row[3]}
        if row
        else None
    )
    db.close()
    return jsonify(
        {
            "posture": posture,
            "events": events,
            "last_meal": last_meal,
            "now": datetime.now().isoformat(),
        }
    )


@app.post("/api/log/meal")
def api_log_meal():
    data = request.get_json(silent=True) or {}
    db = _db()
    db.push_inbox("meal", {"notes": data.get("notes", "")})
    db.close()
    return jsonify({"ok": True})


@app.post("/api/log/symptom")
def api_log_symptom():
    data = request.get_json(silent=True) or {}
    db = _db()
    db.push_inbox(
        "symptom",
        {
            "severity": int(data.get("severity", 1)),
            "type": data.get("type", "heartburn"),
            "notes": data.get("notes", ""),
        },
    )
    db.close()
    return jsonify({"ok": True})


@app.post("/api/log/water")
def api_log_water():
    db = _db()
    db.push_inbox("water", {})
    db.close()
    return jsonify({"ok": True})


@app.route("/api/events")
def api_events():
    limit = min(int(request.args.get("limit", 200)), 1000)
    db = _db()
    rows = db.recent_events(limit=limit)
    db.close()
    return jsonify(rows)


@app.route("/api/foods", methods=["GET", "POST"])
def api_foods():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        foods_service.upsert(
            data["name"],
            data["risk"],
            float(data.get("upright_hours", 2.5)),
        )
        return jsonify({"ok": True})
    return jsonify(
        {k: asdict(v) for k, v in foods_service.all_foods().items()}
    )


@app.route("/api/medications", methods=["GET", "POST", "DELETE"])
def api_medications():
    db = _db()
    if request.method == "GET":
        with db._lock:  # noqa: SLF001
            rows = db._conn.execute(
                "SELECT id, name, dose, time, frequency, enabled FROM medications"
            ).fetchall()
        db.close()
        return jsonify(
            [
                {
                    "id": r[0],
                    "name": r[1],
                    "dose": r[2],
                    "time": r[3],
                    "frequency": r[4],
                    "enabled": bool(r[5]),
                }
                for r in rows
            ]
        )
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        with db._lock:  # noqa: SLF001
            db._conn.execute(
                """INSERT INTO medications(name, dose, time, frequency, enabled)
                   VALUES (?, ?, ?, ?, 1)""",
                (data["name"], data.get("dose", ""), data["time"], data.get("frequency", "daily")),
            )
        db.close()
        return jsonify({"ok": True})
    if request.method == "DELETE":
        med_id = int(request.args.get("id", 0))
        with db._lock:  # noqa: SLF001
            db._conn.execute("DELETE FROM medications WHERE id=?", (med_id,))
        db.close()
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        current = asdict(TUNABLES)
        current.update({k: v for k, v in data.items() if k in current})
        Tunables(**current).save()
        reload_tunables()
        db = _db()
        db.push_inbox("config_reloaded", {})
        db.close()
        return jsonify({"ok": True})
    return jsonify(asdict(TUNABLES))


@app.route("/api/sleep")
def api_sleep():
    db = _db()
    with db._lock:  # noqa: SLF001
        rows = db._conn.execute(
            """SELECT night_of, duration_s, left_pct, right_pct, back_pct,
                      front_pct, score, nudges FROM sleep_log
               ORDER BY id DESC LIMIT 14"""
        ).fetchall()
    db.close()
    return jsonify(
        [
            {
                "night_of": r[0],
                "duration_s": r[1],
                "left_pct": r[2],
                "right_pct": r[3],
                "back_pct": r[4],
                "front_pct": r[5],
                "score": r[6],
                "nudges": r[7],
            }
            for r in rows
        ]
    )


@app.route("/api/export.<fmt>")
def api_export(fmt: str):
    db = _db()
    events = db.recent_events(limit=10000)
    db.close()
    if fmt == "json":
        return jsonify(events)
    if fmt == "csv":
        lines = ["ts,kind,payload"]
        for e in events:
            lines.append(
                f'{e["ts"]},{e["kind"]},"{json.dumps(e["payload"]).replace(chr(34), chr(39))}"'
            )
        return Response("\n".join(lines), mimetype="text/csv")
    return jsonify({"ok": False}), 400


@app.route("/backup.zip")
def backup_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if DB_PATH.exists():
            z.write(DB_PATH, DB_PATH.name)
        if CONFIG_PATH.exists():
            z.write(CONFIG_PATH, CONFIG_PATH.name)
        if FOODS_PATH.exists():
            z.write(FOODS_PATH, FOODS_PATH.name)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"sentinel-backup-{datetime.now():%Y%m%d-%H%M%S}.zip",
    )


def run() -> None:  # pragma: no cover - systemd entrypoint
    app.run(host="0.0.0.0", port=80, debug=False)


if __name__ == "__main__":  # pragma: no cover
    import sys

    port = 5000 if "--dev" in sys.argv else 80
    app.run(host="0.0.0.0", port=port, debug="--dev" in sys.argv)

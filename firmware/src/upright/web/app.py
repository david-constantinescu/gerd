"""Flask PWA served on the LAN at http://<hostname>.local (mDNS) / port 80.

Runs as its own systemd unit (``upright-web.service``) so a webapp crash
cannot kill the firmware loop. The two processes share only the SQLite file
at ``firmware/data/upright.db``.

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

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from ..config import CONFIG_PATH, DB_PATH, FOODS_PATH, TUNABLES, Tunables, reload_tunables
from ..services import analytics as analytics_service
from ..services import demo_seed
from ..services import foods as foods_service
from ..services.logger import Logger
from .auth import (
    is_authenticated,
    login_user,
    logout_user,
    require_login,
    session_secret,
    verify_credentials,
)
from .shell import PtyShell

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
app.secret_key = session_secret()

# Inbox kinds the firmware handles in ModeManager._handle_inbox
DEVICE_COMMANDS: dict[str, str] = {
    "meal": "meal",
    "symptom": "cmd_symptom",
    "water": "water",
    "calibrate": "calibrate",
    "sleep": "cmd_sleep",
    "open_menu": "cmd_open_menu",
    "haptic": "cmd_haptic",
    "demo_enter": "cmd_demo_enter",
    "demo_exit": "cmd_demo_exit",
    "idle": "cmd_idle",
    "med_ack": "med_ack",
    "config_reload": "config_reloaded",
}


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


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        user = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if verify_credentials(user, password):
            login_user(user)
            nxt = request.args.get("next") or url_for("control_panel")
            return redirect(nxt)
        return render_template(
            "login.html", active="control", error="Invalid username or password"
        ), 401
    if is_authenticated():
        return redirect(url_for("control_panel"))
    return render_template("login.html", active="control")


@app.post("/logout")
def logout_page():
    logout_user()
    return redirect(url_for("login_page"))


@app.route("/control")
@require_login
def control_panel():
    return render_template(
        "control.html",
        active="control",
        username=session.get("username", ""),
        commands=sorted(DEVICE_COMMANDS.keys()),
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


@app.post("/api/device/command")
@require_login
def api_device_command():
    """Queue a command for the firmware loop (processed within ~1 s)."""
    data = request.get_json(silent=True) or {}
    cmd = (data.get("command") or "").strip()
    if cmd not in DEVICE_COMMANDS:
        return jsonify({"ok": False, "error": f"unknown command: {cmd}"}), 400
    payload = data.get("payload") or {}
    db = _db()
    db.push_inbox(DEVICE_COMMANDS[cmd], payload)
    db.close()
    return jsonify({"ok": True, "command": cmd, "queued": DEVICE_COMMANDS[cmd]})


@app.get("/api/device/commands")
@require_login
def api_device_commands():
    return jsonify({"commands": sorted(DEVICE_COMMANDS.keys())})


@app.get("/api/auth/status")
def api_auth_status():
    return jsonify({"authenticated": is_authenticated(), "username": session.get("username")})


@app.post("/api/log/meal")
def api_log_meal():
    data = request.get_json(silent=True) or {}
    notes = str(data.get("notes", ""))
    window_s = TUNABLES.post_meal_default_hours * 3600.0
    db = _db()
    db.event_now("meal", {"notes": notes, "window_s": window_s})
    db.push_inbox("meal", {"notes": notes, "window_s": window_s})
    db.close()
    return jsonify({"ok": True, "queued": True})


@app.post("/api/log/symptom")
def api_log_symptom():
    data = request.get_json(silent=True) or {}
    payload = {
        "severity": int(data.get("severity", 1)),
        "type": data.get("type", "Heartburn"),
        "notes": data.get("notes", ""),
    }
    db = _db()
    db.event_now("symptom", payload)
    db.push_inbox("symptom", payload)
    db.close()
    return jsonify({"ok": True})


@app.post("/api/log/water")
def api_log_water():
    db = _db()
    db.event_now("water", {})
    db.push_inbox("water", {})
    db.close()
    return jsonify({"ok": True})


@app.get("/api/terminal/output")
@require_login
def api_terminal_output():
    key = session.get("shell_key")
    if not key:
        return jsonify({"data": ""})
    return jsonify({"data": PtyShell.get(key).read()})


@app.post("/api/terminal/input")
@require_login
def api_terminal_input():
    data = request.get_json(silent=True) or {}
    key = session.get("shell_key")
    if not key:
        return jsonify({"ok": False, "error": "no shell session"}), 400
    PtyShell.get(key).write(data.get("data", ""))
    return jsonify({"ok": True})


@app.post("/api/terminal/resize")
@require_login
def api_terminal_resize():
    data = request.get_json(silent=True) or {}
    key = session.get("shell_key")
    if key:
        PtyShell.get(key).resize(
            int(data.get("rows", 24)),
            int(data.get("cols", 80)),
        )
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
            gerd_score=data.get("gerd_score"),
        )
        foods_service.reload()
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


def _wifi_change_allowed() -> bool:
    """Wi-Fi scan/connect needs login normally, but is open during first-time
    setup (no client connection yet) — the only network then is the setup AP the
    user physically joined, so there's no untrusted LAN to protect against."""
    from ..services import wifi as wifi_service

    return is_authenticated() or not wifi_service.is_client_connected()


@app.get("/api/wifi/status")
def api_wifi_status():
    """Current network identity — how to reach this device on the LAN."""
    from ..services import netinfo
    from ..services import wifi as wifi_service

    info = netinfo.status()
    info["ssid"] = wifi_service.current_ssid()
    info["manageable"] = wifi_service.is_available()
    info["connected"] = wifi_service.is_client_connected()
    info["setup_mode"] = wifi_service.is_ap_active() or not wifi_service.is_client_connected()
    info["setup_ssid"] = wifi_service.SETUP_AP_SSID
    return jsonify(info)


@app.get("/api/wifi/qr.png")
def api_wifi_qr():
    """QR code of the dashboard URL — scan to open from any phone on the LAN."""
    from ..services import netinfo

    url = request.args.get("url") or netinfo.dashboard_url()
    png = netinfo.qr_png_bytes(url, scale=6, border=3)
    if png is None:
        return ("QR unavailable", 503)
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/wifi/scan")
def api_wifi_scan():
    from ..services import wifi as wifi_service

    if not _wifi_change_allowed():
        return jsonify({"error": "login required"}), 401
    return jsonify({"networks": wifi_service.scan(), "available": wifi_service.is_available()})


@app.post("/api/wifi/connect")
def api_wifi_connect():
    from ..services import wifi as wifi_service

    if not _wifi_change_allowed():
        return jsonify({"error": "login required"}), 401
    data = request.get_json(silent=True) or {}
    ok, msg = wifi_service.connect(
        (data.get("ssid") or "").strip(), data.get("password") or None
    )
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@app.route("/api/analytics")
def api_analytics():
    days = min(int(request.args.get("days", 7)), 30)
    db = _db()
    summary = analytics_service.week_summary(db, days=days)
    db.close()
    return jsonify(summary)


@app.post("/api/demo/enter")
@require_login
def api_demo_enter():
    db = _db()
    demo_seed.enter_demo(db)
    db.close()
    reload_tunables()
    return jsonify({"ok": True, "demo_mode": True})


@app.post("/api/demo/exit")
@require_login
def api_demo_exit():
    db = _db()
    demo_seed.exit_demo(db)
    db.close()
    reload_tunables()
    return jsonify({"ok": True, "demo_mode": False})


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
        download_name=f"upright-backup-{datetime.now():%Y%m%d-%H%M%S}.zip",
    )


def run() -> None:  # pragma: no cover - systemd entrypoint
    app.run(host="0.0.0.0", port=80, debug=False)


if __name__ == "__main__":  # pragma: no cover
    import sys

    port = 5000 if "--dev" in sys.argv else 80
    app.run(host="0.0.0.0", port=port, debug="--dev" in sys.argv)

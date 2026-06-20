"""Flask server: serves the browser bench, streams the screen, and exposes the
HTTP/JSON control API used by both the UI and external agents (AI-controllable).

Endpoints
---------
GET  /                      bench UI
GET  /api/state             full device snapshot (FSM, sensors, motor, audio, log)
GET  /screen.png[?scale=N]  current panel frame as PNG (native 160x128 * scale)
GET  /stream.mjpeg          live MJPEG screen stream
POST /api/button            {"button":"a|b","pattern":"single|double|triple"}
POST /api/encoder           {"action":"cw|ccw|click"}
POST /api/posture           {"pitch":<deg>,"roll":<deg>}
POST /api/battery           {"pct":0-100,"low":bool}
POST /api/hrv               {"bpm":<n>,"rmssd":<ms>}
POST /api/camera/frame      raw image bytes (image/*) or {"image":"<dataURL|base64>"}
POST /api/command           {"command":"<inbox-kind>","payload":{...}}  (mirrors the PWA)
"""

from __future__ import annotations

import base64
import io
import logging
import time

from flask import Flask, Response, jsonify, request, send_from_directory
from PIL import Image

from .runner import SIM_ROOT
from .state import SimDevice

log = logging.getLogger("sim.server")

WEB_DIR = SIM_ROOT / "web"

# Friendly command name -> raw inbox kind, mirrored exactly from the firmware's
# web app (web/app.py DEVICE_COMMANDS) so the API matches the real PWA. Raw
# kinds (cmd_open_menu, etc.) are also accepted directly.
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


def create_app(dev: SimDevice) -> Flask:
    app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")

    @app.get("/")
    def index():
        return send_from_directory(str(WEB_DIR), "index.html")

    # ---------------------------------------------------------------- outputs
    @app.get("/api/state")
    def api_state():
        return jsonify(dev.snapshot())

    @app.get("/api/log")
    def api_log():
        return jsonify({"log": list(dev.log_lines)[:120]})

    @app.get("/screen.png")
    def screen_png():
        scale = max(1, min(8, int(request.args.get("scale", 1))))
        png = dev.frame_png(scale=scale)
        if png is None:
            return ("no frame yet", 503)
        return Response(png, mimetype="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/stream.mjpeg")
    def stream_mjpeg():
        def gen():
            last = -1
            boundary = b"--frame"
            while True:
                last = dev.wait_frame(last, timeout=1.0)
                jpeg = dev.frame_jpeg()
                if jpeg is None:
                    time.sleep(0.1)
                    continue
                yield (boundary + b"\r\nContent-Type: image/jpeg\r\n"
                       + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                       + jpeg + b"\r\n")

        return Response(gen(),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    # ----------------------------------------------------------------- inputs
    @app.post("/api/button")
    def api_button():
        data = request.get_json(silent=True) or {}
        dev.press(str(data.get("button", "a")), str(data.get("pattern", "single")))
        return jsonify({"ok": True})

    @app.post("/api/encoder")
    def api_encoder():
        data = request.get_json(silent=True) or {}
        dev.encoder(str(data.get("action", "")))
        return jsonify({"ok": True})

    @app.post("/api/posture")
    def api_posture():
        data = request.get_json(silent=True) or {}
        dev.set_posture(data.get("pitch"), data.get("roll"))
        return jsonify({"ok": True, "pitch": dev.pitch, "roll": dev.roll})

    @app.post("/api/battery")
    def api_battery():
        data = request.get_json(silent=True) or {}
        dev.set_battery(data.get("pct"), data.get("low"))
        return jsonify({"ok": True, "pct": dev.battery_pct, "low": dev.battery_low})

    @app.post("/api/hrv")
    def api_hrv():
        data = request.get_json(silent=True) or {}
        if dev.bus is None:
            return jsonify({"ok": False, "error": "firmware not ready"}), 503
        from upright.events import Event, EventType

        dev.bus.publish(Event(EventType.HRV_SAMPLE, payload={
            "bpm": data.get("bpm"), "rmssd": data.get("rmssd"),
        }))
        return jsonify({"ok": True})

    @app.post("/api/camera/frame")
    def api_camera_frame():
        img = _read_image(request)
        if img is None:
            return jsonify({"ok": False, "error": "no image"}), 400
        dev.set_camera_frame(img)
        return jsonify({"ok": True})

    @app.post("/api/command")
    def api_command():
        data = request.get_json(silent=True) or {}
        cmd = str(data.get("command", "")).strip()
        if not cmd:
            return jsonify({"ok": False, "error": "missing command"}), 400
        kind = DEVICE_COMMANDS.get(cmd, cmd)  # friendly name → raw inbox kind
        payload = data.get("payload") or {}
        try:
            import upright.config as cfg
            from upright.services.logger import Logger

            db = Logger(path=str(cfg.DB_PATH))
            db.push_inbox(kind, payload)
            db.close()
        except Exception as e:
            log.exception("command failed")
            return jsonify({"ok": False, "error": str(e)}), 500
        return jsonify({"ok": True, "command": cmd, "queued": kind})

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True, "booted": dev.booted.is_set()})

    return app


def _read_image(req) -> Image.Image | None:
    """Accept raw image bytes, a multipart file, or a base64/dataURL JSON field."""
    ctype = req.content_type or ""
    try:
        if ctype.startswith("image/"):
            return Image.open(io.BytesIO(req.get_data()))
        if "multipart/form-data" in ctype and req.files:
            f = next(iter(req.files.values()))
            return Image.open(f.stream)
        data = req.get_json(silent=True) or {}
        raw = data.get("image")
        if isinstance(raw, str):
            if "," in raw and raw.strip().startswith("data:"):
                raw = raw.split(",", 1)[1]
            return Image.open(io.BytesIO(base64.b64decode(raw)))
    except Exception:
        log.exception("could not decode camera frame")
    return None

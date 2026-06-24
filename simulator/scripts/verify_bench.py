#!/usr/bin/env python3
"""End-to-end verification of the Pi simulator bench + HTTP API."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8800"
PIZZA = Path("/tmp/pizza_test.jpg")
SIM_CONFIG = Path(__file__).resolve().parents[1] / ".simdata" / "config.json"
SIM_DB = Path(__file__).resolve().parents[1] / ".simdata" / "upright.db"


def get(path: str) -> tuple[int, bytes]:
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.status, r.read()


def post_json(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def post_bytes(path: str, body: bytes, ctype: str) -> int:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": ctype},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.status


def state() -> dict:
    _, raw = get("/api/state")
    return json.loads(raw)["fsm"]


def press(btn: str, pattern: str = "single") -> None:
    post_json("/api/button", {"button": btn, "pattern": pattern})
    time.sleep(0.7)


def wait_until(cond, timeout: float = 8.0, interval: float = 0.25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return False


def idle() -> None:
    post_json("/api/command", {"command": "idle"})
    # Inbox is drained ~once per second in the firmware loop.
    time.sleep(1.2)
    wait_until(
        lambda: state().get("state") == "idle" and not state().get("menu_open"),
        timeout=6.0,
    )


def nav_settings() -> None:
    """Main menu → Settings sub-screen."""
    press("b")
    wait_until(lambda: state().get("menu_open"), timeout=3.0)
    for _ in range(4):
        press("a")
    wait_until(lambda: state().get("menu_index") == 4, timeout=3.0)
    press("b")
    wait_until(lambda: state().get("menu_screen") == "settings", timeout=3.0)


def main() -> int:
    ok = fail = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  PASS  {name}")
        else:
            fail += 1
            print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))

    print(f"Simulator verification @ {BASE}\n")

    try:
        st, body = get("/api/health")
        health = json.loads(body)
        check("GET /api/health", st == 200 and health.get("ok"), str(health))
    except urllib.error.URLError as e:
        check("GET /api/health", False, str(e))
        print("\nSimulator not reachable.")
        return 1

    st, html = get("/")
    check("GET / bench HTML", st == 200 and b"Pi Simulator" in html)
    st, png = get("/screen.png")
    check("GET /screen.png", st == 200 and len(png) > 500)
    try:
        req = urllib.request.Request(f"{BASE}/stream.mjpeg")
        with urllib.request.urlopen(req, timeout=3) as r:
            chunk = r.read(120)
        check("GET /stream.mjpeg", b"--frame" in chunk)
    except urllib.error.URLError as e:
        check("GET /stream.mjpeg", False, str(e))

    batt = post_json("/api/battery", {"pct": 72, "low": False})
    check("POST /api/battery", batt.get("ok") and batt.get("pct") == 72)
    post_json("/api/posture", {"pitch": 4, "roll": 0})
    check(
        "POST /api/posture",
        wait_until(lambda: state().get("ctx_pitch") == 4.0, timeout=3.0),
    )

    # --- main menu opens ---
    idle()
    press("b")
    check("menu opens", wait_until(lambda: state().get("menu_open"), timeout=3.0))

    # --- log water (main index 2) ---
    idle()
    press("b")
    press("a")
    press("a")
    check("water highlighted", state().get("menu_index") == 2)
    press("b")
    check("log water flash", state().get("menu_screen") == "flash", str(state()))

    # --- quick symptom (B double on watch) ---
    idle()
    press("b", "double")
    check("quick symptom flash", state().get("menu_screen") == "flash")

    # --- settings → network QR ---
    idle()
    nav_settings()
    press("a")
    press("a")
    press("b")  # network (settings index 2)
    check("network screen", state().get("menu_screen") == "network", str(state()))
    check(
        "wifi setup AP active",
        wait_until(
            lambda: json.loads(get("/api/state")[1]).get("wifi", {}).get("mode") == "ap",
            timeout=12.0,
        ),
    )
    check(
        "network screen setup mode",
        wait_until(lambda: state().get("net_mode") == "setup", timeout=4.0),
        f"net_mode={state().get('net_mode')}",
    )
    post_json("/api/wifi/sim/connect", {"ssid": "SimHome", "password": "secret"})
    check(
        "wifi client connect",
        wait_until(
            lambda: json.loads(get("/api/state")[1]).get("wifi", {}).get("mode") == "client",
            timeout=6.0,
        ),
    )
    idle()
    nav_settings()
    press("a")
    press("a")
    press("b")
    check(
        "network screen online mode",
        wait_until(lambda: state().get("net_mode") == "online", timeout=4.0),
        f"net_mode={state().get('net_mode')}",
    )
    check(
        "network setup QR mode",
        state().get("net_mode") == "setup",
        f"net_mode={state().get('net_mode')}",
    )

    # --- language → Romanian ---
    idle()
    nav_settings()
    press("a")
    press("a")
    press("a")
    press("b")  # language (settings index 3)
    press("a")
    press("b")  # Română (index 1)
    check(
        "language saved ro",
        wait_until(
            lambda: json.loads(SIM_CONFIG.read_text()).get("language") == "ro",
            timeout=4.0,
        ),
    )

    # --- food photo flow ---
    if PIZZA.exists():
        post_bytes("/api/camera/frame", PIZZA.read_bytes(), "image/jpeg")
        idle()
        press("b")  # open menu → Log Meal
        press("b")  # confirm meal
        press("b")  # yes
        press("b")  # capture
        check(
            "food result screen",
            wait_until(lambda: state().get("menu_screen") == "food_result", timeout=12.0),
            str(state()),
        )
    else:
        check("food photo flow", False, "missing test image")

    # --- sleep mode (menu index 5) ---
    idle()
    press("b")
    for _ in range(5):
        press("a")
    press("b")
    check("sleep → pre_sleep", state().get("state") == "pre_sleep", str(state()))

    # --- inbox commands ---
    idle()
    time.sleep(1.0)
    post_json("/api/command", {"command": "open_menu"})
    check("inbox open_menu", wait_until(lambda: state().get("menu_open"), timeout=3.0))
    def motor_count() -> int:
        _, raw = get("/api/state")
        return len(json.loads(raw).get("motor") or [])

    idle()
    post_json("/api/command", {"command": "haptic"})
    check("haptic motor event", wait_until(lambda: motor_count() > 0, timeout=3.0))

    # --- week stats (settings index 1) ---
    idle()
    nav_settings()
    press("a")
    press("b")
    check(
        "week stats screen",
        wait_until(lambda: state().get("menu_screen") == "stats", timeout=5.0),
        str(state()),
    )
    press("b")  # done
    check("stats dismiss", state().get("menu_screen") != "stats")

    # --- slouch posture ---
    idle()
    post_json("/api/posture", {"pitch": 22, "roll": 4})
    wait_until(lambda: state().get("ctx_pitch", 0) >= 20.0, timeout=5.0)
    post_json("/api/posture", {"pitch": 30, "roll": 4})
    check(
        "slouch posture applied",
        wait_until(lambda: state().get("ctx_pitch", 0) >= 23.0, timeout=6.0),
        f"pitch={state().get('ctx_pitch')}",
    )

    # --- DB events ---
    try:
        import sqlite3

        con = sqlite3.connect(SIM_DB)
        n_water = con.execute("SELECT COUNT(*) FROM events WHERE kind='water'").fetchone()[0]
        n_sym = con.execute("SELECT COUNT(*) FROM events WHERE kind='symptom'").fetchone()[0]
        con.close()
        check("water events in DB", n_water >= 1, f"count={n_water}")
        check("symptom events in DB", n_sym >= 1, f"count={n_sym}")
    except Exception as e:
        check("DB events", False, str(e))

    print(f"\n{'=' * 40}\n{ok} passed, {fail} failed\n")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

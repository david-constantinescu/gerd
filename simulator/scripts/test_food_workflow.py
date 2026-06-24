#!/usr/bin/env python3
"""Test food recognition end-to-end: direct classify + simulator menu flow."""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

# Food photos (Unsplash, stable IDs). expected = substring we expect in detected name.
FOOD_CASES = [
    {
        "id": "pizza",
        "url": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=480",
        "expect_in": ("pizza", "pepperoni", "lasagne", "cheese"),
        "expect_risk": None,  # model may vary; sim should still classify
    },
    {
        "id": "pepperoni_pizza",
        "url": "https://images.unsplash.com/photo-1628840042765-356cda07504e?w=480",
        "expect_in": ("pizza", "pepperoni"),
        "expect_risk": "HIGH",
    },
    {
        "id": "caesar_salad",
        "url": "https://images.unsplash.com/photo-1546793665-c74683f339c1?w=480",
        "expect_in": ("salad", "caesar", "lettuce"),
        "expect_risk": "LOW",
    },
    {
        "id": "banana",
        "url": "https://images.unsplash.com/photo-1603833665858-e61d17a86224?w=480",
        "expect_in": ("banana", "plantain", "fruit"),
        "expect_risk": None,
        "optional": True,  # Food-101 has no plain banana class; CLIP may miss
    },
    {
        "id": "sushi",
        "url": "https://images.unsplash.com/photo-1579584425555-c3ce17fd4351?w=480",
        "expect_in": ("sushi", "sashimi", "nigiri"),
        "expect_risk": None,
    },
    {
        "id": "oatmeal",
        "url": "https://images.unsplash.com/photo-1517673400269-4fdfa8ca3a0b?w=480",
        "expect_in": ("oatmeal", "porridge", "cereal", "congee", "rice"),
        "expect_risk": None,
        "optional": True,
    },
    {
        "id": "burger",
        "url": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=480",
        "expect_in": ("burger", "cheeseburger", "hamburger"),
        "expect_risk": "HIGH",
    },
    {
        "id": "apple_pie",
        "url": "https://images.unsplash.com/photo-1621303833174-89730373bc89?w=480",
        "expect_in": ("apple", "pie", "dessert", "cake"),
        "expect_risk": "HIGH",
        "optional": True,
    },
]

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8800"
FIXTURES = Path(__file__).resolve().parent / "food_fixtures"
SIM_DB = Path(__file__).resolve().parents[1] / ".simdata" / "upright.db"
FIRMWARE_SRC = Path(__file__).resolve().parents[2] / "firmware" / "src"


def download_fixture(case: dict) -> Path:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    dest = FIXTURES / f"{case['id']}.jpg"
    if dest.exists() and dest.stat().st_size > 5000:
        return dest
    for url in (case["url"], case.get("url_fallback")):
        if not url:
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "upright-food-test/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) > 3000:
                dest.write_bytes(data)
                return dest
        except (urllib.error.URLError, OSError):
            continue
    raise OSError(f"could not download {case['id']}")


def classify_local(image_path: Path) -> dict | None:
    sys.path.insert(0, str(FIRMWARE_SRC))
    from PIL import Image

    from upright.services import foods

    img = Image.open(image_path).convert("RGB")
    result = foods.classify(img)
    if result is None:
        return None
    return {
        "name": result.name,
        "risk": result.risk,
        "gerd_score": result.gerd_score,
        "confidence": round(result.confidence, 3),
        "label": result.label,
        "advice": result.advice,
        "upright_hours": result.upright_hours,
    }


def post_json(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_image(path: str, image_path: Path) -> None:
    data = image_path.read_bytes()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "image/jpeg"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def fsm() -> dict:
    req = urllib.request.Request(f"{BASE}/api/state")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["fsm"]


def press(btn: str, pattern: str = "single") -> None:
    post_json("/api/button", {"button": btn, "pattern": pattern})
    time.sleep(0.7)


def idle() -> None:
    post_json("/api/command", {"command": "idle"})
    time.sleep(1.2)


def wait_until(cond, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.3)
    return False


def last_food_event(after_rowid: int = 0) -> dict | None:
    if not SIM_DB.exists():
        return None
    con = sqlite3.connect(SIM_DB)
    row = con.execute(
        "SELECT rowid, kind, payload, ts FROM events "
        "WHERE kind='food_photo' AND rowid > ? ORDER BY rowid DESC LIMIT 1",
        (after_rowid,),
    ).fetchone()
    con.close()
    if not row:
        return None
    payload = json.loads(row[2]) if row[2] else {}
    return {"rowid": row[0], "ts": row[3], **payload}


def food_event_count() -> int:
    if not SIM_DB.exists():
        return 0
    con = sqlite3.connect(SIM_DB)
    n = con.execute("SELECT COUNT(*) FROM events WHERE kind='food_photo'").fetchone()[0]
    con.close()
    return n


def max_food_rowid() -> int:
    if not SIM_DB.exists():
        return 0
    con = sqlite3.connect(SIM_DB)
    row = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM events WHERE kind='food_photo'").fetchone()
    con.close()
    return int(row[0] or 0)


def sim_meal_flow(image_path: Path) -> dict:
    """Upload frame at capture time (camera HAL expires frames after ~2.5s)."""
    before_row = max_food_rowid()
    idle()
    press("b")  # open menu → Log Meal
    press("b")  # confirm meal
    press("b")  # yes → food_photo
    wait_until(lambda: fsm().get("menu_screen") == "food_photo", timeout=6.0)
    post_image("/api/camera/frame", image_path)
    time.sleep(0.35)
    press("b")  # capture
    screen_ok = wait_until(lambda: fsm().get("menu_screen") == "food_result", timeout=18.0)
    wait_until(lambda: last_food_event(before_row) is not None or (
        fsm().get("food_result") or {}).get("name"), timeout=5.0)
    time.sleep(0.5)
    snap = json.loads(urllib.request.urlopen(f"{BASE}/api/state", timeout=10).read())
    fr = snap.get("fsm", {}).get("food_result") or {}
    ev = last_food_event(before_row)
    # Dismiss result screen before next case.
    if fsm().get("menu_screen") == "food_result":
        press("b")
    idle()
    time.sleep(0.8)
    return {
        "screen_ok": screen_ok,
        "fsm": snap.get("fsm", {}),
        "food_result": fr,
        "db_event": ev,
    }


def name_matches(name: str, expect_in: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(tok in low for tok in expect_in)


def main() -> int:
    print(f"Food workflow test @ {BASE}\n")
    print("=" * 72)

    # Health check
    try:
        req = urllib.request.Request(f"{BASE}/api/health")
        with urllib.request.urlopen(req, timeout=5) as r:
            health = json.loads(r.read())
        if not health.get("ok"):
            print("Simulator not healthy")
            return 1
    except urllib.error.URLError:
        print("Simulator not reachable — start with: cd gerd/simulator && ../firmware/.venv/bin/python run.py --port 8800")
        return 1

    direct_ok = direct_fail = 0
    sim_ok = sim_fail = 0
    direct_skip = sim_skip = 0
    rows: list[dict] = []

    for case in FOOD_CASES:
        print(f"\n--- {case['id']} ---")
        try:
            path = download_fixture(case)
            print(f"  fixture: {path.name} ({path.stat().st_size // 1024} KB)")
        except OSError as e:
            print(f"  SKIP download: {e}")
            if case.get("optional"):
                direct_skip += 1
                sim_skip += 1
            else:
                direct_fail += 1
                sim_fail += 1
            continue

        # Direct classification (same code path as device)
        try:
            direct = classify_local(path)
        except Exception as e:
            print(f"  DIRECT ERROR: {e}")
            direct = None

        if direct:
            d_ok = name_matches(direct["name"], case["expect_in"])
            if case.get("expect_risk"):
                d_ok = d_ok and direct["risk"] == case["expect_risk"]
            print(
                f"  DIRECT: {direct['name']} | {direct['risk']} "
                f"| score {direct['gerd_score']} | conf {direct['confidence']:.0%} "
                f"| label={direct['label']!r}"
            )
            print(f"           advice: {direct['advice']}")
            if d_ok:
                direct_ok += 1
                print("  DIRECT: PASS")
            elif case.get("optional"):
                direct_skip += 1
                print("  DIRECT: SKIP (optional)")
            else:
                direct_fail += 1
                print(f"  DIRECT: FAIL (expected one of {case['expect_in']}, risk {case.get('expect_risk')})")
        else:
            if case.get("optional"):
                direct_skip += 1
                print("  DIRECT: SKIP (optional, no classification)")
            else:
                direct_fail += 1
                print("  DIRECT: FAIL (no classification)")

        # Simulator menu workflow
        try:
            sim = sim_meal_flow(path)
        except Exception as e:
            print(f"  SIM ERROR: {e}")
            sim_fail += 1
            continue

        ev = sim["db_event"] or {}
        fr = sim.get("food_result") or {}
        sim_name = fr.get("name") or ev.get("name", "?")
        sim_risk = fr.get("risk") or ev.get("risk", "?")
        sim_score = fr.get("gerd_score") or ev.get("gerd_score", "?")
        s_ok = sim["screen_ok"] and sim_name != "?" and sim_name != "Not recognized"
        s_ok = s_ok and name_matches(str(sim_name), case["expect_in"])
        if case.get("expect_risk") and ev:
            s_ok = s_ok and sim_risk == case["expect_risk"]

        print(f"  SIM screen: {sim['fsm'].get('menu_screen')} state={sim['fsm'].get('state')}")
        print(f"  SIM result: {sim_name} | {sim_risk} | score {sim_score}")
        if s_ok:
            sim_ok += 1
            print("  SIM: PASS")
        elif case.get("optional"):
            sim_skip += 1
            print("  SIM: SKIP (optional)")
        else:
            sim_fail += 1
            print(f"  SIM: FAIL (expected one of {case['expect_in']}, risk {case.get('expect_risk')})")

        rows.append(
            {
                "id": case["id"],
                "direct": direct,
                "sim_db": ev,
                "direct_pass": direct is not None and name_matches(direct["name"], case["expect_in"]),
                "sim_pass": s_ok,
            }
        )

    print("\n" + "=" * 72)
    n = len(FOOD_CASES)
    print(f"DIRECT: {direct_ok}/{n} passed ({direct_skip} optional skipped)")
    print(f"SIMULATOR: {sim_ok}/{n} passed ({sim_skip} optional skipped)")
    print("=" * 72)

    # Summary table
    print(f"\n{'Food':<18} {'Detected':<22} {'Risk':<8} {'Score':<6} {'Conf':<6} {'Sim OK'}")
    print("-" * 72)
    for r in rows:
        d = r["direct"] or {}
        ev = r["sim_db"] or {}
        conf = f"{d.get('confidence', 0):.0%}" if d else "—"
        print(
            f"{r['id']:<18} "
            f"{d.get('name', '—'):<22} "
            f"{d.get('risk', '—'):<8} "
            f"{str(d.get('gerd_score', '—')):<6} "
            f"{conf:<6} "
            f"{'yes' if r['sim_pass'] else 'NO'}"
        )

    return 0 if direct_fail == 0 and sim_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

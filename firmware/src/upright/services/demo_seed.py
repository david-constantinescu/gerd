"""Load synthetic week data for demo / showroom mode."""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import DATA_DIR, DB_PATH, reload_tunables
from ..config import Tunables
from .logger import Logger

log = logging.getLogger("services.demo_seed")

DEMO_WEEK_PATH = DATA_DIR / "demo_week.json"
DEMO_SESSION_PATH = DATA_DIR / "demo_session.json"
DB_BACKUP_PATH = DATA_DIR / "upright.db.bak"


def _load_dataset() -> dict[str, Any]:
    if not DEMO_WEEK_PATH.exists():
        raise FileNotFoundError(f"missing demo dataset: {DEMO_WEEK_PATH}")
    return json.loads(DEMO_WEEK_PATH.read_text())


def _night_of(day_offset: int) -> str:
    return (datetime.now().date() + timedelta(days=day_offset)).isoformat()


def is_demo_mode() -> bool:
    from ..config import TUNABLES

    return bool(TUNABLES.demo_mode)


def set_demo_mode(enabled: bool) -> None:
    tun = Tunables.load()
    tun.demo_mode = enabled
    tun.save()
    reload_tunables()


def get_demo_session_start() -> float | None:
    if not DEMO_SESSION_PATH.exists():
        return None
    try:
        data = json.loads(DEMO_SESSION_PATH.read_text())
        return float(data.get("started_at", 0)) or None
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def _write_demo_session(started_at: float | None = None) -> float:
    ts = started_at if started_at is not None else time.time()
    DEMO_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_SESSION_PATH.write_text(
        json.dumps({"started_at": ts, "boot_count": int(time.time())})
    )
    return ts


def demo_reminder_plan() -> list[dict[str, Any]]:
    data = _load_dataset()
    plan = data.get("demo_reminders")
    if plan:
        return plan
    return [
        {"name": "Omeprazole", "minutes_after_boot": 2},
        {"name": "Famotidine", "minutes_after_boot": 8},
    ]


def demo_med_details(name: str) -> dict[str, str]:
    """Lookup brand + dose for a medication name from the demo dataset."""
    for med in _load_dataset().get("medications", []):
        if med.get("name") == name:
            return {
                "name": str(med.get("name", name)),
                "brand": str(med.get("brand", med.get("name", name))),
                "dose": str(med.get("dose", "")),
            }
    return {"name": name, "brand": name, "dose": ""}


def restart_demo_on_boot(db: Logger) -> None:
    """Fresh synthetic timeline every boot while demo_mode is enabled."""
    log.info("demo mode boot — reseeding synthetic week")
    _clear_user_tables(db)
    _seed_from_json(db, _load_dataset())
    _write_demo_session()
    db.flush()


def enter_demo(db: Logger) -> None:
    """Back up live DB, clear user tables, seed synthetic week."""
    db.flush()
    if not is_demo_mode() and DB_PATH.exists():
        shutil.copy2(DB_PATH, DB_BACKUP_PATH)
        log.info("backed up database to %s", DB_BACKUP_PATH)
    _clear_user_tables(db)
    _seed_from_json(db, _load_dataset())
    _write_demo_session()
    set_demo_mode(True)
    log.info("demo mode enabled — synthetic week loaded")


def exit_demo(db: Logger) -> None:
    """Restore pre-demo database if a backup exists."""
    db.flush()
    set_demo_mode(False)
    DEMO_SESSION_PATH.unlink(missing_ok=True)
    if DB_BACKUP_PATH.exists():
        shutil.copy2(DB_BACKUP_PATH, DB_PATH)
        DB_BACKUP_PATH.unlink(missing_ok=True)
        db.reconnect()
        log.info("restored database from backup")
    else:
        _clear_user_tables(db)
        log.info("no backup found — cleared demo data only")


def _clear_user_tables(db: Logger) -> None:
    with db._lock:  # noqa: SLF001
        for table in (
            "events",
            "posture_log",
            "sleep_log",
            "medications",
            "inbox",
        ):
            db._conn.execute(f"DELETE FROM {table}")
        db._conn.execute("DELETE FROM sessions WHERE ended_at IS NULL")


def _seed_from_json(db: Logger, data: dict[str, Any]) -> None:
    now = time.time()
    with db._lock:  # noqa: SLF001
        for med in data.get("medications", []):
            db._conn.execute(
                """INSERT INTO medications(name, dose, time, frequency, enabled)
                   VALUES (?, ?, ?, ?, 1)""",
                (
                    med["name"],
                    med.get("dose", ""),
                    med["time"],
                    med.get("frequency", "daily"),
                ),
            )
        for night in data.get("sleep", []):
            db._conn.execute(
                """INSERT INTO sleep_log
                   (night_of, duration_s, left_pct, right_pct, back_pct, front_pct,
                    score, nudges, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _night_of(int(night["day_offset"])),
                    night["duration_s"],
                    night["left_pct"],
                    night["right_pct"],
                    night["back_pct"],
                    night["front_pct"],
                    night["score"],
                    night["nudges"],
                    json.dumps({"demo": True}),
                ),
            )
        for ev in data.get("events", []):
            ts = now + float(ev["offset_hours"]) * 3600.0
            db._conn.execute(
                "INSERT INTO events(ts, kind, payload) VALUES (?, ?, ?)",
                (ts, ev["kind"], json.dumps(ev.get("payload") or {})),
            )
        for hours_ago in range(0, 168, 4):
            ts = now - hours_ago * 3600
            pitch = 6.0 if hours_ago % 8 == 0 else -4.0
            db._conn.execute(
                "INSERT INTO posture_log(ts, pitch, roll, state) VALUES (?, ?, ?, ?)",
                (ts, pitch, 2.0, "idle"),
            )
        db._conn.execute(
            "INSERT INTO sessions(started_at, wear_side) VALUES (?, ?)",
            (now - 7 * 86400, "left"),
        )


def seed_demo_db(path: Path) -> None:
    """CLI helper: write a fresh demo-only database file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    db = Logger(path=str(path))
    _seed_from_json(db, _load_dataset())
    db.flush()
    db.close()

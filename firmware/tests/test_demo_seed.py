"""Demo dataset seeding and restore."""

from __future__ import annotations

from pathlib import Path

from upright.services import demo_seed
from upright.services.demo_seed import (
    enter_demo,
    exit_demo,
    is_demo_mode,
    restart_demo_on_boot,
)
from upright.services.logger import Logger


def test_enter_demo_populates_week(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "demo.db"
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("upright.services.demo_seed.DB_PATH", db_path)
    monkeypatch.setattr("upright.services.demo_seed.DB_BACKUP_PATH", tmp_path / "bak.db")
    monkeypatch.setattr("upright.config.CONFIG_PATH", cfg_path)

    db = Logger(path=str(db_path))
    enter_demo(db)

    assert is_demo_mode()
    meals = db.recent_events(limit=200)
    assert any(e["kind"] == "meal" for e in meals)
    assert any(e["kind"] == "food_photo" for e in meals)
    with db._lock:  # noqa: SLF001
        nights = db._conn.execute("SELECT COUNT(*) FROM sleep_log").fetchone()[0]
        meds = db._conn.execute("SELECT COUNT(*) FROM medications").fetchone()[0]
    assert nights == 7
    assert meds == 2

    exit_demo(db)
    assert not is_demo_mode()
    db.close()


def test_restart_demo_on_boot_fresh_session(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "demo.db"
    cfg_path = tmp_path / "config.json"
    session_path = tmp_path / "demo_session.json"
    monkeypatch.setattr(demo_seed, "DB_PATH", db_path)
    monkeypatch.setattr(demo_seed, "DB_BACKUP_PATH", tmp_path / "bak.db")
    monkeypatch.setattr(demo_seed, "DEMO_SESSION_PATH", session_path)
    monkeypatch.setattr("upright.config.CONFIG_PATH", cfg_path)

    db = Logger(path=str(db_path))
    enter_demo(db)
    with db._lock:  # noqa: SLF001
        before = db._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    restart_demo_on_boot(db)
    assert session_path.exists()
    assert demo_seed.get_demo_session_start() is not None
    plan = demo_seed.demo_reminder_plan()
    assert len(plan) >= 1
    details = demo_seed.demo_med_details("Omeprazole")
    assert details["brand"]
    assert details["dose"]

    with db._lock:  # noqa: SLF001
        after = db._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert after == before

    exit_demo(db)
    assert not session_path.exists()
    db.close()

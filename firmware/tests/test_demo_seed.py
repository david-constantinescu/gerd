"""Demo dataset seeding and restore."""

from __future__ import annotations

from pathlib import Path

from upright.services.demo_seed import enter_demo, exit_demo, is_demo_mode
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

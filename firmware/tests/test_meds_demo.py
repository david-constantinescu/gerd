"""Demo-mode medication reminder scheduling."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from unittest.mock import patch

from upright.config import reload_tunables
from upright.events import EventBus, EventType
from upright.services import demo_seed
from upright.services.logger import Logger
from upright.services.meds import MedReminders


def test_demo_schedule_single_reminder_30s_after_boot(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    session = tmp_path / "demo_session.json"
    monkeypatch.setattr("upright.config.CONFIG_PATH", cfg)
    monkeypatch.setattr(demo_seed, "DEMO_SESSION_PATH", session)
    monkeypatch.setattr(demo_seed, "DB_PATH", tmp_path / "db.sqlite")
    monkeypatch.setattr(demo_seed, "DB_BACKUP_PATH", tmp_path / "bak.sqlite")

    cfg.write_text('{"demo_mode": true}')
    reload_tunables()

    boot = time.time() - 10.0
    session.write_text(f'{{"started_at": {boot}}}')

    db = Logger(path=str(tmp_path / "up.sqlite"))
    bus = EventBus()
    meds = MedReminders(bus, db)

    assert list(meds._next.keys()) == ["Omeprazole"]
    when = meds._next["Omeprazole"]
    assert when == datetime.fromtimestamp(boot) + timedelta(seconds=30)

    with patch("upright.services.demo_seed.is_demo_mode", return_value=True):
        meds.tick()
    assert bus.get(timeout=0) is None

    with patch("upright.services.demo_seed.is_demo_mode", return_value=True):
        with patch(
            "upright.services.meds.datetime",
            wraps=datetime,
        ) as mock_dt:
            mock_dt.now.return_value = datetime.fromtimestamp(boot + 31)
            meds.tick()
    ev = bus.get(timeout=0)
    assert ev is not None
    assert ev.type == EventType.MED_REMINDER
    assert ev.payload["name"] == "Omeprazole"
    assert ev.payload.get("demo") is True

    with patch("upright.services.demo_seed.is_demo_mode", return_value=True):
        with patch(
            "upright.services.meds.datetime",
            wraps=datetime,
        ) as mock_dt:
            mock_dt.now.return_value = datetime.fromtimestamp(boot + 600)
            for _ in range(20):
                meds.tick()
    assert bus.get(timeout=0) is None

    db.close()


def test_demo_reminder_plan_default_30_seconds(monkeypatch) -> None:
    monkeypatch.setattr(
        demo_seed,
        "_load_dataset",
        lambda: {"demo_reminders": []},
    )
    plan = demo_seed.demo_reminder_plan()
    assert plan == [{"name": "Omeprazole", "seconds_after_boot": 30}]

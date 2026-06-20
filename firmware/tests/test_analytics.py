"""Week analytics summaries."""

from __future__ import annotations

from upright.services.analytics import oled_lines, week_summary
from upright.services.demo_seed import _load_dataset, _seed_from_json
from upright.services.logger import Logger


def test_week_summary_after_seed(tmp_path) -> None:
    db = Logger(path=str(tmp_path / "a.db"))
    _seed_from_json(db, _load_dataset())
    db.flush()
    summary = week_summary(db, days=7)
    assert summary["meals"] >= 10
    assert summary["symptoms"] >= 3
    assert summary["avg_sleep_score"] is not None
    assert summary["avg_reflux_score"] is not None
    assert len(summary["sleep_nights"]) == 7
    lines = oled_lines(summary)
    assert any("meals" in ln for ln in lines)
    db.close()

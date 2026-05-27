import json

from upright.services.logger import Logger


def test_events_roundtrip(tmp_path):
    db = Logger(path=str(tmp_path / "t.db"))
    db.boot_session(wear_side="right")
    db.event("meal", {"notes": "pizza"})
    db.event("symptom", {"severity": 2})
    db.flush()
    rows = db.recent_events(limit=10)
    assert len(rows) == 2
    assert rows[0]["kind"] == "symptom"
    assert rows[1]["payload"]["notes"] == "pizza"
    db.close()


def test_inbox_roundtrip(tmp_path):
    db = Logger(path=str(tmp_path / "t2.db"))
    db.push_inbox("meal", {"notes": "salad"})
    pending = db.consume_inbox()
    assert len(pending) == 1
    assert pending[0]["kind"] == "meal"
    assert json.dumps(pending[0]["payload"]).find("salad") >= 0
    # second consume is empty
    assert db.consume_inbox() == []
    db.close()


def test_sleep_summary(tmp_path):
    db = Logger(path=str(tmp_path / "t3.db"))
    db.sleep_summary(
        night_of="2026-04-08",
        duration_s=25000,
        left_pct=70.0,
        right_pct=20.0,
        back_pct=10.0,
        front_pct=0.0,
        score=70,
        nudges=1,
    )
    db.flush()
    with db._lock:
        row = db._conn.execute("SELECT night_of, score, nudges FROM sleep_log").fetchone()
    assert row == ("2026-04-08", 70, 1)
    db.close()

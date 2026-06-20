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


def test_recovers_from_corrupt_db(tmp_path):
    """A malformed database file must be quarantined and replaced, not crash."""
    path = tmp_path / "corrupt.db"
    path.write_bytes(b"SQLite format 3\x00" + b"\xde\xad\xbe\xef" * 256)  # junk
    db = Logger(path=str(path))  # must not raise
    db.boot_session()
    db.event_now("meal", {"notes": "ok"})
    db.flush()
    assert len(db.recent_events(limit=5)) == 1
    db.close()
    # the bad file was preserved for forensics
    assert list(tmp_path.glob("corrupt.db.corrupt-*"))


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

"""Meal–symptom correlation analytics."""

import time

from upright.services import analytics
from upright.services.logger import Logger


def test_meal_symptom_correlation(tmp_path):
    db = Logger(path=str(tmp_path / "t.db"))
    now = time.time()
    db.event_now(
        "food_photo",
        {"name": "Pizza", "risk": "HIGH", "gerd_score": 88},
    )
    db.event_now("symptom", {"severity": 2, "type": "Heartburn"})
    # backdate symptom to be 30 min after meal
    with db._lock:  # noqa: SLF001
        db._conn.execute(
            "UPDATE events SET ts=? WHERE kind='symptom'",
            (now + 30 * 60,),
        )
        db._conn.execute(
            "UPDATE events SET ts=? WHERE kind='food_photo'",
            (now,),
        )
    links = analytics.meal_symptom_correlation(db, days=1)
    assert len(links) >= 1
    assert links[0]["food"] == "Pizza"
    db.close()

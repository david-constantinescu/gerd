"""Sleep tracker — position classification + nudge ladder.

Position is derived from roll angle, adjusted for which hip the device is
clipped to (left / right / center). The nudge ladder is capped at 3 events
per night to avoid being its own sleep disruptor.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from ..config import TUNABLES
from ..events import Event, EventBus, EventType

log = logging.getLogger("services.sleep")

POSITIONS = ("left", "right", "back", "front")


def classify_position(roll_deg: float, wear_side: str) -> str:
    """Pure function — easy to unit-test."""
    # Normalise so the user lying on their left side always reads as "left"
    # regardless of which hip the device is clipped to.
    if wear_side == "right":
        roll_deg = -roll_deg
    if -30 <= roll_deg <= 30:
        return "back"
    if 30 < roll_deg <= 150:
        return "left"
    if -150 <= roll_deg < -30:
        return "right"
    return "front"


@dataclass
class _NightState:
    started_at: float = 0.0
    samples: dict[str, int] = field(default_factory=lambda: {p: 0 for p in POSITIONS})
    nudges: int = 0
    last_nudge: float = 0.0
    current_position: str = "back"


class SleepTracker:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.night = _NightState()

    def begin_night(self) -> None:
        self.night = _NightState(started_at=time.time())
        log.info("sleep night begin")

    def sample(self, roll_deg: float) -> None:
        if self.night.started_at == 0.0:
            self.begin_night()
        pos = classify_position(roll_deg, TUNABLES.wear_side)
        self.night.samples[pos] += 1
        self.night.current_position = pos
        if pos != "left":
            self._maybe_nudge(pos)

    def _maybe_nudge(self, pos: str) -> None:
        now = time.time()
        if self.night.nudges >= TUNABLES.sleep_max_nudges:
            return
        if now - self.night.last_nudge < TUNABLES.sleep_nudge_gap_seconds:
            return
        self.night.nudges += 1
        self.night.last_nudge = now
        log.info("sleep nudge %d (position=%s)", self.night.nudges, pos)
        self.bus.publish(
            Event(
                EventType.NUDGE_SENT,
                payload={"position": pos, "count": self.night.nudges},
            )
        )

    def end_night(self) -> dict:
        if self.night.started_at == 0.0:
            return {}
        total = sum(self.night.samples.values()) or 1
        pcts = {f"{k}_pct": v / total * 100 for k, v in self.night.samples.items()}
        score = int(pcts.get("left_pct", 0))
        report = {
            "night_of": datetime.fromtimestamp(self.night.started_at).date().isoformat(),
            "duration_s": int(time.time() - self.night.started_at),
            **pcts,
            "score": score,
            "nudges": self.night.nudges,
        }
        self.bus.publish(Event(EventType.SLEEP_MORNING_REPORT, payload=report))
        self.night = _NightState()
        return report

    def night_score(self) -> int:
        total = sum(self.night.samples.values()) or 1
        return int(self.night.samples.get("left", 0) / total * 100)

    def to_ctx(self) -> dict:
        n = self.night
        elapsed = int(time.time() - n.started_at) if n.started_at else 0
        hrs = elapsed // 3600
        mins = (elapsed % 3600) // 60
        total = sum(n.samples.values()) or 1
        left_pct = int(n.samples.get("left", 0) / total * 100)
        right_pct = int(n.samples.get("right", 0) / total * 100)
        back_pct = int(n.samples.get("back", 0) / total * 100)
        front_pct = int(n.samples.get("front", 0) / total * 100)
        gap_left = 0
        if n.last_nudge > 0:
            gap_left = max(
                0,
                int(TUNABLES.sleep_nudge_gap_seconds - (time.time() - n.last_nudge)),
            )
        return {
            "sleep_elapsed": f"{hrs}h {mins:02d}m" if hrs else f"{mins}m",
            "sleep_nudges": n.nudges,
            "sleep_nudges_max": TUNABLES.sleep_max_nudges,
            "sleep_left_pct": left_pct,
            "sleep_right_pct": right_pct,
            "sleep_back_pct": back_pct,
            "sleep_front_pct": front_pct,
            "sleep_score": self.night_score(),
            "sleep_wear_side": TUNABLES.wear_side,
            "sleep_nudge_cooldown_s": gap_left,
            "sleep_window": f"{TUNABLES.sleep_window_start}-{TUNABLES.sleep_window_end}",
        }

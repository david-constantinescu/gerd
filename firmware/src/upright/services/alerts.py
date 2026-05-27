"""Alert manager — cooldowns, escalation ladder, lying-down grace period.

Three escalation levels:
  level 1  → gentle haptic
  level 2  → moderate haptic
  level 3  → strong haptic + voice

The same posture violation moves up one level for every full
``alert_cooldown_seconds`` it remains unresolved. Voice alerts respect the
``voice_alerts_enabled`` tunable; sleep mode forces voice off entirely.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ..config import TUNABLES
from ..events import Event, EventBus, EventType
from ..hal.audio import Audio
from ..hal.motor import Motor

log = logging.getLogger("services.alerts")


@dataclass
class _AlertState:
    last_fired: float = 0.0
    level: int = 0
    first_seen: float = 0.0


class AlertManager:
    def __init__(
        self,
        bus: EventBus,
        *,
        motor: Motor | None = None,
        audio: Audio | None = None,
    ) -> None:
        self.bus = bus
        self.motor = motor or Motor(dry_run=False)
        self.audio = audio or Audio(dry_run=False)
        self._states: dict[str, _AlertState] = {}

    def reset(self, kind: str) -> None:
        self._states.pop(kind, None)

    def fire(
        self,
        kind: str,
        *,
        voice_clip: str | None = None,
        sleep_mode: bool = False,
    ) -> bool:
        """Fire an alert if cooldown allows. Returns True if it fired."""
        now = time.time()
        s = self._states.setdefault(kind, _AlertState(first_seen=now))
        if now - s.last_fired < TUNABLES.alert_cooldown_seconds and s.last_fired > 0:
            return False

        s.level = min(3, s.level + 1)
        s.last_fired = now

        if TUNABLES.haptic_alerts_enabled:
            pattern = {1: "gentle", 2: "moderate", 3: "strong"}[s.level]
            self.motor.buzz_async(pattern)

        if (
            s.level >= 3
            and not sleep_mode
            and TUNABLES.voice_alerts_enabled
            and voice_clip
        ):
            self.audio.play_async(voice_clip)

        log.info("alert fired: %s lvl=%d", kind, s.level)
        self.bus.publish(
            Event(EventType.ALERT_FIRED, payload={"kind": kind, "level": s.level})
        )
        return True

    def lying_down_grace(self, kind: str = "lying_post_meal") -> tuple[bool, float]:
        """Returns (escalate_now, seconds_into_grace)."""
        now = time.time()
        s = self._states.setdefault(kind, _AlertState(first_seen=now))
        elapsed = now - s.first_seen
        return (elapsed >= TUNABLES.lying_grace_seconds, elapsed)

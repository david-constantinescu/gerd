"""Event bus + event types.

The whole firmware is wired together as a single in-process event bus
(``queue.Queue``). HAL drivers and services produce ``Event`` objects; the
``ModeManager`` consumes them in its main loop and drives state transitions.

This decouples HAL polling from FSM logic and lets unit tests publish
synthetic events without touching real hardware.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    # HAL → bus
    POSTURE_SAMPLE = "posture_sample"
    HRV_SAMPLE = "hrv_sample"
    POWER_SAMPLE = "power_sample"
    BUTTON_PRESS = "button_press"  # payload: pattern (single|double|triple)
    ENCODER_ROTATE = "encoder_rotate"  # payload: direction (cw|ccw)
    ENCODER_CLICK = "encoder_click"
    CAMERA_FRAME = "camera_frame"

    # FSM → services
    STATE_CHANGED = "state_changed"
    ALERT_FIRED = "alert_fired"
    NUDGE_SENT = "nudge_sent"

    # User actions (from device or webapp)
    MEAL_LOGGED = "meal_logged"
    SYMPTOM_LOGGED = "symptom_logged"
    WATER_LOGGED = "water_logged"
    FOOD_PHOTO_REQUEST = "food_photo_request"
    FOOD_RESULT = "food_result"
    MED_REMINDER = "med_reminder"
    MED_ACKNOWLEDGED = "med_acknowledged"

    # Sleep
    SLEEP_POSITION = "sleep_position"
    SLEEP_MORNING_REPORT = "sleep_morning_report"

    # Lifecycle
    CONFIG_RELOADED = "config_reloaded"
    SHUTDOWN = "shutdown"


@dataclass
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Thread-safe event bus. Producers ``publish``; the FSM ``get``s."""

    def __init__(self, maxsize: int = 1024) -> None:
        self._q: queue.Queue[Event] = queue.Queue(maxsize=maxsize)

    def publish(self, event: Event) -> None:
        try:
            self._q.put_nowait(event)
        except queue.Full:
            # Never drop button events; shed sensor samples instead.
            if event.type == EventType.BUTTON_PRESS:
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    pass
                self._q.put_nowait(event)
                return
            dropped = 0
            while dropped < 32:
                try:
                    old = self._q.get_nowait()
                except queue.Empty:
                    break
                dropped += 1
                if old.type == EventType.BUTTON_PRESS:
                    try:
                        self._q.put_nowait(old)
                    except queue.Full:
                        pass
                    break
            try:
                self._q.put_nowait(event)
            except queue.Full:
                pass

    def get(self, timeout: float | None = None) -> Event | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def __len__(self) -> int:
        return self._q.qsize()

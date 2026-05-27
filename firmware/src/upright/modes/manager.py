"""Mode manager — the central FSM.

Consumes events from the bus, dispatches to state handlers, renders the OLED,
drives alerts and logging. Runs in the main thread.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from ..config import DISPLAY_MIN_REFRESH_SECONDS, TUNABLES
from ..events import Event, EventBus, EventType
from ..hal import imu
from ..hal.display import Display
from ..services.alerts import AlertManager
from ..services.logger import Logger
from ..services.meds import MedReminders
from ..services.sleep import SleepTracker
from . import ui
from .states import State, can_transition

log = logging.getLogger("modes.manager")


@dataclass
class Context:
    state: State = State.BOOTING
    pitch: float = 0.0
    roll: float = 0.0
    bpm: float | None = None
    rmssd: float | None = None
    battery_pct: int = 100
    battery_low: bool = False
    posture_pct: float = 100.0
    slouch_started_at: float = 0.0
    alert_level: int = 0
    alert_active: bool = False
    meal_started_at: float = 0.0
    meal_window_s: float = 0.0
    food_result: dict = field(default_factory=dict)
    still_since: float = 0.0
    calibration_step: int = 0
    calibration_baseline_pitch: float = 0.0


class ModeManager:
    def __init__(
        self,
        bus: EventBus,
        db: Logger,
        *,
        alerts: AlertManager,
        sleep: SleepTracker,
        meds: MedReminders,
        display: Display | None = None,
    ) -> None:
        self.bus = bus
        self.db = db
        self.alerts = alerts
        self.sleep = sleep
        self.meds = meds
        self.oled = display or Display(dry_run=False, autoprobe=False)
        self.ctx = Context()
        self._last_render = 0.0
        self._last_sched_tick = 0.0
        self._last_view_sig: tuple | None = None
        self._display_demo = os.environ.get("UPRIGHT_DISPLAY_DEMO", "").lower() in (
            "1",
            "true",
            "yes",
        )

    # -------------------------------------------------- transitions

    def _transition(self, dst: State) -> None:
        post_meal_active = self.ctx.meal_started_at > 0 and (
            time.time() - self.ctx.meal_started_at < self.ctx.meal_window_s
        )
        if not can_transition(self.ctx.state, dst, post_meal_active=post_meal_active):
            log.debug("illegal transition %s → %s (post_meal=%s)",
                      self.ctx.state, dst, post_meal_active)
            return
        log.info("state: %s → %s", self.ctx.state.value, dst.value)
        self.ctx.state = dst
        self.db.event("state_changed", {"to": dst.value})
        self.bus.publish(Event(EventType.STATE_CHANGED, payload={"state": dst.value}))
        # adjust IMU sample rate
        if dst == State.POST_MEAL:
            imu.set_rate(TUNABLES.posture_sample_hz_post_meal)
        elif dst == State.SLEEPING:
            imu.set_rate(TUNABLES.posture_sample_hz_sleep)
        else:
            imu.set_rate(TUNABLES.posture_sample_hz_idle)

    # -------------------------------------------------- handlers

    def _handle_posture(self, ev: Event) -> None:
        self.ctx.pitch = ev.payload["pitch"] - self.ctx.calibration_baseline_pitch
        self.ctx.roll = ev.payload["roll"]

        threshold = (
            TUNABLES.pitch_alert_strict_deg
            if self.ctx.state == State.POST_MEAL
            else TUNABLES.pitch_alert_deg
        )

        if self.ctx.state == State.SLEEPING:
            self.sleep.sample(self.ctx.roll)
            return

        # Posture percent: linear fall-off past threshold.
        deviation = max(0.0, abs(self.ctx.pitch) - threshold / 2)
        self.ctx.posture_pct = max(0.0, 100.0 - deviation * 3.0)

        if abs(self.ctx.pitch) > threshold:
            if self.ctx.slouch_started_at == 0.0:
                self.ctx.slouch_started_at = time.time()
            elif time.time() - self.ctx.slouch_started_at > TUNABLES.pitch_sustained_seconds:
                self.ctx.alert_active = True
                fired = self.alerts.fire(
                    "slouch",
                    voice_clip="alert_slouch",
                    sleep_mode=False,
                )
                if fired:
                    self.ctx.alert_level = self.alerts._states["slouch"].level
                    self.db.event("alert", {"kind": "slouch", "level": self.ctx.alert_level})
        else:
            self.ctx.slouch_started_at = 0.0
            self.ctx.alert_active = False
            self.ctx.alert_level = 0
            self.alerts.reset("slouch")

        # still-since for sleep onset detection
        if abs(self.ctx.pitch) < 3.0:
            if self.ctx.still_since == 0.0:
                self.ctx.still_since = time.time()
        else:
            self.ctx.still_since = 0.0

        self.db.posture(self.ctx.pitch, self.ctx.roll, self.ctx.state.value)

    def _handle_hrv(self, ev: Event) -> None:
        self.ctx.bpm = ev.payload.get("bpm")
        self.ctx.rmssd = ev.payload.get("rmssd")

    def _handle_power(self, ev: Event) -> None:
        pct = ev.payload.get("battery_pct")
        if pct is not None:
            self.ctx.battery_pct = int(pct)
        self.ctx.battery_low = bool(ev.payload.get("battery_low", False))

    def _handle_button(self, ev: Event) -> None:
        pattern = ev.payload.get("pattern", "")
        btn = ev.payload.get("button", "?")
        log.info("button %s: %s", btn, pattern)
        if pattern == "long":
            self._log_meal()
        elif pattern == "verylong":
            self._transition(State.CALIBRATING)
        elif pattern == "single":
            self.db.event("symptom", {"severity": 1})
            if self.ctx.state in (State.IDLE, State.POST_MEAL):
                self._transition(State.FOOD_PHOTO)
                self._run_food_photo()
        elif pattern == "double":
            self.db.event("symptom", {"severity": 2})
        elif pattern == "triple":
            self.db.event("symptom", {"severity": 3})

    def _log_meal(self, notes: str = "") -> None:
        self.ctx.meal_started_at = time.time()
        self.ctx.meal_window_s = TUNABLES.post_meal_default_hours * 3600
        self.db.event("meal", {"notes": notes, "window_s": self.ctx.meal_window_s})
        self.bus.publish(Event(EventType.MEAL_LOGGED, payload={"notes": notes}))
        self._transition(State.POST_MEAL)

    def _run_food_photo(self) -> None:
        from ..hal.camera import capture_with_warmup
        from ..services import foods

        img = capture_with_warmup()
        result = foods.classify(img) if img is not None else None
        if result is None:
            self.ctx.food_result = {
                "name": "unknown",
                "risk": "?",
                "advice": "enter manually",
            }
        else:
            name, risk, conf = result
            advice = {
                "LOW": "Good choice",
                "MEDIUM": "Be careful",
                "HIGH": "Stay upright 3h",
            }.get(risk, "")
            self.ctx.food_result = {"name": name, "risk": risk, "advice": advice}
            self.db.event(
                "food_photo",
                {"name": name, "risk": risk, "confidence": conf},
            )
            self.bus.publish(
                Event(
                    EventType.FOOD_RESULT,
                    payload={"name": name, "risk": risk, "confidence": conf},
                )
            )

    def _handle_inbox(self) -> None:
        """Process requests queued by the Flask webapp."""
        for msg in self.db.consume_inbox():
            kind = msg["kind"]
            payload = msg["payload"]
            if kind == "meal":
                self._log_meal(notes=payload.get("notes", ""))
            elif kind == "symptom":
                self.db.event("symptom", payload)
            elif kind == "water":
                self.db.event("water", payload)
            elif kind == "med_ack":
                self.meds.acknowledge(payload.get("name", ""))
            elif kind == "calibrate":
                self._transition(State.CALIBRATING)
            elif kind == "config_reloaded":
                self.bus.publish(Event(EventType.CONFIG_RELOADED))

    # -------------------------------------------------- sleep entry

    def _maybe_enter_sleep(self) -> None:
        if self.ctx.state != State.IDLE:
            return
        now = datetime.now().time()
        start = datetime.strptime(TUNABLES.sleep_window_start, "%H:%M").time()
        end = datetime.strptime(TUNABLES.sleep_window_end, "%H:%M").time()
        in_window = (start <= now) or (now <= end) if start > end else (start <= now <= end)
        if not in_window:
            return
        if self.ctx.still_since == 0.0:
            return
        stillness = time.time() - self.ctx.still_since
        if stillness > TUNABLES.sleep_pre_stillness_minutes * 60:
            self._transition(State.SLEEPING)
            self.sleep.begin_night()

    def _maybe_exit_post_meal(self) -> None:
        if self.ctx.state != State.POST_MEAL:
            return
        if time.time() - self.ctx.meal_started_at > self.ctx.meal_window_s:
            self.ctx.meal_started_at = 0.0
            self._transition(State.IDLE)

    # -------------------------------------------------- ctx → view

    def _view_signature(self, state: State, ctx: dict) -> tuple:
        """Stable key for deciding whether the TFT needs a new frame."""
        return (
            state.value,
            datetime.now().strftime("%H:%M"),
            ctx.get("battery_text"),
            int(ctx.get("posture_pct", 0) // 10) * 10,  # 10% buckets
            int(round(ctx.get("pitch", 0) / 5.0) * 5),  # 5° buckets
            ctx.get("alert_active"),
            ctx.get("level"),
            ctx.get("meal_age_bucket"),
            int(ctx.get("progress", 0.0) * 10),  # 10% buckets
            ctx.get("name"),
            ctx.get("risk"),
        )

    def _view_ctx(self) -> dict:
        meal = self.db.last_meal()
        last_meal_text = "—"
        meal_age_bucket = -1
        if meal:
            dt = datetime.fromtimestamp(meal["ts"])
            ago = datetime.now() - dt
            mins = int(ago.total_seconds() // 60)
            meal_age_bucket = mins // 15  # signature updates every 15 min
            if mins < 60:
                last_meal_text = f"{meal_age_bucket * 15}m ago"
            else:
                last_meal_text = f"{mins // 60}h ago"
        remaining = ""
        progress = 0.0
        if self.ctx.meal_started_at:
            elapsed = time.time() - self.ctx.meal_started_at
            left = max(0.0, self.ctx.meal_window_s - elapsed)
            remaining = f"{int(left // 3600)}h {int((left % 3600) // 60):02d}m"
            progress = elapsed / self.ctx.meal_window_s if self.ctx.meal_window_s else 0.0
        return {
            "display_demo": self._display_demo,
            "bpm": f"{int(self.ctx.bpm)}" if self.ctx.bpm else "--",
            "battery_pct": self.ctx.battery_pct,
            "battery_low": self.ctx.battery_low,
            "battery_text": "LOW" if self.ctx.battery_low else f"{self.ctx.battery_pct}%",
            "posture_pct": float(int(self.ctx.posture_pct // 2) * 2),
            "pitch": round(self.ctx.pitch, 0),
            "alert_active": self.ctx.alert_active,
            "level": self.ctx.alert_level,
            "last_meal_text": last_meal_text,
            "meal_age_bucket": meal_age_bucket,
            "remaining": remaining,
            "progress": progress,
            "meal_at_text": (
                datetime.fromtimestamp(self.ctx.meal_started_at).strftime("%H:%M")
                if self.ctx.meal_started_at
                else "—"
            ),
            "position": self.sleep.night.current_position,
            "score": 0,
            **self.ctx.food_result,
            "step": ["Stand upright", "Lean forward", "Lie on left"][
                min(2, self.ctx.calibration_step)
            ],
        }

    # -------------------------------------------------- main loop

    def run(self, stop: threading.Event) -> None:
        self._transition(State.IDLE)
        if self._display_demo:
            log.info("display demo mode enabled — holding SYSTEM OK screen")
        # Paint once immediately so the panel is not blank after boot.
        try:
            boot_state = State.IDLE if self._display_demo else self.ctx.state
            boot_view = self._view_ctx()
            ui.render(boot_state, boot_view, self.oled)
            self._last_view_sig = self._view_signature(boot_state, boot_view)
            self._last_render = time.time()
        except Exception as e:  # pragma: no cover
            log.warning("initial render failed: %s", e)
        while not stop.is_set():
            ev = self.bus.get(timeout=0.2)
            if ev is not None:
                if ev.type == EventType.POSTURE_SAMPLE:
                    self._handle_posture(ev)
                elif ev.type == EventType.HRV_SAMPLE:
                    self._handle_hrv(ev)
                elif ev.type == EventType.POWER_SAMPLE:
                    self._handle_power(ev)
                elif ev.type == EventType.BUTTON_PRESS:
                    self._handle_button(ev)
                elif ev.type == EventType.SHUTDOWN:
                    break

            now = time.time()

            # housekeeping (~once per second)
            if now - self._last_sched_tick > 1.0:
                self._last_sched_tick = now
                self._handle_inbox()
                self.meds.tick()
                self._maybe_exit_post_meal()
                self._maybe_enter_sleep()

            # Full-frame SPI refresh only when content meaningfully changes, and
            # at most once per DISPLAY_MIN_REFRESH_SECONDS (clock via minute in sig).
            state = State.IDLE if self._display_demo else self.ctx.state
            view = self._view_ctx()
            sig = self._view_signature(state, view)
            changed = sig != self._last_view_sig
            urgent = False
            if changed and self._last_view_sig is not None:
                prev = self._last_view_sig
                urgent = prev[0] != sig[0] or prev[5] != sig[5]  # FSM state or slouch alert
            interval_ok = now - self._last_render >= DISPLAY_MIN_REFRESH_SECONDS
            if changed and (interval_ok or urgent):
                self._last_render = now
                self._last_view_sig = sig
                try:
                    ui.render(state, view, self.oled)
                except Exception as e:  # pragma: no cover
                    log.warning("render failed: %s", e)

        self.sleep.end_night()
        self.db.flush()

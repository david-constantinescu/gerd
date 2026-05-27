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

from ..config import (
    DISPLAY_MIN_REFRESH_SECONDS,
    DISPLAY_PITCH_REFRESH_SECONDS,
    TUNABLES,
)
from ..events import Event, EventBus, EventType
from ..hal import imu
from ..hal.display import Display
from ..services.alerts import AlertManager
from ..services.logger import Logger
from ..services.meds import MedReminders
from ..services.sleep import SleepTracker
from .. import __version__
from . import ui
from .menu import SYMPTOM_SEVERITIES, SYMPTOM_TYPES, MenuState
from .states import State, can_transition

log = logging.getLogger("modes.manager")

# Screens where bottom tap does nothing (busy or passive).
_NO_SELECT_SCREENS = frozenset({"food_analysing", "food_preview", "flash"})
# Screens where any bottom tap dismisses.
_DISMISS_SCREENS = frozenset({"meal_saved", "symptom_saved", "med_ack", "about"})


@dataclass
class Context:
    state: State = State.BOOTING
    pitch: float = 0.0
    roll: float = 0.0
    bpm: float | None = None
    rmssd: float | None = None
    battery_pct: int = 100
    battery_low: bool = False
    battery_source: str = "unknown"
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
        self.menu = MenuState()
        self._symptom_severity_label = "1 - Mild"
        self._symptom_type_label = "Heartburn"
        self._last_render = 0.0
        self._last_sched_tick = 0.0
        self._last_view_sig: tuple | None = None
        self._last_pitch_render = 0.0
        self._food_preview = None
        self._pitch_display: float | None = None
        self._battery_low_since = 0.0
        self._lying_since: float = 0.0
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
        raw_pitch = ev.payload["pitch"] - self.ctx.calibration_baseline_pitch
        alpha = max(0.05, min(1.0, TUNABLES.pitch_display_alpha))
        if self._pitch_display is None:
            self._pitch_display = raw_pitch
        else:
            self._pitch_display = alpha * raw_pitch + (1.0 - alpha) * self._pitch_display
        self.ctx.pitch = self._pitch_display
        self.ctx.roll = ev.payload["roll"]

        threshold = (
            TUNABLES.pitch_alert_strict_deg
            if self.ctx.state == State.POST_MEAL
            else TUNABLES.pitch_alert_deg
        )

        if self.ctx.state == State.SLEEPING:
            self.sleep.sample(self.ctx.roll)
            return

        lying = abs(self.ctx.pitch) >= TUNABLES.lying_flat_deg
        if lying:
            if self._lying_since == 0.0:
                self._lying_since = time.time()
        else:
            self._lying_since = 0.0
            self.alerts.reset("lying_post_meal")

        # Posture score: 100% at upright, falls off after dead zone + half threshold.
        adjusted = max(0.0, abs(self.ctx.pitch) - TUNABLES.posture_deadzone_deg)
        deviation = max(0.0, adjusted - threshold / 2)
        self.ctx.posture_pct = max(
            0.0, 100.0 - deviation * TUNABLES.posture_pct_slope
        )

        violation = adjusted > threshold
        sustained_limit = TUNABLES.pitch_sustained_seconds
        if self.ctx.state == State.POST_MEAL and lying:
            violation = True
            escalate_now, _ = self.alerts.lying_down_grace("lying_post_meal")
            if not escalate_now:
                violation = False
            sustained_limit = TUNABLES.lying_sustained_seconds

        if violation:
            if self.ctx.slouch_started_at == 0.0:
                self.ctx.slouch_started_at = time.time()
            elif time.time() - self.ctx.slouch_started_at > sustained_limit:
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
        was_low = self.ctx.battery_low
        pct = ev.payload.get("battery_pct")
        if pct is not None:
            self.ctx.battery_pct = int(pct)
        self.ctx.battery_low = bool(ev.payload.get("battery_low", False))
        self.ctx.battery_source = str(ev.payload.get("battery_source", "unknown"))
        now = time.time()
        if self.ctx.battery_low:
            if not was_low:
                self._battery_low_since = now
                log.warning("battery low — haptic warning")
                if TUNABLES.haptic_alerts_enabled:
                    self.alerts.motor.buzz_async("max")
                self._paint_now()
            elif (
                was_low
                and self._battery_low_since > 0
                and now - self._battery_low_since >= 10.0
                and now - self._battery_low_since < 11.0
            ):
                self._paint_now()
        else:
            self._battery_low_since = 0.0
        if self.ctx.battery_low != was_low and not self.ctx.battery_low:
            self._paint_now()

    def _handle_button(self, ev: Event) -> None:
        pattern = ev.payload.get("pattern", "")
        btn = ev.payload.get("button", "?")
        log.info("button %s: %s", btn, pattern)
        now = time.time()
        self.menu.touch(now)
        if btn == "a":
            if pattern == "double":
                self._on_a_double(now)
            elif pattern == "single":
                self._on_a_short(now)
        elif btn == "b":
            if pattern == "double":
                self._on_b_double(now)
            elif pattern in ("single", "triple"):
                self._on_b_short(now)
        self._paint_now()

    def _on_a_short(self, now: float) -> None:
        if self.menu.open and self.menu.screen != "flash":
            self.menu.next_item()
            return
        if self.ctx.state == State.CALIBRATING:
            self._transition(State.IDLE)

    def _on_a_double(self, now: float) -> None:
        if self.menu.open:
            if self.menu.screen == "main":
                self.menu.close()
            else:
                self._menu_back()
            return
        if self.ctx.state == State.CALIBRATING:
            self._transition(State.IDLE)
            self.menu.close()

    def _on_b_short(self, now: float) -> None:
        if not self.menu.open:
            return
        self._menu_select(now)

    def _on_b_double(self, now: float) -> None:
        if self.ctx.state == State.CALIBRATING:
            self.ctx.calibration_step = min(2, self.ctx.calibration_step + 1)
            if self.ctx.calibration_step >= 2:
                self.ctx.calibration_baseline_pitch = self.ctx.pitch
                self._transition(State.IDLE)
                self.menu.close()
            return
        if self.menu.screen == "flash":
            self.menu.close()
            return
        if not self.menu.open:
            if self.ctx.state in (State.IDLE, State.POST_MEAL):
                self.menu.open_main(now)
            return
        if self.menu.screen == "food_photo":
            self._capture_food(now)
            return
        self._menu_select(now)

    def _menu_select(self, now: float) -> None:
        """Bottom tap — confirm highlighted row (single or double)."""
        if self.menu.screen in _NO_SELECT_SCREENS:
            return
        if self.menu.screen in _DISMISS_SCREENS:
            self.menu.close()
            return
        action = self.menu.current_action()
        if action:
            self._menu_action(action, now)

    def _menu_back(self) -> None:
        parent = {
            "meal_confirm": "main",
            "food_photo": "meal_confirm",
            "food_preview": "food_photo",
            "food_result": "food_photo",
            "symptom_severity": "main",
            "symptom_type": "symptom_severity",
            "symptom_saved": "main",
            "meal_saved": "main",
            "med_prompt": "main",
            "med_ack": "main",
            "med_info": "main",
            "settings": "main",
            "about": "main",
            "food_analysing": "food_photo",
        }
        if self.menu.screen == "main":
            self.menu.close()
            return
        nxt = parent.get(self.menu.screen, "main")
        self.menu.screen = nxt
        self.menu.index = 0
        if nxt == "main":
            self.menu.open = True

    def _menu_action(self, action: str, now: float) -> None:
        """Confirm the highlighted menu choice."""
        if action == "meal":
            self.menu.screen = "meal_confirm"
            self.menu.index = 0
        elif action == "symptom":
            self.menu.screen = "symptom_severity"
            self.menu.index = 0
        elif action == "med":
            self.menu.screen = "med_info"
            self.menu.index = 0
        elif action == "settings":
            self.menu.screen = "settings"
            self.menu.index = 0
        elif action == "sleep":
            self.menu.close()
            self.sleep.begin_night()
            self._transition(State.PRE_SLEEP)
        elif action == "about":
            self.menu.screen = "about"
            self.menu.index = 0
        elif action == "about_done":
            self.menu.close()
        elif action == "med_done":
            self._menu_back()
        elif action == "calibrate":
            self.menu.close()
            self.ctx.calibration_step = 0
            self._transition(State.CALIBRATING)
        elif action == "meal_yes":
            self._log_meal()
            self.menu.screen = "food_photo"
            self.menu.index = 0
        elif action == "meal_no":
            self.menu.close()
        elif action.startswith("symptom_type_"):
            idx = int(action.rsplit("_", 1)[-1])
            self._save_symptom(self.menu.symptom_severity + 1, idx, now)
        elif action.startswith("symptom_"):
            sev = int(action.split("_")[1])
            self.menu.symptom_severity = sev - 1
            self.menu.screen = "symptom_type"
            self.menu.index = 0
        elif action == "med_ack":
            name = self.menu.pending_med
            if name:
                self.meds.acknowledge(name)
            self.menu.screen = "med_ack"
            self.menu.flash_until = now + 2.0
        elif action == "food_capture":
            self._capture_food(now)
        elif action == "food_skip":
            self.menu.screen = "meal_saved"
            self.menu.flash_until = now + 2.5
        elif action == "food_confirm":
            hours = float(self.ctx.food_result.get("upright_hours", 0) or 0)
            if hours > 0 and self.ctx.meal_started_at:
                self.ctx.meal_window_s = hours * 3600.0
            self.menu.close()
            if self.ctx.state == State.FOOD_PHOTO:
                self._transition(State.POST_MEAL if self.ctx.meal_started_at else State.IDLE)
        elif action == "food_retry":
            self.menu.screen = "food_photo"
            self.menu.index = 0

    def _save_symptom(self, severity: int, type_idx: int, now: float) -> None:
        self._symptom_severity_label = SYMPTOM_SEVERITIES[severity - 1]
        self._symptom_type_label = SYMPTOM_TYPES[type_idx]
        self.db.event(
            "symptom",
            {
                "severity": severity,
                "type": self._symptom_type_label,
            },
        )
        self.bus.publish(
            Event(
                EventType.SYMPTOM_LOGGED,
                payload={"severity": severity, "type": self._symptom_type_label},
            )
        )
        self.menu.screen = "symptom_saved"
        self.menu.flash_until = now + 2.5

    def _capture_food(self, now: float) -> None:
        from ..hal.camera import capture_with_warmup

        self._transition(State.FOOD_PHOTO)
        self.menu.screen = "food_analysing"
        self._paint_now()
        img = capture_with_warmup()
        if img is not None:
            self._food_preview = img.copy()
            self.menu.screen = "food_preview"
            self._paint_now()
            time.sleep(1.0)
        self._food_preview = None
        self.menu.screen = "food_analysing"
        self._paint_now()
        self._run_food_photo(img)
        self.menu.open = True
        self.menu.screen = "food_result"
        self.menu.index = 0
        self.menu.touch(now)

    def _handle_med_reminder(self, ev: Event) -> None:
        name = ev.payload.get("name", "Medication")
        self.menu.open = True
        self.menu.screen = "med_prompt"
        self.menu.pending_med = name
        self.menu.pending_med_time = datetime.now().strftime("%H:%M")
        self.menu.index = 0
        self.menu.touch(time.time())
        self._paint_now()

    def _log_meal(self, notes: str = "") -> None:
        self.ctx.meal_started_at = time.time()
        self.ctx.meal_window_s = TUNABLES.post_meal_default_hours * 3600
        self.db.event("meal", {"notes": notes, "window_s": self.ctx.meal_window_s})
        self.bus.publish(Event(EventType.MEAL_LOGGED, payload={"notes": notes}))
        self._transition(State.POST_MEAL)

    def _run_food_photo(self, img=None) -> None:
        from ..hal.camera import capture_with_warmup
        from ..services import foods

        if img is None:
            img = capture_with_warmup()
        result = foods.classify(img) if img is not None else None
        if result is None:
            self.ctx.food_result = {
                "name": "unknown",
                "risk": "?",
                "gerd_score": 0,
                "upright_hours": TUNABLES.post_meal_default_hours,
                "advice": "Not recognized — use phone log",
            }
        else:
            self.ctx.food_result = {
                "name": result.name,
                "risk": result.risk,
                "gerd_score": result.gerd_score,
                "upright_hours": result.upright_hours,
                "advice": result.advice,
                "confidence": result.confidence,
            }
            self.ctx.meal_window_s = result.upright_hours * 3600.0
            self.db.event(
                "food_photo",
                {
                    "name": result.name,
                    "risk": result.risk,
                    "gerd_score": result.gerd_score,
                    "upright_hours": result.upright_hours,
                    "confidence": result.confidence,
                    "label": result.label,
                },
            )
            self.bus.publish(
                Event(
                    EventType.FOOD_RESULT,
                    payload={
                        "name": result.name,
                        "risk": result.risk,
                        "gerd_score": result.gerd_score,
                        "confidence": result.confidence,
                    },
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
        base = (
            state.value,
            datetime.now().strftime("%H:%M"),
            int(ctx.get("battery_pct", 100) // 5) * 5,
            bool(ctx.get("battery_low")),
            int(float(ctx.get("battery_low_age_s", 0)) // 2),
            bool(ctx.get("battery_powered")),
            bool(ctx.get("battery_ok_green")),
            int(ctx.get("posture_pct", 0) // 10) * 10,
            int(round(float(ctx.get("pitch", 0)) * 2) / 2),
            ctx.get("alert_active"),
            ctx.get("level"),
            ctx.get("meal_age_bucket"),
            int(ctx.get("progress", 0.0) * 10),
            ctx.get("name"),
            ctx.get("risk"),
        )
        if ctx.get("menu_open"):
            return base + (
                ctx.get("menu_screen"),
                ctx.get("menu_index"),
                ctx.get("menu_flash"),
            )
        return base

    def _view_ctx(self) -> dict:
        meal = self.db.last_meal()
        last_meal_text = "—"
        meal_age_bucket = -1
        last_food = self.db.last_food_photo()
        last_food_name = "—"
        last_food_risk = ""
        last_food_score = 0
        food_upright_hours = 0.0
        if last_food:
            last_food_name = str(last_food.get("name", "—"))[:16]
            last_food_risk = str(last_food.get("risk", ""))
            last_food_score = int(last_food.get("gerd_score", 0) or 0)
            food_upright_hours = float(last_food.get("upright_hours", 0) or 0)
        last_symptom = self.db.last_symptom()
        last_symptom_text = ""
        if last_symptom:
            typ = str(last_symptom.get("type", ""))[:12]
            sev = last_symptom.get("severity", "")
            last_symptom_text = f"{typ} sev{sev}" if typ else ""
        med_line = self.meds.status_line()
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
        low_age = (
            time.time() - self._battery_low_since
            if self.ctx.battery_low and self._battery_low_since > 0
            else 0.0
        )
        ok_green = not self.ctx.battery_low and (
            self.ctx.battery_source == "alert_pin"
            or self.ctx.battery_pct >= 50
        )
        return {
            "display_demo": self._display_demo,
            "bpm": f"{int(self.ctx.bpm)}" if self.ctx.bpm else "--",
            "battery_pct": self.ctx.battery_pct,
            "battery_low": self.ctx.battery_low,
            "battery_source": self.ctx.battery_source,
            "battery_powered": self.ctx.battery_source == "alert_pin"
            and not self.ctx.battery_low,
            "battery_ok_green": ok_green,
            "battery_low_age_s": low_age,
            "battery_text": "LOW" if self.ctx.battery_low else f"{self.ctx.battery_pct}%",
            "posture_pct": float(int(self.ctx.posture_pct // 2) * 2),
            "pitch": round(self.ctx.pitch, 1),
            "roll": round(self.ctx.roll, 1),
            "alert_active": self.ctx.alert_active,
            "level": self.ctx.alert_level,
            "last_meal_text": last_meal_text,
            "last_food_name": last_food_name,
            "last_food_risk": last_food_risk,
            "last_food_score": last_food_score,
            "rmssd_text": (
                f"{int(self.ctx.rmssd)}"
                if self.ctx.rmssd is not None
                else "--"
            ),
            "date_text": datetime.now().strftime("%a %d %b"),
            "wear_side": TUNABLES.wear_side,
            "med_line": med_line,
            "last_symptom_text": last_symptom_text,
            "food_upright_hours": food_upright_hours,
            "hotspot_ssid": TUNABLES.hotspot_ssid,
            "hotspot_ip": TUNABLES.hotspot_ip,
            "meal_age_bucket": meal_age_bucket,
            "remaining": remaining,
            "progress": progress,
            "meal_at_text": (
                datetime.fromtimestamp(self.ctx.meal_started_at).strftime("%H:%M")
                if self.ctx.meal_started_at
                else "—"
            ),
            "position": self.sleep.night.current_position,
            **self.sleep.to_ctx(),
            "score": self.sleep.night_score(),
            **self.ctx.food_result,
            "step": ["Stand upright", "Lean forward", "Lie on left"][
                min(2, self.ctx.calibration_step)
            ],
            "version": __version__,
            "symptom_severity_label": self._symptom_severity_label,
            "symptom_type_label": self._symptom_type_label,
            "meal_window_text": (
                f"{int(TUNABLES.post_meal_default_hours)}h "
                f"{int((TUNABLES.post_meal_default_hours % 1) * 60):02d}m"
            ),
            "analyse_progress": 0.65,
            "food_preview_image": self._food_preview,
            **self.menu.to_ctx(),
        }

    def _paint_now(self) -> None:
        state = State.IDLE if self._display_demo else self.ctx.state
        view = self._view_ctx()
        try:
            ui.render(state, view, self.oled)
            self._last_render = time.time()
            self._last_view_sig = self._view_signature(state, view)
        except Exception as e:  # pragma: no cover
            log.warning("render failed: %s", e)

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
                elif ev.type == EventType.MED_REMINDER:
                    self._handle_med_reminder(ev)
                elif ev.type == EventType.NUDGE_SENT:
                    if TUNABLES.haptic_alerts_enabled:
                        self.alerts.motor.buzz_async("max")
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
                if self.menu.idle_expired(now):
                    self.menu.close()
                if self.menu.screen == "flash" and now > self.menu.flash_until:
                    self.menu.close()
                elif self.menu.screen in ("symptom_saved", "meal_saved", "med_ack"):
                    if now > self.menu.flash_until:
                        self.menu.close()

            # Full-frame SPI refresh only when content meaningfully changes, and
            # at most once per DISPLAY_MIN_REFRESH_SECONDS (clock via minute in sig).
            state = State.IDLE if self._display_demo else self.ctx.state
            view = self._view_ctx()
            sig = self._view_signature(state, view)
            changed = sig != self._last_view_sig
            urgent = False
            if changed and self._last_view_sig is not None:
                prev = self._last_view_sig
                urgent = prev[0] != sig[0] or prev[5] != sig[5]
                if len(prev) > 2 and len(sig) > 2 and prev[2] != sig[2]:
                    urgent = True
                pitch_due = now - self._last_pitch_render >= DISPLAY_PITCH_REFRESH_SECONDS
                if len(prev) > 4 and len(sig) > 4 and prev[4] != sig[4] and pitch_due:
                    urgent = True
                    self._last_pitch_render = now
            interval_ok = (
                self.menu.open
                or now - self._last_render >= DISPLAY_MIN_REFRESH_SECONDS
            )
            if changed and (interval_ok or urgent):
                self._last_render = now
                self._last_view_sig = sig
                try:
                    ui.render(state, view, self.oled)
                except Exception as e:  # pragma: no cover
                    log.warning("render failed: %s", e)

        self.sleep.end_night()
        self.db.flush()

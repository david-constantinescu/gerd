"""Two-button menu navigation — see reference docs/oled-mockups.md."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import TUNABLES

MAIN_ITEMS: list[tuple[str, str]] = [
    ("Log Meal", "meal"),
    ("Log Symptom", "symptom"),
    ("Medication", "med"),
    ("Settings", "settings"),
    ("Sleep Mode", "sleep"),
    ("About", "about"),
]

def settings_items() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = [
        ("Calibrate posture", "calibrate"),
        ("Week stats", "stats"),
        ("Network", "network"),
    ]
    if TUNABLES.demo_mode:
        items.append(("Exit demo mode", "demo_exit"))
    else:
        items.append(("Demo mode", "demo_enter"))
    return items


# Back-compat for imports/tests that expect a static list
SETTINGS_ITEMS: list[tuple[str, str]] = settings_items()

SYMPTOM_SEVERITIES: list[str] = [
    "1 - Mild",
    "2 - Moderate",
    "3 - Severe",
]

SYMPTOM_TYPES: list[str] = [
    "Heartburn",
    "Regurgitation",
    "Bloating",
    "Chest pain",
    "Other",
]

MENU_IDLE_SECONDS = 30.0


@dataclass
class MenuState:
    open: bool = False
    screen: str = "main"
    index: int = 0
    confirm_yes: bool = True
    food_skip: bool = False
    symptom_severity: int = 0
    symptom_type: int = 0
    pending_med: str = ""
    pending_med_brand: str = ""
    pending_med_dose: str = ""
    pending_med_time: str = ""
    flash_until: float = 0.0
    flash_message: str = ""
    last_input: float = field(default_factory=lambda: 0.0)

    def touch(self, now: float) -> None:
        self.last_input = now

    def idle_expired(self, now: float) -> bool:
        if not self.open:
            return False
        return now - self.last_input > MENU_IDLE_SECONDS

    def reset(self) -> None:
        self.open = False
        self.screen = "main"
        self.index = 0
        self.confirm_yes = True
        self.food_skip = False
        self.symptom_severity = 0
        self.symptom_type = 0
        self.pending_med = ""
        self.pending_med_brand = ""
        self.pending_med_dose = ""
        self.pending_med_time = ""

    def open_main(self, now: float) -> None:
        self.open = True
        self.screen = "main"
        self.index = 0
        self.touch(now)

    def close(self) -> None:
        self.reset()

    def _list_len(self) -> int:
        if self.screen == "main":
            return len(MAIN_ITEMS)
        if self.screen == "symptom_severity":
            return len(SYMPTOM_SEVERITIES)
        if self.screen == "symptom_type":
            return len(SYMPTOM_TYPES)
        if self.screen == "meal_confirm":
            return 2
        if self.screen == "food_photo":
            return 2
        if self.screen == "food_result":
            return 2
        if self.screen == "settings":
            return len(settings_items())
        if self.screen in ("about", "med_info", "stats", "network"):
            return 1
        return 1

    def next_item(self) -> None:
        n = self._list_len()
        if n > 1:
            self.index = (self.index + 1) % n

    def prev_item(self) -> None:
        n = self._list_len()
        if n > 1:
            self.index = (self.index - 1) % n

    def flash(self, message: str, now: float, seconds: float = 2.5) -> None:
        self.flash_message = message
        self.flash_until = now + seconds
        self.screen = "flash"

    def current_action(self) -> str | None:
        if self.screen == "main":
            return MAIN_ITEMS[self.index][1]
        if self.screen == "meal_confirm":
            return "meal_yes" if self.index == 0 else "meal_no"
        if self.screen == "symptom_severity":
            return f"symptom_{self.index + 1}"
        if self.screen == "symptom_type":
            return f"symptom_type_{self.index}"
        if self.screen == "food_photo":
            return "food_capture" if self.index == 0 else "food_skip"
        if self.screen == "food_result":
            return "food_confirm" if self.index == 0 else "food_retry"
        if self.screen == "med_prompt" and self.pending_med:
            return "med_ack"
        if self.screen == "settings":
            return settings_items()[self.index][1]
        if self.screen == "stats":
            return "stats_done"
        if self.screen == "network":
            return "network_done"
        if self.screen == "med_info":
            return "med_done"
        if self.screen == "about":
            return "about_done"
        return None

    def to_ctx(self) -> dict:
        return {
            "menu_open": self.open,
            "menu_screen": self.screen,
            "menu_index": self.index,
            "menu_confirm_yes": self.confirm_yes,
            "menu_pending_med": self.pending_med,
            "menu_pending_med_brand": self.pending_med_brand,
            "menu_pending_med_dose": self.pending_med_dose,
            "menu_pending_med_time": self.pending_med_time,
            "menu_flash": self.flash_message if self.screen == "flash" else "",
            "menu_symptom_severity": self.symptom_severity,
            "menu_symptom_type": self.symptom_type,
        }

"""On-device menu navigation (OLED menu PDF).

Encoder click opens the main menu from the watch face; encoder rotation scrolls;
button A goes back; button B confirms the highlighted item when a menu is open.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAIN_ITEMS: list[tuple[str, str]] = [
    ("Log Meal", "meal"),
    ("Log Symptom", "symptom"),
    ("Medication", "med"),
    ("Settings", "settings"),
    ("About", "about"),
]


@dataclass
class MenuState:
    open: bool = False
    screen: str = "main"  # main | meal_confirm | symptom | med | settings | about
    index: int = 0
    confirm_yes: bool = True
    symptom_severity: int = 1  # 1=mild, 2=moderate, 3=severe
    pending_med: str = ""

    def reset(self) -> None:
        self.open = False
        self.screen = "main"
        self.index = 0
        self.confirm_yes = True
        self.symptom_severity = 1

    def open_main(self) -> None:
        self.open = True
        self.screen = "main"
        self.index = 0

    def scroll(self, direction: str) -> None:
        delta = 1 if direction == "cw" else -1
        if self.screen == "main":
            self.index = (self.index + delta) % len(MAIN_ITEMS)
        elif self.screen == "meal_confirm":
            self.confirm_yes = not self.confirm_yes
        elif self.screen == "symptom":
            self.symptom_severity = ((self.symptom_severity - 1 + delta) % 3) + 1
        elif self.screen in ("med", "settings", "about"):
            pass

    def current_action(self) -> str | None:
        if self.screen == "main":
            return MAIN_ITEMS[self.index][1]
        if self.screen == "meal_confirm":
            return "meal_yes" if self.confirm_yes else "meal_no"
        if self.screen == "symptom":
            return f"symptom_{self.symptom_severity}"
        if self.screen == "med" and self.pending_med:
            return "med_ack"
        return None

    def to_ctx(self) -> dict:
        return {
            "menu_open": self.open,
            "menu_screen": self.screen,
            "menu_index": self.index,
            "menu_confirm_yes": self.confirm_yes,
            "menu_symptom_severity": self.symptom_severity,
            "menu_pending_med": self.pending_med,
        }

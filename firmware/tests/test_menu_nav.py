"""Two-button menu navigation (no encoder)."""

import time

from upright.modes.menu import MAIN_ITEMS, MenuState


def test_main_menu_scroll_wraps() -> None:
    m = MenuState()
    m.open_main(0.0)
    assert m.screen == "main"
    start = m.index
    for _ in range(len(MAIN_ITEMS)):
        m.next_item()
    assert m.index == start


def test_meal_confirm_action() -> None:
    m = MenuState()
    m.open = True
    m.screen = "meal_confirm"
    m.index = 0
    assert m.current_action() == "meal_yes"
    m.index = 1
    assert m.current_action() == "meal_no"


def test_idle_timeout() -> None:
    m = MenuState()
    m.open_main(100.0)
    assert not m.idle_expired(120.0)
    assert m.idle_expired(131.0)

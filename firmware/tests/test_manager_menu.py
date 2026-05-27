"""Menu selection flows — every branch reachable via bottom tap."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from upright.events import EventBus
from upright.modes.manager import ModeManager
from upright.modes.menu import MAIN_ITEMS, SETTINGS_ITEMS, MenuState
from upright.modes.states import State
from upright.services.alerts import AlertManager
from upright.services.logger import Logger
from upright.services.meds import MedReminders
from upright.services.sleep import SleepTracker


@pytest.fixture
def mgr(tmp_path):
    bus = EventBus()
    db = Logger(path=str(tmp_path / "menu.db"))
    db.boot_session()
    alerts = AlertManager(bus)
    sleep = SleepTracker(bus)
    meds = MedReminders(bus, db)
    display = MagicMock()
    display.width = 160
    display.height = 128
    m = ModeManager(bus, db, alerts=alerts, sleep=sleep, meds=meds, display=display)
    m._transition(State.IDLE)
    return m


def _open_main(mgr: ModeManager) -> None:
    mgr.menu.open_main(time.time())


def _select(mgr: ModeManager) -> None:
    mgr._menu_select(time.time())


def test_main_menu_every_item_opens_branch(mgr: ModeManager) -> None:
    _open_main(mgr)
    for i, (_label, action) in enumerate(MAIN_ITEMS):
        mgr.menu.index = i
        _select(mgr)
        if action == "meal":
            assert mgr.menu.screen == "meal_confirm"
        elif action == "symptom":
            assert mgr.menu.screen == "symptom_severity"
        elif action == "med":
            assert mgr.menu.screen == "med_info"
        elif action == "settings":
            assert mgr.menu.screen == "settings"
        elif action == "sleep":
            assert mgr.ctx.state == State.PRE_SLEEP
            assert not mgr.menu.open
            mgr._transition(State.IDLE)
            mgr.menu.open = False
            _open_main(mgr)
            continue
        elif action == "about":
            assert mgr.menu.screen == "about"
        mgr._menu_back()
        assert mgr.menu.screen == "main"
        mgr.menu.index = i


def test_meal_flow_yes_and_no(mgr: ModeManager) -> None:
    _open_main(mgr)
    mgr.menu.index = 0
    _select(mgr)
    assert mgr.menu.screen == "meal_confirm"
    mgr.menu.index = 1
    _select(mgr)
    assert not mgr.menu.open

    _open_main(mgr)
    mgr.menu.index = 0
    _select(mgr)
    mgr.menu.index = 0
    _select(mgr)
    assert mgr.menu.screen == "food_photo"
    assert mgr.ctx.state == State.POST_MEAL


def test_symptom_flow(mgr: ModeManager) -> None:
    _open_main(mgr)
    mgr.menu.index = 1
    _select(mgr)
    assert mgr.menu.screen == "symptom_severity"
    mgr.menu.index = 0
    _select(mgr)
    assert mgr.menu.screen == "symptom_type"
    mgr.menu.index = 0
    _select(mgr)
    assert mgr.menu.screen == "symptom_saved"


def test_settings_calibrate(mgr: ModeManager) -> None:
    _open_main(mgr)
    mgr.menu.index = 3
    _select(mgr)
    assert mgr.menu.screen == "settings"
    mgr.menu.index = 0
    _select(mgr)
    assert mgr.ctx.state == State.CALIBRATING
    assert not mgr.menu.open


def test_med_info_done(mgr: ModeManager) -> None:
    _open_main(mgr)
    mgr.menu.index = 2
    _select(mgr)
    assert mgr.menu.screen == "med_info"
    _select(mgr)
    assert mgr.menu.screen == "main"


def test_food_result_confirm_and_retry(mgr: ModeManager) -> None:
    mgr.menu.open = True
    mgr.menu.screen = "food_result"
    mgr.menu.index = 1
    _select(mgr)
    assert mgr.menu.screen == "food_photo"
    mgr.menu.screen = "food_result"
    mgr.menu.index = 0
    mgr.ctx.state = State.FOOD_PHOTO
    mgr.ctx.meal_started_at = time.time()
    _select(mgr)
    assert not mgr.menu.open
    assert mgr.ctx.state == State.POST_MEAL


def test_med_prompt_ack(mgr: ModeManager) -> None:
    mgr.menu.open = True
    mgr.menu.screen = "med_prompt"
    mgr.menu.pending_med = "Omeprazole"
    mgr.menu.index = 0
    _select(mgr)
    assert mgr.menu.screen == "med_ack"


def test_menu_state_actions_match_screens() -> None:
    m = MenuState()
    m.open_main(0.0)
    for i in range(len(MAIN_ITEMS)):
        m.index = i
        assert m.current_action() == MAIN_ITEMS[i][1]
    m.screen = "settings"
    m.index = 0
    assert m.current_action() == SETTINGS_ITEMS[0][1]

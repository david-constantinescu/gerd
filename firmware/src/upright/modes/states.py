"""FSM states + transition guards.

8 states, modelled after the OLED menu PDF and the project description.
``can_transition`` is the single source of truth for legal transitions and is
unit-tested without any hardware.
"""

from __future__ import annotations

from enum import Enum


class State(str, Enum):
    BOOTING = "booting"
    ONBOARDING = "onboarding"
    IDLE = "idle"
    POST_MEAL = "post_meal"
    FOOD_PHOTO = "food_photo"
    PRE_SLEEP = "pre_sleep"
    SLEEPING = "sleeping"
    CALIBRATING = "calibrating"


# (from, to) pairs that are *always* legal. Most other transitions go through
# can_transition() which adds runtime guards (POST_MEAL countdown active,
# sleep window time check, etc).
_BASE_EDGES: set[tuple[State, State]] = {
    (State.BOOTING, State.ONBOARDING),
    (State.BOOTING, State.IDLE),
    (State.ONBOARDING, State.IDLE),
    (State.IDLE, State.POST_MEAL),
    (State.IDLE, State.FOOD_PHOTO),
    (State.IDLE, State.PRE_SLEEP),
    (State.IDLE, State.CALIBRATING),
    (State.POST_MEAL, State.IDLE),
    (State.POST_MEAL, State.FOOD_PHOTO),
    (State.FOOD_PHOTO, State.IDLE),
    (State.FOOD_PHOTO, State.POST_MEAL),
    (State.PRE_SLEEP, State.SLEEPING),
    (State.PRE_SLEEP, State.IDLE),
    (State.SLEEPING, State.IDLE),
    (State.CALIBRATING, State.IDLE),
}


def can_transition(
    src: State,
    dst: State,
    *,
    post_meal_active: bool = False,
) -> bool:
    """Pure transition guard. ``post_meal_active`` is the only runtime input
    that materially blocks transitions (POST_MEAL must NOT be interrupted by
    sleep)."""
    if src == dst:
        return True
    if (src, dst) not in _BASE_EDGES:
        return False
    if dst in (State.PRE_SLEEP, State.SLEEPING) and post_meal_active:
        return False
    return True

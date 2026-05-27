from upright.modes.states import State, can_transition


def test_idle_can_go_to_post_meal():
    assert can_transition(State.IDLE, State.POST_MEAL)


def test_post_meal_blocks_sleep():
    assert not can_transition(State.IDLE, State.PRE_SLEEP, post_meal_active=True)
    assert not can_transition(State.IDLE, State.SLEEPING, post_meal_active=True)


def test_pre_sleep_to_sleeping_ok():
    assert can_transition(State.PRE_SLEEP, State.SLEEPING)


def test_calibrating_must_return_to_idle():
    assert can_transition(State.CALIBRATING, State.IDLE)
    assert not can_transition(State.CALIBRATING, State.POST_MEAL)


def test_food_photo_reachable_from_idle_or_post_meal():
    assert can_transition(State.IDLE, State.FOOD_PHOTO)
    assert can_transition(State.POST_MEAL, State.FOOD_PHOTO)
    assert not can_transition(State.SLEEPING, State.FOOD_PHOTO)


def test_identity_transition_allowed():
    assert can_transition(State.IDLE, State.IDLE)

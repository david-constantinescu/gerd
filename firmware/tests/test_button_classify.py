from upright.hal.button import classify, ready_to_emit


def test_single_press():
    assert classify([0.0]) == "single"


def test_double_press():
    assert classify([0.0, 0.1]) == "double"


def test_double_press_quick_zap_zap():
    assert classify([0.0, 0.22]) == "double"


def test_triple_press_counts_as_double():
    assert classify([0.0, 0.1, 0.2]) == "double"


def test_ready_to_emit_waits_for_second_tap():
    assert not ready_to_emit([0.0], 0.35, gap=0.4, window=0.6, pressed_at=None)
    assert ready_to_emit([0.0], 0.65, gap=0.4, window=0.6, pressed_at=None)


def test_ready_to_emit_double_after_gap():
    assert not ready_to_emit([0.0, 0.35], 0.50, gap=0.4, window=0.6, pressed_at=None)
    assert ready_to_emit([0.0, 0.35], 0.80, gap=0.4, window=0.6, pressed_at=None)

from upright.hal.button import classify


def test_single_press():
    assert classify([0.0], hold_duration=0.1) == "single"


def test_double_press():
    assert classify([0.0, 0.1], hold_duration=0.1) == "double"


def test_triple_press():
    assert classify([0.0, 0.1, 0.2], hold_duration=0.1) == "triple"


def test_long_press():
    assert classify([], hold_duration=2.0) == "long"


def test_very_long_press():
    assert classify([], hold_duration=3.5) == "verylong"

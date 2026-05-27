from upright.hal.button import classify, classify_hold


def test_single_press():
    assert classify([0.0], hold_duration=0.1, long_threshold=1.8) == "single"


def test_double_press():
    assert classify([0.0, 0.1], hold_duration=0.1, long_threshold=1.8) == "double"


def test_triple_press():
    assert classify([0.0, 0.1, 0.2], hold_duration=0.1, long_threshold=1.8) == "triple"


def test_long_press():
    assert classify([], hold_duration=1.85, long_threshold=1.8) == "long"


def test_bottom_long_threshold_higher():
    assert classify([], hold_duration=2.0, long_threshold=2.35) == "single"
    assert classify([], hold_duration=2.4, long_threshold=2.35) == "long"


def test_very_long_press():
    assert classify([], hold_duration=3.6, long_threshold=1.8) == "verylong"
    assert classify_hold(3.6, long_threshold=2.35) == "verylong"

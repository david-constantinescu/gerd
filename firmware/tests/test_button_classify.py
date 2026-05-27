from upright.hal.button import classify


def test_single_press():
    assert classify([0.0]) == "single"


def test_double_press():
    assert classify([0.0, 0.1]) == "double"


def test_double_press_quick_zap_zap():
    assert classify([0.0, 0.22]) == "double"


def test_triple_press():
    assert classify([0.0, 0.1, 0.2]) == "triple"

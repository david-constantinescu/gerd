from sentinel.services.sleep import classify_position


def test_left_side_on_left_wear():
    assert classify_position(90.0, "left") == "left"


def test_right_side_on_left_wear():
    assert classify_position(-90.0, "left") == "right"


def test_on_back():
    assert classify_position(0.0, "left") == "back"


def test_wear_side_flip():
    # When clipped on the right hip, lying on the user's left should still
    # read as "left" (device flips internally).
    assert classify_position(-90.0, "right") == "left"

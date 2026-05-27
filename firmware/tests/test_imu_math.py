import math

from upright.hal.imu import angles_from_accel


def test_upright_is_zero_pitch():
    pitch, roll = angles_from_accel(0.0, 0.0, 1.0)
    assert abs(pitch) < 1e-6
    assert abs(roll) < 1e-6


def test_forward_lean_positive_pitch():
    pitch, _ = angles_from_accel(0.5, 0.0, 0.866)
    assert pitch > 20


def test_left_tilt_positive_roll():
    _, roll = angles_from_accel(0.0, 0.5, 0.866)
    assert roll > 20


def test_flat_on_back_is_90_pitch():
    pitch, _ = angles_from_accel(1.0, 0.0, 0.0)
    assert math.isclose(pitch, 90.0, abs_tol=0.1)

from upright.hal.power import lipo_pct_from_voltage_mv, sample_battery


def test_lipo_voltage_mapping():
    assert lipo_pct_from_voltage_mv(4200) == 100
    assert lipo_pct_from_voltage_mv(4000) == 80
    assert lipo_pct_from_voltage_mv(3700) == 30
    assert lipo_pct_from_voltage_mv(3300) == 0


def test_sample_battery_stub_path(monkeypatch):
    monkeypatch.setattr("upright.hal.power._read_max17043", lambda: None)
    monkeypatch.setattr("upright.hal.power._read_ina219_mv", lambda: None)
    monkeypatch.setattr("upright.hal.power.read_active_low", lambda _pin: False)
    pct, low, source = sample_battery()
    assert pct == 100
    assert low is False
    assert source == "alert_pin"

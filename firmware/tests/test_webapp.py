import pytest

from upright import config
from upright.services.logger import Logger
from upright.web.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point DB + config at throwaway paths for this test run.
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "web.db")
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    Logger(path=str(tmp_path / "web.db")).close()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_dashboard_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"UpRight" in r.data


def test_live_endpoint(client):
    r = client.get("/api/live")
    assert r.status_code == 200
    body = r.get_json()
    assert "events" in body
    assert "now" in body


def test_log_meal_and_readback(client):
    r = client.post("/api/log/meal", json={"notes": "spaghetti"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_settings_roundtrip(client):
    r = client.post("/api/settings", json={"pitch_alert_deg": 12.0})
    assert r.get_json()["ok"] is True
    r = client.get("/api/settings")
    assert r.get_json()["pitch_alert_deg"] == 12.0

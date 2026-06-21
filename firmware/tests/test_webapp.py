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


def test_wifi_status_public(client):
    r = client.get("/api/wifi/status")
    assert r.status_code == 200
    body = r.get_json()
    assert "url" in body and "mdns" in body


def test_wifi_qr_png(client):
    r = client.get("/api/wifi/qr.png")
    assert r.status_code == 200
    assert r.mimetype == "image/png"
    assert r.data[:4] == b"\x89PNG"


def test_wifi_open_during_setup(client):
    # First-time setup (not yet connected to any network): scan/connect are open
    # so the user can provision Wi-Fi without an account.
    assert client.get("/api/wifi/scan").status_code == 200


def test_wifi_requires_login_when_connected(client, monkeypatch):
    # Once on a real network, changing Wi-Fi needs login.
    from upright.services import wifi as wifi_service

    monkeypatch.setattr(wifi_service, "is_client_connected", lambda: True)
    assert client.get("/api/wifi/scan").status_code == 401
    assert client.post("/api/wifi/connect", json={"ssid": "X"}).status_code == 401


def test_settings_page_has_network_not_hotspot(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert b"Network" in r.data
    assert b"Hotspot" not in r.data

"""Web control panel authentication."""

from __future__ import annotations

import pytest

from upright.web.app import app
from upright.web.auth import verify_credentials


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("upright.web.auth.SECRET_PATH", tmp_path / "secret.txt")
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    return app.test_client()


def test_verify_credentials_default():
    assert verify_credentials("softhoarders", "0031")
    assert not verify_credentials("softhoarders", "wrong")


def test_control_requires_login(client):
    r = client.get("/control")
    assert r.status_code == 302
    assert "/login" in r.location


def test_login_and_command(client):
    r = client.post(
        "/login",
        data={"username": "softhoarders", "password": "0031"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    r = client.post(
        "/api/device/command",
        json={"command": "water", "payload": {}},
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

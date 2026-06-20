"""Tests for the LAN-access stack: netinfo helpers, wifi (nmcli) wrapper, QR."""

from unittest.mock import patch

from upright.services import netinfo, wifi


def test_hostname_and_mdns():
    host = netinfo.hostname()
    assert host and "." not in host  # short name only
    assert netinfo.mdns_host() == f"{host}.local"


def test_dashboard_url_prefers_mdns():
    url = netinfo.dashboard_url(prefer_mdns=True)
    assert url == f"http://{netinfo.mdns_host()}/"


def test_lan_ip_returns_str_or_none():
    ip = netinfo.lan_ip()
    assert ip is None or (ip.count(".") == 3 and not ip.startswith("127."))


def test_status_shape():
    s = netinfo.status()
    assert set(s) == {"host", "mdns", "ip", "url"}


def test_qr_image_is_pil():
    img = netinfo.qr_image("http://upright.local/")
    assert img is not None
    assert img.size[0] > 0 and img.size[1] > 0  # a real raster


def test_qr_png_and_svg():
    assert netinfo.qr_png_bytes("x")[:8] == b"\x89PNG\r\n\x1a\n"
    assert "<svg" in (netinfo.qr_svg("x") or "")


def test_qr_degrades_without_segno():
    with patch.object(netinfo, "_qr", return_value=None):
        assert netinfo.qr_png_bytes("x") is None
        assert netinfo.qr_image("x") is None
        assert netinfo.qr_svg("x") is None


def test_wifi_graceful_without_nmcli():
    """Off the Pi (no nmcli) every call must degrade, never raise."""
    with patch.object(wifi, "is_available", return_value=False):
        assert wifi.current_ssid() is None
        assert wifi.scan() == []
        ok, msg = wifi.connect("Net", "pw")
        assert ok is False and "not available" in msg


def test_wifi_connect_requires_ssid():
    with patch.object(wifi, "is_available", return_value=True):
        ok, msg = wifi.connect("")
        assert ok is False and "SSID" in msg


def test_wifi_scan_parses_nmcli(monkeypatch):
    class FakeProc:
        returncode = 0
        stdout = "HomeNet:72:WPA2\nHomeNet:72:WPA2\nOpenCafe:40:\n"

    monkeypatch.setattr(wifi, "is_available", lambda: True)
    monkeypatch.setattr(wifi, "_run", lambda *a, **k: FakeProc())
    nets = wifi.scan()
    assert [n["ssid"] for n in nets] == ["HomeNet", "OpenCafe"]  # deduped, sorted
    assert nets[0]["secure"] is True
    assert nets[1]["secure"] is False

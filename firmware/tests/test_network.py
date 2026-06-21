"""Tests for the LAN-access stack: netinfo helpers, wifi (nmcli) wrapper, QR."""

from unittest.mock import patch

from upright.services import netinfo, provisioning, wifi


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


def test_wifi_ap_graceful_without_nmcli():
    with patch.object(wifi, "is_available", return_value=False):
        assert wifi.is_ap_active() is False
        assert wifi.is_client_connected() is False
        assert wifi.start_ap()[0] is False
        assert wifi.stop_ap()[0] is False


def test_start_ap_hardened_profile(monkeypatch):
    """The AP must free the radio and beacon with explicit WPA2/RSN + a channel."""
    calls = []

    class Ok:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, timeout):
        calls.append(args)
        return Ok()

    monkeypatch.setattr(wifi, "is_available", lambda: True)
    monkeypatch.setattr(wifi, "is_ap_active", lambda: False)
    monkeypatch.setattr(wifi, "_run", fake_run)
    ok, _ = wifi.start_ap()
    assert ok is True
    flat = [" ".join(c) for c in calls]
    assert any("device disconnect" in c for c in flat)  # freed the single radio
    assert any("connection delete" in c for c in flat)  # recreated cleanly
    add = next(c for c in calls if "add" in c)
    add_str = " ".join(add)
    for token in ("802-11-wireless.mode ap", "wifi-sec.proto rsn", "ccmp",
                  "802-11-wireless.channel", "ipv4.method shared"):
        assert token in add_str


def test_active_wifi_cons_distinguishes_ap(monkeypatch):
    class FakeProc:
        returncode = 0
        stdout = f"wifi:HomeNet\nethernet:Wired\nwifi:{wifi.SETUP_AP_CON}\n"

    monkeypatch.setattr(wifi, "is_available", lambda: True)
    monkeypatch.setattr(wifi, "_run", lambda *a, **k: FakeProc())
    assert wifi.is_ap_active() is True       # setup AP connection present
    assert wifi.is_client_connected() is True  # HomeNet is a non-AP wifi con


def test_wifi_qr_payload_format_and_escaping():
    p = provisioning.wifi_qr_payload("MyNet", "p;a:ss")
    assert p.startswith("WIFI:S:MyNet;T:WPA;P:")
    assert "p\\;a\\:ss" in p  # ';' and ':' escaped
    assert p.endswith(";;")
    # open network
    assert "T:nopass;" in provisioning.wifi_qr_payload("Open", "")


def test_provisioning_setup_url():
    assert provisioning.setup_url() == f"http://{wifi.SETUP_AP_GATEWAY}/"


def test_provisioning_tick_brings_ap_up_when_offline(monkeypatch):
    calls = []
    monkeypatch.setattr(wifi, "is_available", lambda: True)
    monkeypatch.setattr(wifi, "is_client_connected", lambda: False)
    monkeypatch.setattr(wifi, "is_ap_active", lambda: False)
    monkeypatch.setattr(wifi, "start_ap", lambda: (calls.append("up") or (True, "up")))
    provisioning._tick()
    assert calls == ["up"]


def test_provisioning_tick_drops_ap_when_connected(monkeypatch):
    calls = []
    monkeypatch.setattr(wifi, "is_available", lambda: True)
    monkeypatch.setattr(wifi, "is_client_connected", lambda: True)
    monkeypatch.setattr(wifi, "is_ap_active", lambda: True)
    monkeypatch.setattr(wifi, "stop_ap", lambda: (calls.append("down") or (True, "down")))
    provisioning._tick()
    assert calls == ["down"]


def test_provisioning_thread_noop_without_nmcli():
    with patch.object(wifi, "is_available", return_value=False):
        th = provisioning.start_thread(dry_run=False)
        assert th.is_alive()
        th.stop.set()

"""First-time Wi-Fi provisioning via a temporary setup access point.

When the device has no Wi-Fi connection, a background loop brings up a
short-lived setup AP (``wifi.SETUP_AP_*``). The user scans a standard Wi-Fi QR
on the OLED to join it from any phone (iOS + Android both support Wi-Fi QR
codes), opens the dashboard at the AP gateway, and picks their home network.
Once the device associates as a client, the AP is taken back down.

No hostapd/dnsmasq — NetworkManager provides the AP + DHCP in ``shared`` mode.
Everything degrades to a no-op where ``nmcli`` is absent (dev machine / sim).
"""

from __future__ import annotations

import logging
import threading

from . import wifi

log = logging.getLogger("services.provisioning")

# Give NetworkManager time to auto-connect to a known network at boot before we
# decide the device is "unprovisioned" and raise the setup AP. Kept short so the
# AP appears quickly when the saved network is out of range / wrong.
_BOOT_GRACE_S = 12.0
_CHECK_INTERVAL_S = 15.0

# Cheap, cached "are we hosting the setup AP right now?" flag, refreshed by the
# reconcile loop. The web captive-portal hook reads this on every request, so it
# must not shell out to nmcli each time.
_setup_mode = False


def is_setup_mode() -> bool:
    return _setup_mode


def setup_url() -> str:
    return f"http://{wifi.SETUP_AP_GATEWAY}/"


def _qr_escape(value: str) -> str:
    for ch in ("\\", ";", ",", '"', ":"):
        value = value.replace(ch, "\\" + ch)
    return value


def wifi_qr_payload(ssid: str | None = None, password: str | None = None) -> str:
    """A standard ``WIFI:`` QR string that phones recognise as "join network"."""
    ssid = ssid if ssid is not None else wifi.SETUP_AP_SSID
    password = password if password is not None else wifi.SETUP_AP_PASSWORD
    auth = "WPA" if password else "nopass"
    return f"WIFI:S:{_qr_escape(ssid)};T:{auth};P:{_qr_escape(password)};;"


def state() -> dict:
    """Snapshot for the OLED Network screen / web."""
    return {
        "connected": wifi.is_client_connected(),
        "ap_active": wifi.is_ap_active(),
        "setup_ssid": wifi.SETUP_AP_SSID,
        "setup_password": wifi.SETUP_AP_PASSWORD,
        "setup_url": setup_url(),
    }


def _tick() -> None:
    """One reconcile step: AP up iff there's no client connection."""
    global _setup_mode
    if not wifi.is_available():
        _setup_mode = False
        return
    if wifi.is_client_connected():
        if wifi.is_ap_active():
            wifi.stop_ap()
        _setup_mode = False
    elif not wifi.is_ap_active():
        ok, msg = wifi.start_ap()
        if not ok:
            log.warning("could not raise setup AP: %s", msg)
        _setup_mode = ok
    else:
        _setup_mode = True


def _loop(stop: threading.Event) -> None:
    stop.wait(_BOOT_GRACE_S)  # let NM autoconnect first
    while not stop.is_set():
        try:
            _tick()
        except Exception as e:  # pragma: no cover - runtime/nmcli specific
            log.warning("provisioning tick failed: %s", e)
        stop.wait(_CHECK_INTERVAL_S)


def start_thread(*, dry_run: bool = False) -> threading.Thread:
    """Start the AP-reconcile loop. No-op (idle thread) without nmcli / on dry-run."""
    stop = threading.Event()
    active = (not dry_run) and wifi.is_available()
    target = (lambda: _loop(stop)) if active else (lambda: stop.wait())
    th = threading.Thread(target=target, name="provisioning", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    if active:
        log.info("Wi-Fi provisioning watcher started")
    return th

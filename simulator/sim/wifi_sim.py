"""Simulated NetworkManager Wi-Fi for the Pi bench.

The real firmware talks to ``nmcli``; on a dev machine that binary is absent so
provisioning never runs and the Network screen always looks "offline". This
module patches :mod:`upright.services.wifi` with an in-memory state machine and
forces the provisioning watcher to start even under ``--dry-run``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import SimDevice

log = logging.getLogger("sim.wifi")

# Visible during setup-mode scan in the browser bench.
DEFAULT_SCAN = [
    {"ssid": "SimHome", "signal": 82, "secure": True},
    {"ssid": "SimGuest", "signal": 55, "secure": True},
    {"ssid": "SimOpen", "signal": 40, "secure": False},
]


def install(dev: SimDevice) -> None:
    """Replace ``wifi`` + ``netinfo.lan_ip`` with sim-backed implementations."""
    import upright.services.netinfo as netinfo
    import upright.services.provisioning as provisioning
    import upright.services.wifi as wifi

    dev.wifi_mode = "offline"  # offline | ap | client
    dev.wifi_client_ssid: str | None = None
    dev.wifi_client_ip = "192.168.1.42"
    dev.wifi_scan = list(DEFAULT_SCAN)

    _orig_lan_ip = netinfo.lan_ip
    _orig_start_thread = provisioning.start_thread

    def is_available() -> bool:
        return True

    def current_ssid() -> str | None:
        if dev.wifi_mode == "client":
            return dev.wifi_client_ssid
        return None

    def scan(*, timeout: float = 20.0) -> list[dict]:
        return list(dev.wifi_scan)

    def connect(ssid: str, password: str | None = None, *, timeout: float = 45.0) -> tuple[bool, str]:
        if not ssid:
            return False, "missing SSID"
        if dev.wifi_mode == "ap":
            stop_ap()
        dev.wifi_mode = "client"
        dev.wifi_client_ssid = ssid
        log.info("sim Wi-Fi connected to %r", ssid)
        return True, f"connected to {ssid}"

    def _active_wifi_cons() -> list[str]:
        if dev.wifi_mode == "ap":
            return [wifi.SETUP_AP_CON]
        if dev.wifi_mode == "client" and dev.wifi_client_ssid:
            return [dev.wifi_client_ssid]
        return []

    def _device_state() -> str:
        if dev.wifi_mode == "client":
            return "connected"
        if dev.wifi_mode == "ap":
            return "connected"
        return "disconnected"

    def wlan_ipv4() -> str | None:
        if dev.wifi_mode == "client":
            return dev.wifi_client_ip
        if dev.wifi_mode == "ap":
            return wifi.SETUP_AP_GATEWAY
        return None

    def is_ap_active() -> bool:
        return dev.wifi_mode == "ap"

    def is_client_connected() -> bool:
        return dev.wifi_mode == "client" and bool(dev.wifi_client_ssid)

    def has_usable_client() -> bool:
        return dev.wifi_mode == "client" and bool(dev.wifi_client_ssid)

    def start_ap() -> tuple[bool, str]:
        if dev.wifi_mode == "ap":
            return True, "setup AP already up"
        dev.wifi_mode = "ap"
        dev.wifi_client_ssid = None
        log.info("sim setup AP up")
        return True, "setup AP up"

    def stop_ap() -> tuple[bool, str]:
        if dev.wifi_mode != "ap":
            return True, "setup AP down"
        dev.wifi_mode = "offline"
        log.info("sim setup AP down")
        return True, "setup AP down"

    def sim_lan_ip() -> str | None:
        if dev.wifi_mode == "client":
            return dev.wifi_client_ip
        if dev.wifi_mode == "ap":
            return wifi.SETUP_AP_GATEWAY
        return _orig_lan_ip()

    def start_thread(*, dry_run: bool = False):
        # Provisioning must run in the simulator even though main() uses dry_run.
        return _orig_start_thread(dry_run=False)

    wifi.is_available = is_available
    wifi.current_ssid = current_ssid
    wifi.scan = scan
    wifi.connect = connect
    wifi._active_wifi_cons = _active_wifi_cons
    wifi._device_state = _device_state
    wifi.wlan_ipv4 = wlan_ipv4
    wifi.is_ap_active = is_ap_active
    wifi.is_client_connected = is_client_connected
    wifi.has_usable_client = has_usable_client
    wifi.start_ap = start_ap
    wifi.stop_ap = stop_ap
    netinfo.lan_ip = sim_lan_ip
    provisioning.start_thread = start_thread

    log.info("sim Wi-Fi backend installed")

"""Wi-Fi management via NetworkManager (``nmcli``).

Raspberry Pi OS Bookworm manages networking with NetworkManager, so adding or
switching networks is just an ``nmcli`` call. Off the Pi (dev machine, the
simulator) ``nmcli`` is absent and every function degrades gracefully so the
firmware and web app keep running.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger("services.wifi")

# Temporary "setup" access point, brought up only while the device has no Wi-Fi
# (see services.provisioning). NetworkManager handles DHCP in `shared` mode and
# hands out the gateway below — no hostapd/dnsmasq needed.
WIFI_IFACE = "wlan0"
SETUP_AP_SSID = "UpRight-Setup"
SETUP_AP_PASSWORD = "uprightsetup"  # >= 8 chars (WPA2); shown in the on-screen QR
SETUP_AP_CON = "upright-setup"  # NetworkManager connection name
SETUP_AP_GATEWAY = "10.42.0.1"  # NM `shared` mode default


def is_available() -> bool:
    return shutil.which("nmcli") is not None


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["nmcli", *args], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("nmcli %s failed: %s", " ".join(args), e)
        return None


def current_ssid() -> str | None:
    """SSID of the active Wi-Fi connection, or ``None``."""
    if not is_available():
        return None
    proc = _run(["-t", "-f", "active,ssid", "dev", "wifi"], timeout=8)
    if proc is None or proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        # Format: "yes:MyNetwork" / "no:Other" — ':' inside SSIDs is escaped \:
        if line.startswith("yes:"):
            return line[4:].replace("\\:", ":") or None
    return None


def scan(*, timeout: float = 20.0) -> list[dict]:
    """Visible networks, strongest first: ``[{ssid, signal, secure}]``."""
    if not is_available():
        return []
    _run(["dev", "wifi", "rescan"], timeout=timeout)  # best-effort refresh
    proc = _run(["-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"], timeout=timeout)
    if proc is None or proc.returncode != 0:
        return []
    seen: set[str] = set()
    nets: list[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        ssid = parts[0].replace("\\:", ":").strip()
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        try:
            signal = int(parts[1])
        except ValueError:
            signal = 0
        security = parts[2].strip()
        nets.append(
            {"ssid": ssid, "signal": signal, "secure": bool(security and security != "--")}
        )
    nets.sort(key=lambda n: n["signal"], reverse=True)
    return nets


def connect(ssid: str, password: str | None = None, *, timeout: float = 45.0) -> tuple[bool, str]:
    """Join (and persist) a Wi-Fi network. Returns ``(ok, message)``.

    On the Pi Zero 2 W there is a single radio, so the setup AP (if up) must be
    torn down before associating as a client. The caller's HTTP response may not
    reach a phone that was on the setup AP — that's expected; the device joins
    the network and the OLED then shows the dashboard QR.
    """
    if not is_available():
        return False, "NetworkManager (nmcli) is not available on this host"
    if not ssid:
        return False, "missing SSID"
    if is_ap_active():
        stop_ap()
    args = ["dev", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    proc = _run(args, timeout=timeout)
    if proc is None:
        return False, "could not run nmcli"
    if proc.returncode == 0:
        log.info("connected to Wi-Fi %r", ssid)
        return True, proc.stdout.strip() or f"connected to {ssid}"
    return False, proc.stderr.strip() or proc.stdout.strip() or "connection failed"


# --------------------------------------------------------------- setup-AP / state
def _active_wifi_cons() -> list[str]:
    """Names of currently-active Wi-Fi connections."""
    proc = _run(["-t", "-f", "TYPE,NAME", "connection", "show", "--active"], timeout=8)
    if proc is None or proc.returncode != 0:
        return []
    names: list[str] = []
    for line in proc.stdout.splitlines():
        typ, _, name = line.partition(":")
        if "wireless" in typ or typ == "wifi":
            names.append(name.replace("\\:", ":"))
    return names


def is_ap_active() -> bool:
    """True when our temporary setup AP is up."""
    if not is_available():
        return False
    return SETUP_AP_CON in _active_wifi_cons()


def is_client_connected() -> bool:
    """True when associated to a real Wi-Fi network (not our setup AP)."""
    if not is_available():
        return False
    return any(n != SETUP_AP_CON for n in _active_wifi_cons())


def start_ap() -> tuple[bool, str]:
    """Bring up the temporary setup AP (idempotent)."""
    if not is_available():
        return False, "nmcli unavailable"
    if is_ap_active():
        return True, "setup AP already up"
    existing = _run(["-t", "-f", "NAME", "connection", "show"], timeout=8)
    known = existing.stdout.splitlines() if existing else []
    if SETUP_AP_CON not in known:
        add = _run(
            [
                "connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
                "con-name", SETUP_AP_CON, "autoconnect", "no", "ssid", SETUP_AP_SSID,
                "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                "ipv4.method", "shared",
                "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", SETUP_AP_PASSWORD,
            ],
            timeout=20,
        )
        if add is None or add.returncode != 0:
            return False, (add.stderr.strip() if add else "could not create AP profile")
    up = _run(["connection", "up", SETUP_AP_CON], timeout=30)
    if up is not None and up.returncode == 0:
        log.info("setup AP %r up at %s", SETUP_AP_SSID, SETUP_AP_GATEWAY)
        return True, "setup AP up"
    return False, (up.stderr.strip() if up else "could not start setup AP")


def stop_ap() -> tuple[bool, str]:
    """Take the setup AP down (idempotent)."""
    if not is_available():
        return False, "nmcli unavailable"
    proc = _run(["connection", "down", SETUP_AP_CON], timeout=15)
    if proc is not None and proc.returncode == 0:
        log.info("setup AP down")
        return True, "setup AP down"
    return False, (proc.stderr.strip() if proc else "could not stop setup AP")

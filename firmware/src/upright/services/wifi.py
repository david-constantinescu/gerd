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
SETUP_AP_PASSWORD = "softhoarders"  # >= 8 chars (WPA2); shown in the on-screen QR
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
        # Re-enable autoconnect on the profile we just joined.
        _run(["connection", "modify", ssid, "connection.autoconnect", "yes"], timeout=5)
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


def _wireless_connection_names() -> list[str]:
    """All saved Wi-Fi connection profile names."""
    proc = _run(["-t", "-f", "NAME,TYPE", "connection", "show"], timeout=10)
    if proc is None or proc.returncode != 0:
        return []
    names: list[str] = []
    for line in proc.stdout.splitlines():
        name, _, typ = line.partition(":")
        typ = typ.replace("\\:", ":")
        name = name.replace("\\:", ":")
        if "wireless" in typ or typ == "802-11-wireless":
            names.append(name)
    return names


def _device_state() -> str:
    """``wlan0`` link state from NetworkManager (e.g. ``connected``, ``connecting``)."""
    proc = _run(["-t", "-f", "GENERAL.STATE", "device", "show", WIFI_IFACE], timeout=8)
    if proc is None or proc.returncode != 0:
        return ""
    return proc.stdout.strip().lower()


def wlan_ipv4() -> str | None:
    """IPv4 address on ``wlan0``, without a prefix length."""
    proc = _run(["-t", "-f", "IP4.ADDRESS", "device", "show", WIFI_IFACE], timeout=8)
    if proc is None or proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if ":" not in line:
            continue
        addr = line.split(":", 1)[1].strip().split("/")[0]
        if addr and not addr.startswith("127."):
            return addr
    return None


def is_ap_active() -> bool:
    """True when our temporary setup AP is up."""
    if not is_available():
        return False
    return SETUP_AP_CON in _active_wifi_cons()


def is_client_connected() -> bool:
    """True when associated to a real Wi-Fi network (not our setup AP).

    NetworkManager can keep a saved profile marked "active" while it is still
    ``connecting`` or retrying in the background — that must not block the
    setup AP on the Pi Zero 2 W's single radio.
    """
    if not is_available():
        return False
    state = _device_state()
    if "connected" not in state or "connecting" in state or "disconnected" in state:
        return False
    client_cons = [n for n in _active_wifi_cons() if n != SETUP_AP_CON]
    if not client_cons:
        return False
    ssid = current_ssid()
    if ssid == SETUP_AP_SSID:
        return False
    return True


def has_usable_client() -> bool:
    """True when the device is on a real LAN with a routable client IP."""
    if not is_client_connected():
        return False
    ip = wlan_ipv4()
    if not ip:
        return False
    if ip.startswith("10.42.") or ip == SETUP_AP_GATEWAY:
        return False
    if ip.startswith("169.254."):
        return False
    return True


def _prepare_radio_for_ap() -> None:
    """Free ``wlan0`` and ensure the radio is on before beaconing.

    We only *transiently* free the radio (``device disconnect``) — we never set
    ``autoconnect=no`` on saved networks, because that persists to disk and would
    trap the device offline forever (it could never auto-rejoin a network that
    was merely briefly unreachable at boot). While the AP connection is active it
    holds the single radio, so a saved network can't steal it back.
    """
    if shutil.which("rfkill"):
        try:
            subprocess.run(
                ["rfkill", "unblock", "wifi"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    _run(["radio", "wifi", "on"], timeout=5)
    _run(["device", "set", WIFI_IFACE, "managed", "yes"], timeout=5)
    _run(["device", "disconnect", WIFI_IFACE], timeout=15)


def start_ap() -> tuple[bool, str]:
    """Bring up the temporary setup AP (idempotent).

    The Pi Zero 2 W has a single radio, so a saved network that NetworkManager
    keeps trying to auto-reconnect can hog wlan0 and stop the AP activating.
    We free the radio first, then (re)create the profile with explicit WPA2/RSN
    ciphers and a fixed 2.4 GHz channel — the bare ``key-mgmt wpa-psk`` form can
    leave wpa_supplicant unable to start beaconing on some brcmfmac builds.
    """
    if not is_available():
        return False, "nmcli unavailable"
    if is_ap_active():
        return True, "setup AP already up"
    last_err = "could not start setup AP"
    for attempt in range(2):
        _prepare_radio_for_ap()
        # Recreate the profile each time so the hardened settings always apply.
        _run(["connection", "delete", SETUP_AP_CON], timeout=10)
        add = _run(
            [
                "connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
                "con-name", SETUP_AP_CON, "autoconnect", "no", "ssid", SETUP_AP_SSID,
                "802-11-wireless.mode", "ap",
                "802-11-wireless.band", "bg", "802-11-wireless.channel", "6",
                "ipv4.method", "shared",
                "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", SETUP_AP_PASSWORD,
                "wifi-sec.proto", "rsn",
                "wifi-sec.pairwise", "ccmp", "wifi-sec.group", "ccmp",
            ],
            timeout=20,
        )
        if add is None or add.returncode != 0:
            last_err = add.stderr.strip() if add else "could not create AP profile"
            log.warning("setup AP profile create failed (attempt %d): %s", attempt + 1, last_err)
            continue
        up = _run(["connection", "up", SETUP_AP_CON], timeout=30)
        if up is not None and up.returncode == 0:
            log.info("setup AP %r up at %s", SETUP_AP_SSID, SETUP_AP_GATEWAY)
            return True, "setup AP up"
        last_err = up.stderr.strip() if up else "could not start setup AP"
        log.warning("setup AP up failed (attempt %d): %s", attempt + 1, last_err)
    return False, last_err


def stop_ap() -> tuple[bool, str]:
    """Take the setup AP down (idempotent)."""
    if not is_available():
        return False, "nmcli unavailable"
    proc = _run(["connection", "down", SETUP_AP_CON], timeout=15)
    if proc is not None and proc.returncode == 0:
        log.info("setup AP down")
        return True, "setup AP down"
    return False, (proc.stderr.strip() if proc else "could not stop setup AP")

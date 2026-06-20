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
    """Join (and persist) a Wi-Fi network. Returns ``(ok, message)``."""
    if not is_available():
        return False, "NetworkManager (nmcli) is not available on this host"
    if not ssid:
        return False, "missing SSID"
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

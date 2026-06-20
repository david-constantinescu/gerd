"""Local-network identity helpers — the bits needed to reach the device on a LAN.

Everything here is pure stdlib except QR generation, which uses the tiny
pure-Python ``segno`` package (optional — callers degrade gracefully if it is
missing). Works both on the Pi and on a dev machine / the simulator.
"""

from __future__ import annotations

import io
import logging
import socket

log = logging.getLogger("services.netinfo")

# The web dashboard listens on port 80 in production (see systemd/upright-web).
WEB_PORT = 80


def hostname() -> str:
    """Short hostname (e.g. ``softhoarders-pi``), without any domain suffix."""
    return socket.gethostname().split(".")[0]


def mdns_host() -> str:
    """mDNS / Bonjour name — resolvable as ``<hostname>.local`` on the LAN."""
    return f"{hostname()}.local"


def lan_ip() -> str | None:
    """Primary outbound IPv4 address, or ``None`` if offline.

    Uses the standard UDP-socket trick: no packet is actually sent, the kernel
    just picks the interface it *would* route through.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.255.255", 1))
        ip = s.getsockname()[0]
        return ip if ip and not ip.startswith("127.") else None
    except OSError:
        return None
    finally:
        s.close()


def _url_for(host: str) -> str:
    port = "" if WEB_PORT == 80 else f":{WEB_PORT}"
    return f"http://{host}{port}/"


def dashboard_url(*, prefer_mdns: bool = True) -> str:
    """Best URL to reach the dashboard. Prefers the friendly mDNS name; falls
    back to the raw IP when mDNS is unlikely to resolve."""
    if prefer_mdns:
        return _url_for(mdns_host())
    ip = lan_ip()
    return _url_for(ip) if ip else _url_for(mdns_host())


def status() -> dict[str, str | None]:
    """Snapshot for the OLED Network screen and the web /api/wifi/status."""
    return {
        "host": hostname(),
        "mdns": mdns_host(),
        "ip": lan_ip(),
        "url": dashboard_url(),
    }


# --------------------------------------------------------------------- QR codes
def _qr(data: str):
    try:
        import segno  # type: ignore[import-not-found]
    except ImportError:
        log.warning("segno not installed — QR codes disabled")
        return None
    return segno.make(data, error="m")


def qr_png_bytes(data: str, *, scale: int = 3, border: int = 2) -> bytes | None:
    qr = _qr(data)
    if qr is None:
        return None
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()


def qr_image(data: str, *, scale: int = 3, border: int = 2):
    """Return a PIL RGB image of the QR code, or ``None`` if unavailable."""
    png = qr_png_bytes(data, scale=scale, border=border)
    if png is None:
        return None
    from PIL import Image

    return Image.open(io.BytesIO(png)).convert("RGB")


def qr_svg(data: str, *, scale: int = 4, border: int = 2) -> str | None:
    qr = _qr(data)
    if qr is None:
        return None
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, border=border, xmldecl=False, svgns=True)
    return buf.getvalue().decode()

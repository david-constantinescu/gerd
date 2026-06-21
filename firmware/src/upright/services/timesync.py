"""Keep the system clock correct on a Pi Zero 2 W (which has no RTC).

chrony (configured by install.sh) is the primary mechanism and disciplines the
clock continuously over NTP. This module is the active belt-and-suspenders:

* on boot and whenever the network comes back, it forces an immediate chrony
  step (``chronyc -a makestep``) so the clock is right within seconds, and
* if NTP is blocked (some captive / corporate Wi-Fi blocks UDP 123) and the
  clock is implausibly old, it reads the ``Date`` header from an HTTPS request
  and sets the clock through the narrow ``upright-set-time`` sudo helper.

Everything degrades to a no-op off-Pi (no ``chronyc`` / sudoers helper), so the
simulator and dev machines are untouched.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

log = logging.getLogger("services.timesync")

# Clocks before this are obviously unsynced (no RTC → stale/epoch on boot).
_PLAUSIBLE_AFTER = datetime(2024, 1, 1, tzinfo=timezone.utc)
_CHECK_INTERVAL_S = 6 * 3600.0  # re-affirm every 6 h
_RETRY_INTERVAL_S = 120.0  # while the clock still looks wrong
_TIME_URLS = (
    "https://www.google.com/generate_204",
    "https://cloudflare.com",
)
_SETTIME_HELPER = "/usr/local/sbin/upright-set-time"


def clock_ok() -> bool:
    return datetime.now(timezone.utc) >= _PLAUSIBLE_AFTER


def _run(cmd: list[str], timeout: float = 15.0) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        return True
    except Exception as e:  # pragma: no cover - host/runtime specific
        log.debug("%s failed: %s", " ".join(cmd), e)
        return False


def _chrony_makestep() -> bool:
    """Ask chrony to step the clock to NTP time right now."""
    if shutil.which("chronyc") is None:
        return False
    # ``-a`` authorizes via the local socket; both forms are allowed in sudoers.
    return _run(["sudo", "-n", "chronyc", "-a", "makestep"]) or _run(
        ["sudo", "-n", "chronyc", "makestep"]
    )


def _http_time() -> datetime | None:
    """Best-effort wall-clock from a server's ``Date`` header (works sans NTP)."""
    for url in _TIME_URLS:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=8) as resp:
                date_hdr = resp.headers.get("Date")
            if date_hdr:
                return parsedate_to_datetime(date_hdr)
        except Exception as e:  # pragma: no cover - network specific
            log.debug("http time from %s failed: %s", url, e)
    return None


def _set_via_helper(when: datetime) -> bool:
    if not os.path.exists(_SETTIME_HELPER):
        return False
    epoch = int(when.astimezone(timezone.utc).timestamp())
    return _run(["sudo", "-n", _SETTIME_HELPER, str(epoch)])


def sync_now() -> bool:
    """Make one best effort to correct the clock. Returns True if it now looks ok."""
    _chrony_makestep()
    if clock_ok():
        return True
    # NTP likely blocked or not yet synced — fall back to HTTP Date.
    when = _http_time()
    if when is not None and when >= _PLAUSIBLE_AFTER:
        if _set_via_helper(when):
            log.info("clock set from HTTP Date: %s", when.isoformat())
        else:
            log.debug("HTTP time available but set helper unavailable")
    return clock_ok()


def status() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "clock_ok": clock_ok(),
        "utc": now.isoformat(timespec="seconds"),
        "chrony": shutil.which("chronyc") is not None,
    }


def _loop(stop: threading.Event) -> None:
    # Small startup delay so NetworkManager has a chance to associate first.
    stop.wait(15.0)
    while not stop.is_set():
        ok = False
        try:
            ok = sync_now()
        except Exception as e:  # pragma: no cover - runtime specific
            log.warning("timesync tick failed: %s", e)
        stop.wait(_CHECK_INTERVAL_S if ok else _RETRY_INTERVAL_S)


def start_thread(*, dry_run: bool = False) -> threading.Thread:
    """Start the clock-keeper. No-op thread on dry-run / when chrony is absent."""
    stop = threading.Event()
    active = (not dry_run) and shutil.which("chronyc") is not None
    target = (lambda: _loop(stop)) if active else (lambda: stop.wait())
    th = threading.Thread(target=target, name="timesync", daemon=True)
    th.stop = stop  # type: ignore[attr-defined]
    th.start()
    if active:
        log.info("time-sync watcher started")
    return th

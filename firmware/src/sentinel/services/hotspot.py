"""WiFi hotspot control. Wraps ``systemctl`` calls to hostapd / dnsmasq.

Also watches ``data/config.json`` and triggers a tunables reload when it
changes (so the webapp's settings sliders take effect immediately).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime

from ..config import CONFIG_PATH, TUNABLES, reload_tunables

log = logging.getLogger("services.hotspot")


def _systemctl(*args: str) -> bool:
    if shutil.which("systemctl") is None:
        return False
    try:
        subprocess.run(["sudo", "systemctl", *args], check=True)
        return True
    except subprocess.CalledProcessError as e:
        log.error("systemctl %s failed: %s", " ".join(args), e)
        return False


def is_active() -> bool:
    if shutil.which("systemctl") is None:
        return False
    r = subprocess.run(
        ["systemctl", "is-active", "hostapd"],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() == "active"


def turn_on() -> bool:
    log.info("turning hotspot ON")
    return _systemctl("start", "hostapd") and _systemctl("start", "dnsmasq")


def turn_off() -> bool:
    log.info("turning hotspot OFF")
    return _systemctl("stop", "dnsmasq") and _systemctl("stop", "hostapd")


def schedule_tick() -> None:
    """Call once per minute. Honours TUNABLES.hotspot_mode + on/off times."""
    mode = TUNABLES.hotspot_mode
    if mode == "always":
        if not is_active():
            turn_on()
        return
    if mode == "manual":
        return
    # scheduled
    now = datetime.now().strftime("%H:%M")
    if now == TUNABLES.hotspot_schedule_on:
        turn_on()
    elif now == TUNABLES.hotspot_schedule_off:
        turn_off()


def watch_config_file() -> None:
    """Try to start a watchdog observer; quietly no-op if watchdog isn't
    installed (e.g. dev machine)."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        return

    class _H(FileSystemEventHandler):
        def on_modified(self, event):
            if event.src_path.endswith(CONFIG_PATH.name):
                log.info("config.json changed — reloading")
                reload_tunables()

    obs = Observer()
    obs.schedule(_H(), str(CONFIG_PATH.parent), recursive=False)
    obs.daemon = True
    obs.start()

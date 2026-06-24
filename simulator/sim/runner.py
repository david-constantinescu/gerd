"""Boot the real firmware with the simulated HAL.

Order matters: we patch ``upright.config`` paths *before* any other firmware
module is imported (the firmware does ``from ..config import DB_PATH`` etc., so
the value is bound at import time — exactly the pattern the test-suite relies
on). Then we import the HAL/main/manager modules, install the sim backends, and
run ``upright.main.main(["--dry-run"])`` in a daemon thread.

``--dry-run`` is passed only so the firmware skips real GPIO claiming; every
hardware seam is already replaced by :func:`sim.hal_sim.install`.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from pathlib import Path

from . import hal_sim
from .state import SimDevice

log = logging.getLogger("sim.runner")

_HERE = Path(__file__).resolve()
SIM_ROOT = _HERE.parent.parent                       # gerd/simulator
FIRMWARE_ROOT = SIM_ROOT.parent / "firmware"          # gerd/firmware
FIRMWARE_SRC = FIRMWARE_ROOT / "src"
REAL_DATA = FIRMWARE_ROOT / "data"
SIM_DATA = SIM_ROOT / ".simdata"


class _LogTap(logging.Handler):
    """Mirror firmware log records into the device's UI log buffer."""

    def __init__(self, dev: SimDevice) -> None:
        super().__init__()
        self.dev = dev
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.dev.add_log(self.format(record))
        except Exception:
            pass


def _prepare_data(fresh: bool, demo: bool) -> None:
    """Copy the firmware data dir into an isolated sandbox so we never clobber it."""
    import sys

    sys.path.insert(0, str(FIRMWARE_SRC))
    import upright.config as cfg  # noqa: E402  — only config is imported so far

    SIM_DATA.mkdir(parents=True, exist_ok=True)
    copy_names = [
        "config.json",
        "foods.json",
        "demo_week.json",
        "demo_session.json",
        "display.default.json",
        "web_secret.txt",
    ]
    for name in copy_names:
        src = REAL_DATA / name
        dst = SIM_DATA / name
        if src.exists() and (fresh or not dst.exists()):
            shutil.copy2(src, dst)
    locales_src, locales_dst = REAL_DATA / "locales", SIM_DATA / "locales"
    if locales_src.is_dir() and fresh:
        if locales_dst.exists():
            shutil.rmtree(locales_dst)
        shutil.copytree(locales_src, locales_dst)
    elif locales_src.is_dir() and not locales_dst.exists():
        shutil.copytree(locales_src, locales_dst)
    # Seed the DB from the real one once (so demo history is visible), unless fresh.
    db_src, db_dst = REAL_DATA / "upright.db", SIM_DATA / "upright.db"
    if db_src.exists() and not db_dst.exists() and not fresh:
        shutil.copy2(db_src, db_dst)

    # Force interactive posture control: demo_mode would otherwise inject
    # synthetic sensor data and fight the UI sliders.
    cfg_path = SIM_DATA / "config.json"
    conf: dict = {}
    if cfg_path.exists():
        try:
            conf = json.loads(cfg_path.read_text())
        except Exception:
            conf = {}
    conf["demo_mode"] = bool(demo)
    cfg_path.write_text(json.dumps(conf, indent=2))

    # Redirect all firmware paths into the sandbox.
    cfg.DATA_DIR = SIM_DATA
    cfg.DB_PATH = SIM_DATA / "upright.db"
    cfg.CONFIG_PATH = SIM_DATA / "config.json"
    cfg.FOODS_PATH = SIM_DATA / "foods.json"
    # Models/audio stay pointed at the real (read-only) firmware tree.
    cfg.MODELS_DIR = FIRMWARE_ROOT / "models"
    cfg.AUDIO_DIR = FIRMWARE_ROOT / "audio"
    log.info("sim data sandbox: %s (demo_mode=%s)", SIM_DATA, demo)


def start_firmware(dev: SimDevice, *, fresh: bool = False, demo: bool = False) -> threading.Thread:
    """Set everything up and launch the firmware loop in a daemon thread."""
    _prepare_data(fresh=fresh, demo=demo)

    # Now safe to import the rest of the firmware (paths already redirected).
    import upright.main as main_mod  # noqa: F401  — imports hal/manager/services transitively

    # Tap firmware logging into the UI console.
    tap = _LogTap(dev)
    tap.setLevel(logging.INFO)
    logging.getLogger().addHandler(tap)
    logging.getLogger("upright").addHandler(tap)

    hal_sim.install(dev)

    def _run() -> None:
        try:
            main_mod.main(["--dry-run"])
        except Exception:
            log.exception("firmware loop crashed")

    t = threading.Thread(target=_run, name="firmware", daemon=True)
    t.start()
    log.info("firmware thread started")
    return t

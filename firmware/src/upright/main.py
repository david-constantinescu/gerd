"""Main entrypoint — wires HAL → event bus → ModeManager → services.

On the Pi this is started as ``python -m upright.main`` by
``systemd/upright.service``. Pass ``--dry-run`` to start the loop with all
HAL drivers in stub mode (no GPIO / I²C touched). Useful on macOS.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from . import __version__
from .config import reload_tunables
from .events import Event, EventBus, EventType
from .modes.manager import ModeManager
from .services import alerts as alerts_service
from .services import demo_seed
from .services import logger as logger_service
from .services import meds as meds_service
from .services import sleep as sleep_service

log = logging.getLogger("upright")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _init_gpio_pins(*, dry_run: bool) -> None:
    """Claim GPIO via lgpio before luma opens SPI (avoids SPI deadlocks on Pi)."""
    if dry_run:
        return
    from .config import PIN_BUTTON_A, PIN_BUTTON_B, PIN_LIPO_ALERT, PIN_MOTOR
    from .hal.gpio_lgpio import claim_input, claim_output

    claim_output(PIN_MOTOR, initial=0)
    claim_input(PIN_BUTTON_A)
    claim_input(PIN_BUTTON_B)
    claim_input(PIN_LIPO_ALERT)


def _start_hal(bus: EventBus, dry_run: bool) -> list[threading.Thread]:
    """Start every HAL polling thread. Returns the list so they can be joined."""
    from .hal import button, imu, power

    threads: list[threading.Thread] = []
    threads.append(imu.start_thread(bus, dry_run=dry_run))
    threads.append(power.start_thread(bus, dry_run=dry_run))
    threads.append(button.start_thread(bus, dry_run=dry_run))
    return threads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="upright", description="UpRight firmware")
    parser.add_argument("--dry-run", action="store_true", help="run with HAL stubs (no GPIO/I²C)")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)

    if args.version:
        print(f"upright {__version__}")
        return 0

    _setup_logging()
    tunables = reload_tunables()
    log.info("UpRight v%s starting (dry_run=%s)", __version__, args.dry_run)
    log.info("Wear side: %s | language: %s", tunables.wear_side, tunables.language)

    bus = EventBus()
    db = logger_service.Logger()
    if tunables.demo_mode:
        demo_seed.restart_demo_on_boot(db)
    db.boot_session()

    alerts = alerts_service.AlertManager(bus)
    sleep = sleep_service.SleepTracker(bus)
    meds = meds_service.MedReminders(bus, db)

    _init_gpio_pins(dry_run=args.dry_run)

    manager = ModeManager(bus, db, alerts=alerts, sleep=sleep, meds=meds)

    hal_threads = _start_hal(bus, dry_run=args.dry_run)

    stop_evt = threading.Event()

    def _shutdown(signum, _frame):
        log.info("signal %s received — shutting down", signum)
        stop_evt.set()
        bus.publish(Event(EventType.SHUTDOWN))

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        manager.run(stop_evt)
    finally:
        log.info("flushing database…")
        db.flush()
        db.close()
        for t in hal_threads:
            t.join(timeout=1.0)
        log.info("bye")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

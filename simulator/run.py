#!/usr/bin/env python3
"""UpRight Raspberry Pi simulator — single entrypoint.

Runs the real firmware (firmware/src/upright) with a simulated hardware layer
and serves a browser "virtual device" + HTTP control API.

    python run.py                 # http://localhost:8000
    python run.py --port 9000
    python run.py --fresh         # reset the data sandbox first
    python run.py --demo          # seed synthetic week data (disables live posture)

Use the firmware's venv (it already has flask + pillow + numpy):
    ../firmware/.venv/bin/python run.py
"""

from __future__ import annotations

import argparse
import logging
import webbrowser

from sim.runner import start_firmware
from sim.server import create_app
from sim.state import SimDevice


def main() -> int:
    p = argparse.ArgumentParser(prog="upright-sim", description="UpRight Pi simulator")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--fresh", action="store_true", help="reset the .simdata sandbox")
    p.add_argument("--demo", action="store_true", help="enable demo_mode (synthetic data)")
    p.add_argument("--open", action="store_true", help="open the bench in a browser")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    dev = SimDevice()
    start_firmware(dev, fresh=args.fresh, demo=args.demo)

    app = create_app(dev)
    url = f"http://localhost:{args.port}"
    print(f"\n  UpRight simulator → {url}\n")
    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    # threaded=True so the MJPEG stream + API serve concurrently with the firmware.
    app.run(host=args.host, port=args.port, threaded=True, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

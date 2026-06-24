"""Simulated HAL backends + the monkeypatch installer.

These mirror the *public interface* of each real HAL module so the firmware
runs unchanged, but instead of touching GPIO / I²C / SPI / a USB camera they
read inputs from / write outputs to the shared :class:`SimDevice`.

``install(dev)`` must be called after the relevant ``upright.*`` modules have
been imported (the runner guarantees this) and before ``upright.main.main()``
constructs anything.
"""

from __future__ import annotations

import logging
import threading
import time

from .state import PANEL_H, PANEL_W, SimDevice

log = logging.getLogger("sim.hal")


# --------------------------------------------------------------------------- #
# Display — reuse the REAL Display class (resize/convert/blank logic) but feed  #
# a fake luma-style panel that captures each frame instead of driving SPI.      #
# --------------------------------------------------------------------------- #
def _make_sim_display(dev: SimDevice):
    from upright.hal.display import Display

    class _SimPanel:
        """Quacks like a luma device: ``display(image)`` and ``clear()``."""

        def __init__(self) -> None:
            self.width = PANEL_W
            self.height = PANEL_H

        def display(self, image) -> None:
            dev.set_frame(image)

        def clear(self) -> None:
            from PIL import Image

            dev.set_frame(Image.new("RGB", (PANEL_W, PANEL_H), (0, 0, 0)))

    class SimDisplay(Display):
        def __init__(self, *, dry_run: bool = False, autoprobe: bool = True) -> None:
            # Build the real object with no hardware probing, then graft on a
            # config + device matching the actual Pi panel so .color / new_frame
            # / show / blanking all behave exactly as on-device.
            super().__init__(dry_run=True, autoprobe=False)
            self._dry_run = False
            self._cfg = {
                "interface": "spi",
                "driver": "adafruit_st7735r",
                "width": PANEL_W,
                "height": PANEL_H,
                "rotate": 90,
            }
            self.width = PANEL_W
            self.height = PANEL_H
            self._device = _SimPanel()
            log.info("sim display ready: %dx%d RGB (ST7735R)", PANEL_W, PANEL_H)

    return SimDisplay


# --------------------------------------------------------------------------- #
# Input + sensor threads (button / encoder / imu / power start_thread)          #
# --------------------------------------------------------------------------- #
def _thread(target):
    t = threading.Thread(target=target, daemon=True)
    t.stop = threading.Event()  # type: ignore[attr-defined]
    return t


def _make_button_start(dev: SimDevice):
    from upright.events import Event, EventType

    def start_thread(evt_bus, *, dry_run: bool):
        def loop():
            while not th.stop.is_set():
                try:
                    button, pattern = dev.button_q.get(timeout=0.2)
                except Exception:
                    continue
                evt_bus.publish(
                    Event(
                        EventType.BUTTON_PRESS,
                        payload={"pattern": pattern, "button": button, "raw": pattern},
                    )
                )

        th = _thread(loop)
        th.start()
        return th

    return start_thread


def _make_encoder_start(dev: SimDevice):
    from upright.events import Event, EventType

    def start_thread(evt_bus, *, dry_run: bool):
        def loop():
            while not th.stop.is_set():
                try:
                    action = dev.encoder_q.get(timeout=0.2)
                except Exception:
                    continue
                if action == "click":
                    evt_bus.publish(Event(EventType.ENCODER_CLICK))
                else:
                    evt_bus.publish(
                        Event(EventType.ENCODER_ROTATE, payload={"dir": action})
                    )

        th = _thread(loop)
        th.start()
        return th

    return start_thread


def _make_imu_start(dev: SimDevice):
    from upright.events import Event, EventType

    def start_thread(evt_bus, *, dry_run: bool):
        def loop():
            while not th.stop.is_set():
                ax, ay, az = dev.accel()
                evt_bus.publish(
                    Event(
                        EventType.POSTURE_SAMPLE,
                        payload={
                            "pitch": dev.pitch,
                            "roll": dev.roll,
                            "pitch_raw": dev.pitch,
                            "ax": ax,
                            "ay": ay,
                            "az": az,
                        },
                    )
                )
                th.stop.wait(max(0.05, 1.0 / max(0.5, dev.imu_hz)))

        th = _thread(loop)
        th.start()
        return th

    return start_thread


def _make_power_start(dev: SimDevice):
    from upright.events import Event, EventType

    def start_thread(evt_bus, *, dry_run: bool):
        def loop():
            while not th.stop.is_set():
                low = dev.battery_low or dev.battery_pct <= 20
                evt_bus.publish(
                    Event(
                        EventType.POWER_SAMPLE,
                        payload={
                            "battery_pct": dev.battery_pct,
                            "battery_low": low,
                            "battery_ok": not low,
                            "battery_source": "sim",
                        },
                    )
                )
                th.stop.wait(5.0)

        th = _thread(loop)
        th.start()
        return th

    return start_thread


# --------------------------------------------------------------------------- #
# Camera (capture / capture_with_warmup / CameraPreview)                        #
# --------------------------------------------------------------------------- #
def _make_camera(dev: SimDevice):
    def capture(width=640, height=480, device="", prefer_opencv=False):
        return dev.get_camera_frame(width, height)

    def capture_with_warmup(retries=2):
        # Bench uploads are still images at arbitrary resolution — use the
        # original pixels for classification (resize only inside TFLite).
        with dev._camera_lock:
            img = dev._camera_img
        if img is not None:
            return img.convert("RGB")
        return dev.get_camera_frame(640, 480)

    class CameraPreview:
        def __init__(self, *, interval_s: float = 0.35) -> None:
            self._running = False
            self._interval = interval_s

        @property
        def running(self) -> bool:
            return self._running

        def start(self) -> None:
            self._running = True

        def stop(self) -> None:
            self._running = False

        def latest(self):
            if not self._running:
                return None
            return dev.get_camera_frame(320, 240)

    return capture, capture_with_warmup, CameraPreview


# --------------------------------------------------------------------------- #
# Motor / Audio (record the call so the UI can react)                           #
# --------------------------------------------------------------------------- #
def _make_motor(dev: SimDevice):
    class Motor:
        def __init__(self, *, dry_run: bool = False) -> None:
            self._dry_run = dry_run

        def buzz(self, pattern: str = "gentle") -> None:
            dev.add_motor_event(pattern)
            log.info("motor buzz: %s", pattern)

        def buzz_async(self, pattern: str = "gentle") -> None:
            self.buzz(pattern)

    return Motor


def _make_audio(dev: SimDevice):
    class Audio:
        def __init__(self, *, dry_run: bool = False) -> None:
            self._dry_run = dry_run

        def play(self, name: str) -> None:
            dev.add_audio_event(name)
            log.info("audio play: %s", name)

        def play_async(self, name: str) -> None:
            self.play(name)

    return Audio


# --------------------------------------------------------------------------- #
# Misc: a dummy ``signal`` so main() can register handlers off the main thread  #
# --------------------------------------------------------------------------- #
class _DummySignal:
    SIGTERM = 15
    SIGINT = 2

    @staticmethod
    def signal(*_args, **_kwargs):  # noqa: D401 - no-op
        return None


def install(dev: SimDevice) -> None:
    """Replace every hardware seam with a simulated backend."""
    import upright.hal.button as button
    import upright.hal.camera as camera
    import upright.hal.encoder as encoder
    import upright.hal.imu as imu
    import upright.hal.motor as motor
    import upright.hal.power as power
    import upright.main as main_mod
    import upright.modes.manager as manager_mod
    import upright.services.alerts as alerts_mod
    from upright.hal import audio as audio_mod

    # Display
    main_mod.Display = _make_sim_display(dev)

    # Signals (main() runs in a worker thread here)
    main_mod.signal = _DummySignal()

    # Input + sensor threads
    button.start_thread = _make_button_start(dev)
    encoder.start_thread = _make_encoder_start(dev)
    imu.start_thread = _make_imu_start(dev)
    power.start_thread = _make_power_start(dev)

    # Keep imu.set_rate functional: record the requested rate on the device.
    def set_rate(hz: float) -> None:
        dev.imu_hz = float(hz)

    imu.set_rate = set_rate

    # Camera
    cap, cap_warm, preview_cls = _make_camera(dev)
    camera.capture = cap
    camera.capture_with_warmup = cap_warm
    camera.CameraPreview = preview_cls
    manager_mod.CameraPreview = preview_cls  # manager imported the name directly

    # Motor / Audio (alerts imported the classes into its own namespace)
    sim_motor = _make_motor(dev)
    sim_audio = _make_audio(dev)
    motor.Motor = sim_motor
    audio_mod.Audio = sim_audio
    alerts_mod.Motor = sim_motor
    alerts_mod.Audio = sim_audio

    # Capture the live ModeManager + bus once the firmware constructs them.
    _orig_init = manager_mod.ModeManager.__init__

    def _init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        dev.manager = self
        dev.bus = getattr(self, "bus", None)
        dev.booted.set()

    manager_mod.ModeManager.__init__ = _init

    from . import wifi_sim

    wifi_sim.install(dev)

    log.info("sim HAL installed")

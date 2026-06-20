"""UpRight Pi simulator — runs the real firmware with a simulated hardware layer.

The firmware in ``firmware/src/upright`` is imported and executed unchanged. Its
lowest layer (the HAL: buttons, IMU, power, display, camera, motor, audio) is
swapped for in-process simulation backends wired to a browser "virtual device"
and an HTTP control API. Everything above the HAL — the boot sequence, the FSM,
the menu system, posture detection, the services, and the exact ``ui.render``
frames pushed to the panel — is the genuine firmware code path that runs on the
Raspberry Pi.
"""

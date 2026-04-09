"""Hardware abstraction layer.

Each module in here wraps exactly one piece of hardware. Pi-only libraries
(``RPi.GPIO``, ``smbus2``, ``luma.oled``, ``tflite_runtime``) are imported
*lazily* inside functions so the package still imports cleanly on macOS for
unit tests and editor tooling.
"""

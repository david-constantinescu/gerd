"""Software I²C for MPU6050 on GPIO 27 (SDA) / 3 (SCL) via lgpio.

GPIO 28 is not usable on Pi Zero 2 W (SDIO). See reference docs/WIRING.md.
"""

from __future__ import annotations

import logging
import time

from ..config import PIN_MPU6050_SCL, PIN_MPU6050_SDA
from . import gpio_lgpio as gpio

log = logging.getLogger("hal.i2c_bitbang")

_PWR_MGMT_1 = 0x6B
_WHO_AM_I = 0x75
_MPU_WHO_AM_I = 0x68
_CONFIG = 0x1A
_DLPF_5HZ = 6
_ACCEL_XOUT_H = 0x3B


def _twos(val: int) -> int:
    return val - 65536 if val & 0x8000 else val


class Mpu6050Bitbang:
    def __init__(self, sda: int = PIN_MPU6050_SDA, scl: int = PIN_MPU6050_SCL) -> None:
        self._sda = sda
        self._scl = scl
        self._addr = 0x68

    def open(self, *, timeout_s: float = 1.5) -> None:
        deadline = time.monotonic() + timeout_s
        self._bus_idle()
        for addr in (0x68, 0x69):
            if time.monotonic() > deadline:
                break
            self._addr = addr
            try:
                self._write_reg(_PWR_MGMT_1, 0x00)
                time.sleep(0.05)
                who = self._read_reg(_WHO_AM_I)
                if who == _MPU_WHO_AM_I:
                    self._write_reg(_CONFIG, _DLPF_5HZ)
                    log.info(
                        "MPU6050 bit-bang on GPIO %s/%s addr 0x%02x WHO_AM_I ok",
                        self._sda,
                        self._scl,
                        addr,
                    )
                    return
            except OSError:
                continue
        raise OSError(
            f"MPU6050 not found on bit-bang I²C (SDA=GPIO{self._sda} SCL=GPIO{self._scl})"
        )

    def read_accel(self) -> tuple[float, float, float]:
        raw = self._read_regs(_ACCEL_XOUT_H, 6)
        ax = _twos(raw[0] << 8 | raw[1]) / 16384.0
        ay = _twos(raw[2] << 8 | raw[3]) / 16384.0
        az = _twos(raw[4] << 8 | raw[5]) / 16384.0
        return ax, ay, az

    def close(self) -> None:
        gpio.free(self._sda)
        gpio.free(self._scl)

    def _sda_release(self) -> None:
        gpio.claim_input_strict(self._sda)

    def _sda_low(self) -> None:
        gpio.claim_output_strict(self._sda, initial=0)

    def _scl_release(self) -> None:
        gpio.claim_input_strict(self._scl)

    def _scl_low(self) -> None:
        gpio.claim_output_strict(self._scl, initial=0)

    def _read_sda(self) -> int:
        return gpio.read_gpio(self._sda)

    def _tick(self) -> None:
        time.sleep(0.00008)

    def _bus_idle(self) -> None:
        try:
            gpio.claim_input_strict(self._sda)
            gpio.claim_input_strict(self._scl)
        except Exception as e:
            if self._scl == 28:
                raise OSError(
                    "GPIO 28 is reserved on Pi Zero 2 W — move MPU6050 SCL to GPIO 3 "
                    "(header pin 5) and update wiring"
                ) from e
            raise
        self._tick()

    def _start(self) -> None:
        self._sda_release()
        self._scl_release()
        self._tick()
        self._sda_low()
        self._tick()
        self._scl_low()
        self._tick()

    def _stop(self) -> None:
        self._sda_low()
        self._tick()
        self._scl_release()
        self._tick()
        self._sda_release()
        self._tick()

    def _write_byte(self, value: int) -> None:
        for bit in range(7, -1, -1):
            if value & (1 << bit):
                self._sda_release()
            else:
                self._sda_low()
            self._tick()
            self._scl_release()
            self._tick()
            self._scl_low()
            self._tick()
        self._sda_release()
        self._tick()
        self._scl_release()
        self._tick()
        self._scl_low()
        self._tick()
        if self._read_sda():
            raise OSError("I²C NACK")

    def _read_byte(self, *, ack: bool) -> int:
        value = 0
        self._sda_release()
        for bit in range(7, -1, -1):
            self._tick()
            self._scl_release()
            self._tick()
            if self._read_sda():
                value |= 1 << bit
            self._scl_low()
            self._tick()
        if ack:
            self._sda_low()
        else:
            self._sda_release()
        self._tick()
        self._scl_release()
        self._tick()
        self._scl_low()
        self._tick()
        self._sda_release()
        return value

    def _write_reg(self, reg: int, val: int) -> None:
        self._start()
        self._write_byte(self._addr << 1)
        self._write_byte(reg)
        self._write_byte(val)
        self._stop()

    def _read_reg(self, reg: int) -> int:
        self._start()
        self._write_byte(self._addr << 1)
        self._write_byte(reg)
        self._start()
        self._write_byte((self._addr << 1) | 1)
        val = self._read_byte(ack=False)
        self._stop()
        return val

    def _read_regs(self, reg: int, count: int) -> list[int]:
        self._start()
        self._write_byte(self._addr << 1)
        self._write_byte(reg)
        self._start()
        self._write_byte((self._addr << 1) | 1)
        out = []
        for i in range(count):
            out.append(self._read_byte(ack=(i < count - 1)))
        self._stop()
        return out

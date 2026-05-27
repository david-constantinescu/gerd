"""Software I²C for MPU6050 on GPIO 27 (SDA) / 28 (SCL) via lgpio.

Used when the kernel ``i2c-gpio`` overlay is absent or stuck (ghost ACK bus).
"""

from __future__ import annotations

import logging
import time

from ..config import PIN_MPU6050_SCL, PIN_MPU6050_SDA

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
        self._h: int | None = None
        self._addr = 0x68

    def open(self) -> None:
        import lgpio  # type: ignore[import-not-found]

        self._h = lgpio.gpiochip_open(0)
        for pin in (self._sda, self._scl):
            lgpio.gpio_claim_input(self._h, pin, lgpio.SET_PULL_UP)
        self._bus_idle()
        for addr in (0x68, 0x69):
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
        raise OSError("MPU6050 not found on bit-bang I²C")

    def read_accel(self) -> tuple[float, float, float]:
        raw = self._read_regs(_ACCEL_XOUT_H, 6)
        ax = _twos(raw[0] << 8 | raw[1]) / 16384.0
        ay = _twos(raw[2] << 8 | raw[3]) / 16384.0
        az = _twos(raw[4] << 8 | raw[5]) / 16384.0
        return ax, ay, az

    def close(self) -> None:
        if self._h is not None:
            import lgpio  # type: ignore[import-not-found]

            lgpio.gpiochip_close(self._h)
            self._h = None

    def _sda_release(self) -> None:
        import lgpio  # type: ignore[import-not-found]

        lgpio.gpio_claim_input(self._h, self._sda, lgpio.SET_PULL_UP)

    def _sda_low(self) -> None:
        import lgpio  # type: ignore[import-not-found]

        lgpio.gpio_claim_output(self._h, self._sda, 0)

    def _scl_release(self) -> None:
        import lgpio  # type: ignore[import-not-found]

        lgpio.gpio_claim_input(self._h, self._scl, lgpio.SET_PULL_UP)

    def _scl_low(self) -> None:
        import lgpio  # type: ignore[import-not-found]

        lgpio.gpio_claim_output(self._h, self._scl, 0)

    def _read_sda(self) -> int:
        import lgpio  # type: ignore[import-not-found]

        return int(lgpio.gpio_read(self._h, self._sda))

    def _tick(self) -> None:
        time.sleep(0.00008)

    def _bus_idle(self) -> None:
        self._sda_release()
        self._scl_release()
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

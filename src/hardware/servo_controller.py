from __future__ import annotations

import threading
import time
from typing import Dict

from src.models import ToolClass

try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685

    PCA_AVAILABLE = True
except Exception:
    board = None
    busio = None
    PCA9685 = None
    PCA_AVAILABLE = False
    print("[WARN] PCA9685 dependencies not found - servo controller in simulation mode")


def _angle_to_pulse_us(angle: int) -> int:
    """Convert angle in degrees (0-180) to pulse width in microseconds."""
    return int(500 + (angle / 180.0) * 2000)


def _pulse_us_to_duty_cycle(pulse_us: int, frequency_hz: int) -> int:
    period_us = 1_000_000 / frequency_hz
    return int((pulse_us / period_us) * 0xFFFF)


class ServoController:
    """Controls flap servos using PCA9685 with simulation fallback."""

    _PWM_FREQUENCY_HZ = 50
    _LEGACY_GPIO_TO_PCA_CHANNEL = {
        17: 0,  # flap1 / plier
        27: 1,  # flap2 / screwdriver
        22: 2,  # flap3 / wrench
    }

    def __init__(
        self,
        servo_pins: Dict[ToolClass, int],
        open_angle: int,
        close_angle: int,
        open_secs: float,
    ) -> None:
        self.servo_pins = servo_pins
        self.open_angle = open_angle
        self.close_angle = close_angle
        self.open_secs = open_secs
        self._timers: Dict[ToolClass, threading.Timer] = {}
        self._channels = {tool: self._to_channel(pin) for tool, pin in servo_pins.items()}

        if PCA_AVAILABLE:
            try:
                i2c = busio.I2C(board.SCL, board.SDA)
                self.pca = PCA9685(i2c)
                self.pca.frequency = self._PWM_FREQUENCY_HZ
                for channel in self._channels.values():
                    self._set_angle(channel, self.close_angle)
            except Exception as exc:
                print(f"[WARN] PCA9685 init failed ({exc}) - simulation mode")
                self.pca = None
        else:
            self.pca = None

    @classmethod
    def _to_channel(cls, pin_or_channel: int) -> int:
        if 0 <= pin_or_channel <= 15:
            return pin_or_channel
        if pin_or_channel in cls._LEGACY_GPIO_TO_PCA_CHANNEL:
            mapped = cls._LEGACY_GPIO_TO_PCA_CHANNEL[pin_or_channel]
            print(f"[INFO] Mapping legacy GPIO pin {pin_or_channel} -> PCA9685 channel {mapped}")
            return mapped
        raise ValueError(
            f"Invalid PCA9685 channel '{pin_or_channel}'. Use 0-15 or one of: "
            f"{sorted(cls._LEGACY_GPIO_TO_PCA_CHANNEL)}"
        )

    def _set_angle(self, channel: int, angle: int) -> None:
        pulse = _angle_to_pulse_us(angle)
        duty_cycle = _pulse_us_to_duty_cycle(pulse, self._PWM_FREQUENCY_HZ)
        if self.pca:
            self.pca.channels[channel].duty_cycle = duty_cycle
        else:
            print(f"[SIM] Servo channel {channel} -> {angle} degrees")

    def open(self, tool: ToolClass, auto_close: bool = True) -> bool:
        channel = self._channels.get(tool)
        if channel is None:
            print(f"[WARN] No servo mapped for '{tool.value}'")
            return False

        timer = self._timers.pop(tool, None)
        if timer:
            timer.cancel()

        print(f"[SERVO] Opening compartment: {tool.value}")
        self._set_angle(channel, self.open_angle)

        if auto_close:
            t = threading.Timer(self.open_secs, self.close, args=[tool])
            t.daemon = True
            t.start()
            self._timers[tool] = t
        return True

    def close(self, tool: ToolClass) -> None:
        channel = self._channels.get(tool)
        if channel is None:
            return
        print(f"[SERVO] Closing compartment: {tool.value}")
        self._set_angle(channel, self.close_angle)
        self._timers.pop(tool, None)

    def close_all(self) -> None:
        for tool in self.servo_pins:
            self.close(tool)

    def cleanup(self) -> None:
        self.close_all()
        time.sleep(0.5)
        if self.pca:
            for channel in self._channels.values():
                self.pca.channels[channel].duty_cycle = 0
            self.pca.deinit()

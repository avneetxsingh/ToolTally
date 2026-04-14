from __future__ import annotations

import threading
import time
from typing import Dict

from src.models import ToolClass

try:
    import pigpio

    GPIO_AVAILABLE = True
except ImportError:
    pigpio = None
    GPIO_AVAILABLE = False
    print("[WARN] pigpio not found - servo controller in simulation mode")


def _angle_to_pulse(angle: int) -> int:
    """Convert angle in degrees (0-180) to pulse width in microseconds."""
    return int(500 + (angle / 180.0) * 2000)


class ServoController:
    """Controls flap servos using pigpio with simulation fallback."""

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

        if GPIO_AVAILABLE:
            self.pi = pigpio.pi()
            if not self.pi.connected:
                print("[WARN] pigpio daemon not running - simulation mode")
                self.pi = None
            else:
                for pin in self.servo_pins.values():
                    self.pi.set_mode(pin, pigpio.OUTPUT)
                    self._set_angle(pin, self.close_angle)
        else:
            self.pi = None

    def _set_angle(self, pin: int, angle: int) -> None:
        if self.pi:
            self.pi.set_servo_pulsewidth(pin, _angle_to_pulse(angle))
        else:
            print(f"[SIM] Servo pin {pin} -> {angle} degrees")

    def open(self, tool: ToolClass, auto_close: bool = False) -> bool:
        pin = self.servo_pins.get(tool)
        if pin is None:
            print(f"[WARN] No servo mapped for '{tool.value}'")
            return False

        timer = self._timers.pop(tool, None)
        if timer:
            timer.cancel()

        self._set_angle(pin, self.open_angle)

        if auto_close:
            t = threading.Timer(self.open_secs, self.close, args=[tool])
            t.daemon = True
            t.start()
            self._timers[tool] = t
        return True

    def close(self, tool: ToolClass) -> None:
        pin = self.servo_pins.get(tool)
        if pin is None:
            return
        self._set_angle(pin, self.close_angle)
        self._timers.pop(tool, None)

    def close_all(self) -> None:
        for tool in self.servo_pins:
            self.close(tool)

    def cleanup(self) -> None:
        self.close_all()
        time.sleep(0.2)
        if self.pi:
            for pin in self.servo_pins.values():
                self.pi.set_servo_pulsewidth(pin, 0)
            self.pi.stop()

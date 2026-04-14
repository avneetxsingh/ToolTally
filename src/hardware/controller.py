from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from src.models import ToolClass
from src.hardware.servo_controller import ServoController


class HardwareController(ABC):
    @abstractmethod
    def initialize_safe_state(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def open_flap(self, tool: ToolClass) -> None:
        raise NotImplementedError

    @abstractmethod
    def close_all_flaps(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def unlock_drawer(self, tool: ToolClass) -> None:
        raise NotImplementedError

    @abstractmethod
    def lock_drawer(self, tool: ToolClass) -> None:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        raise NotImplementedError


class MockHardwareController(HardwareController):
    def __init__(self, flap_pins: Dict[ToolClass, int], solenoid_pins: Dict[ToolClass, int]) -> None:
        self.flap_pins = flap_pins
        self.solenoid_pins = solenoid_pins

    def initialize_safe_state(self) -> None:
        print("[HW] init safe state: flaps closed, drawers locked")

    def open_flap(self, tool: ToolClass) -> None:
        print(f"[HW] open flap for {tool.value} (pin={self.flap_pins.get(tool)})")

    def close_all_flaps(self) -> None:
        print("[HW] close all flaps")

    def unlock_drawer(self, tool: ToolClass) -> None:
        print(f"[HW] unlock drawer for {tool.value} (pin={self.solenoid_pins.get(tool)})")

    def lock_drawer(self, tool: ToolClass) -> None:
        print(f"[HW] lock drawer for {tool.value} (pin={self.solenoid_pins.get(tool)})")

    def shutdown(self) -> None:
        self.close_all_flaps()
        for tool in self.solenoid_pins:
            self.lock_drawer(tool)
        print("[HW] shutdown complete")


class RaspberryPiHardwareController(HardwareController):
    def __init__(
        self,
        flap_pins: Dict[ToolClass, int],
        solenoid_pins: Dict[ToolClass, int],
        active_low: bool = False,
        servo_open_angle: int = 90,
        servo_close_angle: int = 0,
        servo_open_secs: float = 1.0,
    ) -> None:
        self.solenoid_pins = solenoid_pins
        self.servo = ServoController(
            servo_pins=flap_pins,
            open_angle=servo_open_angle,
            close_angle=servo_close_angle,
            open_secs=servo_open_secs,
        )

        try:
            from gpiozero import OutputDevice
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("gpiozero is required for raspberry_pi mode") from exc

        self.solenoids = {
            tool: OutputDevice(pin, active_high=not active_low, initial_value=False)
            for tool, pin in solenoid_pins.items()
        }

    def initialize_safe_state(self) -> None:
        self.close_all_flaps()
        for tool in self.solenoids:
            self.lock_drawer(tool)

    def open_flap(self, tool: ToolClass) -> None:
        self.servo.open(tool)

    def close_all_flaps(self) -> None:
        self.servo.close_all()

    def unlock_drawer(self, tool: ToolClass) -> None:
        self.solenoids[tool].on()

    def lock_drawer(self, tool: ToolClass) -> None:
        self.solenoids[tool].off()

    def shutdown(self) -> None:
        self.close_all_flaps()
        for tool in self.solenoids:
            self.lock_drawer(tool)
        for solenoid in self.solenoids.values():
            solenoid.close()
        self.servo.cleanup()

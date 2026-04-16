from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.models import ToolClass


@dataclass(frozen=True)
class TimingConfig:
    flap_open_seconds: float
    flap_settle_seconds: float
    drawer_unlock_seconds: float
    detection_cooldown_seconds: float


@dataclass(frozen=True)
class HardwareConfig:
    mode: str
    flap_pins: Dict[ToolClass, int]
    solenoid_pins: Dict[ToolClass, int]
    linearactuator: Optional[int]
    active_low: bool
    servo_open_angle: int
    servo_close_angle: int


@dataclass(frozen=True)
class RuntimeConfig:
    database_path: str
    allowed_pin_suffixes: List[str]


@dataclass(frozen=True)
class DetectionConfig:
    mode: str
    camera_index: int
    show_preview: bool


@dataclass(frozen=True)
class AppConfig:
    timing: TimingConfig
    hardware: HardwareConfig
    runtime: RuntimeConfig
    detection: DetectionConfig


def _to_tool_map(raw: Dict[str, int]) -> Dict[ToolClass, int]:
    mapped: Dict[ToolClass, int] = {}
    for key, value in raw.items():
        tool = ToolClass(key)
        if tool == ToolClass.WHITE:
            continue
        mapped[tool] = value
    return mapped


def load_config(path: str | Path) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    timing = TimingConfig(**data["timing"])
    hardware_raw = data["hardware"]
    runtime_raw = data["runtime"]
    detection_raw = data.get("detection", {})

    hardware = HardwareConfig(
        mode=hardware_raw["mode"],
        flap_pins=_to_tool_map(hardware_raw["flap_pins"]),
        solenoid_pins=_to_tool_map(hardware_raw["solenoid_pins"]),
        linearactuator=(
            int(hardware_raw["linearactuator"])
            if hardware_raw.get("linearactuator") is not None
            else None
        ),
        active_low=bool(hardware_raw.get("active_low", False)),
        servo_open_angle=int(hardware_raw.get("servo_open_angle", 90)),
        servo_close_angle=int(hardware_raw.get("servo_close_angle", 0)),
    )
    runtime = RuntimeConfig(
        database_path=runtime_raw["database_path"],
        allowed_pin_suffixes=list(runtime_raw.get("allowed_pin_suffixes", [])),
    )
    detection = DetectionConfig(
        mode=str(detection_raw.get("mode", "manual")),
        camera_index=int(detection_raw.get("camera_index", 0)),
        show_preview=bool(detection_raw.get("show_preview", True)),
    )
    return AppConfig(timing=timing, hardware=hardware, runtime=runtime, detection=detection)

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models import ToolClass, ToolEvent, tool_from_label


class DetectionProvider(ABC):
    @abstractmethod
    def next_event(self) -> ToolEvent:
        raise NotImplementedError


class ManualInputDetectionProvider(DetectionProvider):
    def next_event(self) -> ToolEvent:
        value = input(
            "Detected class [white/plier/pliers/screwdriver/wrench/quit]: "
        ).strip().lower()
        if value == "quit":
            raise KeyboardInterrupt
        tool = tool_from_label(value)
        if tool is None:
            raise ValueError(f"Unknown class label: {value}")
        return ToolEvent(tool=tool, confidence=1.0, source="manual")


class CameraDetectionProvider(DetectionProvider):
    def __init__(self, camera_index: int = 0, show_preview: bool = True) -> None:
        from CameraDetection import CameraDetectionEngine

        self.engine = CameraDetectionEngine(
            camera_index=camera_index,
            show_preview=show_preview,
        )

    def next_event(self) -> ToolEvent:
        tool, confidence = self.engine.next_tool_event()
        return ToolEvent(tool=tool, confidence=confidence, source="camera")

    def cleanup(self) -> None:
        self.engine.cleanup()

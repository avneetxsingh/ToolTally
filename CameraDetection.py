#!/usr/bin/env python3
"""Camera detection adapter for ToolTally.

This currently provides a camera loop with manual class keying:
- 0 -> white
- 1 -> plier
- 2 -> screwdriver
- 3 -> wrench
- q -> quit

Replace `_infer_tool` with your trained model inference when ready.
"""

from __future__ import annotations

import argparse
from typing import Tuple

import cv2

from src.models import ToolClass, tool_from_label


KEY_TO_TOOL = {
    ord("0"): ToolClass.WHITE,
    ord("1"): ToolClass.PLIER,
    ord("2"): ToolClass.SCREWDRIVER,
    ord("3"): ToolClass.WRENCH,
}

# Preserve exact model training class order/labels.
CLASS_NAMES = ["pliers", "screwdriver", "white", "wrench"]


class CameraDetectionEngine:
    def __init__(self, camera_index: int = 0, show_preview: bool = True) -> None:
        self.camera_index = camera_index
        self.show_preview = show_preview
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Unable to open camera index {camera_index}.")

    def _infer_tool(self, frame) -> Tuple[ToolClass, float]:
        # Placeholder until model integration lands.
        # Keep returning WHITE by default and allow operator key overrides.
        return ToolClass.WHITE, 0.0

    def map_model_label(self, label: str) -> ToolClass:
        tool = tool_from_label(label)
        if tool is None:
            raise ValueError(f"Unsupported model label: {label}")
        return tool

    def next_tool_event(self) -> Tuple[ToolClass, float]:
        while True:
            ok, frame = self.cap.read()
            if not ok:
                raise RuntimeError("Failed to read frame from camera.")

            predicted_tool, confidence = self._infer_tool(frame)

            if self.show_preview:
                text = (
                    "Tool: "
                    f"{predicted_tool.value} ({confidence:.2f}) | "
                    "Keys: 0=white 1=plier 2=screwdriver 3=wrench q=quit"
                )
                cv2.putText(
                    frame,
                    text,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("ToolTally Camera Detection", frame)
                key = cv2.waitKey(1) & 0xFF
            else:
                key = -1

            if key == ord("q"):
                raise KeyboardInterrupt
            if key in KEY_TO_TOOL:
                return KEY_TO_TOOL[key], 1.0
            if predicted_tool != ToolClass.WHITE:
                return predicted_tool, confidence

    def cleanup(self) -> None:
        if self.cap:
            self.cap.release()
        if self.show_preview:
            cv2.destroyAllWindows()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ToolTally camera detection preview.")
    parser.add_argument("--camera-index", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable OpenCV preview window.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = CameraDetectionEngine(
        camera_index=args.camera_index,
        show_preview=not args.no_preview,
    )
    print("Press q to quit. Press 0/1/2/3 to emit white/plier/screwdriver/wrench.")
    try:
        while True:
            tool, conf = engine.next_tool_event()
            print(f"Detected: {tool.value} ({conf:.2f})")
    except KeyboardInterrupt:
        pass
    finally:
        engine.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

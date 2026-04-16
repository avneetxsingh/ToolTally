from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np
from picamera2 import Picamera2

from src.models import ToolClass, tool_from_label

MODEL_PATH = Path("best.onnx")
IMG_SIZE = 320
CLASS_NAMES = ["pliers", "screwdriver", "white", "wrench"]


class CameraDetectionEngine:
    def __init__(
        self,
        camera_index: int = 0,
        show_preview: bool = True,
        model_path: str = str(MODEL_PATH),
    ) -> None:
        # Picamera2 doesn't use a camera index, but we keep this argument
        # for compatibility with the detection provider interface.
        self.camera_index = camera_index
        self.show_preview = show_preview
        self.has_display = os.environ.get("DISPLAY") is not None

        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"format": "RGB888", "size": (640, 480)}
        )
        self.picam2.configure(config)
        self.picam2.start()

        time.sleep(3)
        self._configure_camera_controls()
        time.sleep(2)

    def _configure_camera_controls(self) -> None:
        try:
            self.picam2.set_controls(
                {
                    "AeEnable": True,
                    "AwbEnable": True,
                    "Brightness": 0.1,
                    "Contrast": 1.2,
                    "Sharpness": 1.5,
                    "AfMode": 2,
                    "AfSpeed": 1,
                }
            )
            print("Autofocus enabled.")
        except Exception as exc:
            print(f"Autofocus not supported on this module: {exc}")
            self.picam2.set_controls(
                {
                    "AeEnable": True,
                    "AwbEnable": True,
                    "Brightness": 0.1,
                    "Contrast": 1.2,
                    "Sharpness": 1.5,
                }
            )

    @staticmethod
    def _postprocess_cls(preds: np.ndarray) -> Tuple[str, float]:
        outputs = np.squeeze(np.array(preds))
        exp_scores = np.exp(outputs - np.max(outputs))
        probs = exp_scores / np.sum(exp_scores)
        class_id = int(np.argmax(probs))
        confidence = float(probs[class_id])
        label = CLASS_NAMES[class_id]
        return label, confidence

    def next_tool_event(self) -> Tuple[ToolClass, float]:
        frame_rgb = self.picam2.capture_array()
        h, w = frame_rgb.shape[:2]

        size = min(h, w)
        x_off = (w - size) // 2
        y_off = (h - size) // 2
        square_img = frame_rgb[y_off : y_off + size, x_off : x_off + size]

        blob = cv2.dnn.blobFromImage(
            square_img,
            scalefactor=1 / 255.0,
            size=(IMG_SIZE, IMG_SIZE),
            swapRB=True,
            crop=False,
        )

        self.net.setInput(blob)
        start_time = time.time()
        preds = self.net.forward()
        inference_ms = (time.time() - start_time) * 1000

        label, confidence = self._postprocess_cls(preds)
        tool = tool_from_label(label)
        if tool is None:
            raise ValueError(f"Unknown class label from model: {label}")

        print(f"{label.upper():12s}  conf={confidence:.3f}  ({int(inference_ms)}ms)")

        if self.show_preview and self.has_display:
            self._render_preview(square_img, label, confidence, inference_ms)

        return tool, confidence

    def _render_preview(
        self,
        square_img: np.ndarray,
        label: str,
        confidence: float,
        inference_ms: float,
    ) -> None:
        display_frame = cv2.cvtColor(square_img, cv2.COLOR_RGB2BGR)
        color = (0, 255, 0) if label != "white" else (0, 0, 255)
        cv2.rectangle(display_frame, (0, 0), (640, 50), (0, 0, 0), -1)
        cv2.putText(
            display_frame,
            f"{label.upper()}  {confidence:.2f}  ({int(inference_ms)}ms)",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
        )
        cv2.imshow("Smart Toolbox AI", display_frame)
        cv2.waitKey(1)

    def cleanup(self) -> None:
        self.picam2.stop()
        if self.has_display:
            cv2.destroyAllWindows()

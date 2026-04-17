# ── camera_detector.py ───────────────────────────────────────────────
# Background thread that streams MJPEG from `rpicam-vid` and runs
# cv2.dnn ONNX classification on every decoded frame.
#
# Same approach as your high_res_classification.py but without picamera2,
# so it plays nicely alongside the Tkinter UI on the Pi.
#
# Public API:
#     CameraDetector()
#     .start()          — spawn the capture+inference thread
#     .stop()           — request shutdown (joins rpicam-vid process)
#     .get_latest()     — (frame_bgr, label, confidence)
#     .get_top_detection() — (label, confidence)
#     .available        — True once we've decoded at least one frame
# ─────────────────────────────────────────────────────────────────────

import cv2
import time
import subprocess
import threading
import numpy as np

from config import (MODEL_PATH, CLASS_NAMES, EMPTY_CLASS,
                    FRAME_WIDTH, FRAME_HEIGHT,
                    FRAMERATE, IMG_SIZE,
                    VERBOSE_LOGS)


def _log(msg):
    if VERBOSE_LOGS:
        print(f"[CAM] {msg}")


def _softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()


def _classify(net, frame_bgr):
    """
    Center-crop to square, run cv2.dnn classification.
    Returns (label, confidence, square_crop).
    """
    h, w = frame_bgr.shape[:2]
    size  = min(h, w)
    x_off = (w - size) // 2
    y_off = (h - size) // 2
    square = frame_bgr[y_off:y_off + size, x_off:x_off + size]

    # rpicam-vid MJPEG → cv2.imdecode gives BGR, so swapRB=False.
    blob = cv2.dnn.blobFromImage(
        square,
        scalefactor=1 / 255.0,
        size=(IMG_SIZE, IMG_SIZE),
        swapRB=False,
        crop=False,
    )
    net.setInput(blob)
    preds  = net.forward()
    scores = _softmax(np.squeeze(np.array(preds)))
    cls_id = int(np.argmax(scores))
    conf   = float(scores[cls_id])
    label  = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else "unknown"
    return label, conf, square


# ═══════════════════════════════════════════════════════════════════
#  CameraDetector
# ═══════════════════════════════════════════════════════════════════
class CameraDetector:
    def __init__(self):
        self._lock          = threading.Lock()
        self._running       = False
        self._thread        = None
        self._proc          = None

        self._latest_frame  = None
        self._latest_label  = EMPTY_CLASS
        self._latest_conf   = 0.0
        self._latest_square = None
        self.available      = False

        self._net = cv2.dnn.readNetFromONNX(MODEL_PATH)
        self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        _log(f"ONNX model loaded from {MODEL_PATH}")

    # ── Lifecycle ────────────────────────────────────────────────
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ── Accessors ────────────────────────────────────────────────
    def get_latest(self):
        with self._lock:
            return self._latest_frame, self._latest_label, self._latest_conf

    def get_top_detection(self):
        with self._lock:
            return self._latest_label, self._latest_conf

    # ── Camera pipe ──────────────────────────────────────────────
    def _open_camera(self):
        cmd = [
            "rpicam-vid",
            "--width",     str(FRAME_WIDTH),
            "--height",    str(FRAME_HEIGHT),
            "--framerate", str(FRAMERATE),
            "--codec",     "mjpeg",
            "--output",    "-",
            "--timeout",   "0",
            "--inline",
            "--nopreview",
            "-n",
        ]
        _log(f"spawning: {' '.join(cmd)}")
        return subprocess.Popen(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)

    def _loop(self):
        try:
            self._proc = self._open_camera()
        except FileNotFoundError:
            _log("ERROR: rpicam-vid not found. Is it installed on this Pi?")
            self._running = False
            return
        except Exception as e:
            _log(f"ERROR spawning rpicam-vid: {e}")
            self._running = False
            return

        buf = b""
        time.sleep(2)  # camera warm-up

        while self._running:
            try:
                chunk = self._proc.stdout.read(4096)
            except Exception as e:
                _log(f"stdout read failed: {e}")
                break

            if not chunk:
                # rpicam-vid exited — bail.
                if self._proc.poll() is not None:
                    _log("rpicam-vid exited unexpectedly")
                    break
                time.sleep(0.01)
                continue

            buf += chunk

            # Find a complete JPEG between the SOI/EOI markers.
            start = buf.find(b"\xff\xd8")
            if start == -1:
                buf = b""
                continue
            end = buf.find(b"\xff\xd9", start + 2)
            if end == -1:
                # incomplete frame; keep buffering
                continue

            jpg = buf[start:end + 2]
            buf = buf[end + 2:]

            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8),
                                 cv2.IMREAD_COLOR)
            if frame is None:
                continue

            try:
                label, conf, square = _classify(self._net, frame)
            except Exception as e:
                _log(f"inference error: {e}")
                continue

            with self._lock:
                self._latest_frame  = frame
                self._latest_label  = label
                self._latest_conf   = conf
                self._latest_square = square
                self.available      = True

        _log("capture loop exiting")
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

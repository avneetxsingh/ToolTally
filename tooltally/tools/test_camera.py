#!/usr/bin/env python3
# ── tools/test_camera.py ─────────────────────────────────────────────
# Headless sanity check — prints the model's top detection once per
# second for ~15 seconds. Use this to confirm rpicam-vid + ONNX work
# before starting the full UI.
#
# Run from the project root:
#     python3 tools/test_camera.py
# ─────────────────────────────────────────────────────────────────────

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camera_detector import CameraDetector


def main():
    cam = CameraDetector()
    cam.start()

    print("Waiting for first frame…")
    for _ in range(30):
        if cam.available:
            break
        time.sleep(0.5)
    if not cam.available:
        print("ERROR: no frames received from rpicam-vid.")
        cam.stop()
        return

    print("Streaming detections (Ctrl-C to stop):")
    try:
        for _ in range(15):
            label, conf = cam.get_top_detection()
            print(f"  {label.upper():12s}  conf={conf:.3f}")
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()


if __name__ == "__main__":
    main()

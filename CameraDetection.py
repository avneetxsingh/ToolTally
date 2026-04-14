import cv2
import numpy as np
import time
from picamera2 import Picamera2
import os

MODEL_PATH = "best.onnx"
IMG_SIZE = 320
CLASS_NAMES = ["pliers", "screwdriver", "white", "wrench"]

net = cv2.dnn.readNetFromONNX(MODEL_PATH)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"format": 'RGB888', "size": (640, 480)})
picam2.configure(config)
picam2.start()

time.sleep(3)
try:
    picam2.set_controls({
        "AeEnable": True,
        "AwbEnable": True,
        "Brightness": 0.1,
        "Contrast": 1.2,
        "Sharpness": 1.5,
        "AfMode": 2,        # 2 = continuous autofocus
        "AfSpeed": 1,       # 1 = fast
    })
    print("Autofocus enabled.")
except Exception as e:
    # Some Pi camera modules don't support autofocus (e.g. IMX219)
    # IMX708 (Camera Module 3) does support it
    print(f"Autofocus not supported on this module: {e}")
    picam2.set_controls({
        "AeEnable": True,
        "AwbEnable": True,
        "Brightness": 0.1,
        "Contrast": 1.2,
        "Sharpness": 1.5,
    })
time.sleep(2)

HAS_DISPLAY = os.environ.get("DISPLAY") is not None

def postprocess_cls(preds):
    outputs = np.squeeze(np.array(preds))
    exp_scores = np.exp(outputs - np.max(outputs))
    probs = exp_scores / np.sum(exp_scores)
    class_id = int(np.argmax(probs))
    conf = float(probs[class_id])
    label = CLASS_NAMES[class_id]
    return label, conf

try:
    while True:
        frame_rgb = picam2.capture_array()
        h, w = frame_rgb.shape[:2]

        size = min(h, w)
        x_off = (w - size) // 2
        y_off = (h - size) // 2
        square_img = frame_rgb[y_off:y_off+size, x_off:x_off+size]

        blob = cv2.dnn.blobFromImage(
            square_img,
            scalefactor=1/255.0,
            size=(IMG_SIZE, IMG_SIZE),
            swapRB=True,
            crop=False
        )

        net.setInput(blob)
        start_time = time.time()
        preds = net.forward()
        inference_ms = (time.time() - start_time) * 1000

        label, conf = postprocess_cls(preds)

        print(f"{label.upper():12s}  conf={conf:.3f}  ({int(inference_ms)}ms)")

        if HAS_DISPLAY:
            display_frame = cv2.cvtColor(square_img, cv2.COLOR_RGB2BGR)
            color = (0, 255, 0) if label != "white" else (0, 0, 255)
            cv2.rectangle(display_frame, (0, 0), (640, 50), (0, 0, 0), -1)
            cv2.putText(display_frame,
                        f"{label.upper()}  {conf:.2f}  ({int(inference_ms)}ms)",
                        (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            cv2.imshow("Smart Toolbox AI", display_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                cv2.imwrite("debug.jpg", cv2.cvtColor(square_img, cv2.COLOR_RGB2BGR))
                print("Saved debug.jpg")

except KeyboardInterrupt:
    print("\nShutting down...")
finally:
    picam2.stop()
    if HAS_DISPLAY:
        cv2.destroyAllWindows()
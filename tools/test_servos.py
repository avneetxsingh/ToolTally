#!/usr/bin/env python3
# ── tools/test_servos.py ─────────────────────────────────────────────
# Exercise every flap + the slide servo, one at a time.
#
# Run from the project root:
#     python3 tools/test_servos.py
# ─────────────────────────────────────────────────────────────────────

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servo_controller import ServoController
from config import SERVO_CHANNELS, SLIDE_CHANNEL


def main():
    sc = ServoController()
    print(f"Available (real hardware): {sc.available}")
    print(f"Flap channels: {SERVO_CHANNELS}")
    print(f"Slide channel: {SLIDE_CHANNEL}\n")

    try:
        for tool in SERVO_CHANNELS:
            print(f"── {tool} (ch {SERVO_CHANNELS[tool]}) ──")
            sc.open_flap(tool, auto_close=False)
            time.sleep(1.5)
            sc.close_flap(tool)
            time.sleep(1.0)

        print("── slide (ch 8) ──")
        sc.run_slide()

        print("\nDone.")
    finally:
        sc.cleanup()


if __name__ == "__main__":
    main()

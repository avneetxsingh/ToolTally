#!/usr/bin/env python3
# ── tools/test_workflow.py ───────────────────────────────────────────
# Simulate a full deposit choreography without the UI.
#
# Usage:
#     python3 tools/test_workflow.py            # defaults to "wrench"
#     python3 tools/test_workflow.py pliers
# ─────────────────────────────────────────────────────────────────────

import sys, os, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servo_controller   import ServoController
from workflow_controller import WorkflowController
from config import SERVO_CHANNELS


def main():
    tool = sys.argv[1] if len(sys.argv) > 1 else "wrench"
    if tool not in SERVO_CHANNELS:
        print(f"Unknown tool '{tool}'. Valid: {list(SERVO_CHANNELS)}")
        sys.exit(1)

    sc  = ServoController()
    wf  = WorkflowController(sc)  # no ui_scheduler — callbacks run on worker

    done = threading.Event()
    def cb(success, error):
        print(f"\n>>> DEPOSIT FINISHED  success={success}  error={error!r}")
        done.set()

    print(f"Running deposit sequence for '{tool}'…")
    wf.run_deposit_sequence(tool, confidence=0.95, on_done=cb)

    done.wait(timeout=30)
    sc.cleanup()


if __name__ == "__main__":
    main()

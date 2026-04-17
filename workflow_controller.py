# ── workflow_controller.py ───────────────────────────────────────────
# Sequences the multi-step hardware choreography of ToolTally.
#
# Why this exists:
#   The UI must never block — but the deposit sequence (open flap →
#   run slide → wait → close flap) takes several seconds. This module
#   runs that sequence on a background thread and calls a callback on
#   the UI thread when done, so the Tkinter event loop keeps ticking.
#
# Deposit choreography:
#     1. Open flap for detected tool  (no auto-close — we'll close it)
#     2. Wait FLAP_OPEN_SETTLE_SECS    (let the flap finish moving)
#     3. Run slide servo (ch 8):
#           move to SLIDE_ACTIVE_ANGLE, hold SLIDE_ACTIVE_SECS, return
#     4. Wait SLIDE_RETURN_SETTLE      (let the tool settle in the bin)
#     5. Close flap
#     6. Fire on_done(success, error_msg)  via ui_scheduler
# ─────────────────────────────────────────────────────────────────────

import threading
import time
import traceback

from config import (FLAP_OPEN_SETTLE_SECS,
                    SLIDE_RETURN_SETTLE,
                    VERBOSE_LOGS)


def _log(msg):
    if VERBOSE_LOGS:
        print(f"[WORKFLOW] {msg}")


class WorkflowController:
    """
    Coordinates ServoController + timing for high-level actions.

    Parameters
    ----------
    servo : ServoController
        Already-initialised servo controller.
    ui_scheduler : callable(fn) -> None, optional
        Function that schedules `fn` on the UI thread. For Tkinter pass
        `root.after` wrapped like `lambda fn: root.after(0, fn)`. If None,
        callbacks just fire on the worker thread (fine for headless tests).
    """

    def __init__(self, servo, ui_scheduler=None):
        self.servo = servo
        self._ui   = ui_scheduler or (lambda fn: fn())
        self._busy_lock = threading.Lock()
        self._busy      = False

    @property
    def busy(self):
        return self._busy

    # ═══════════════════════════════════════════════════════════
    #  DEPOSIT — full choreography
    # ═══════════════════════════════════════════════════════════
    def run_deposit_sequence(self, tool, confidence, on_done=None):
        """
        Run the deposit choreography for `tool` on a background thread.

        on_done(success: bool, error: str) is invoked via the UI scheduler
        when the sequence finishes (whether by success or by exception).
        """
        if not self._try_acquire():
            _log("busy — rejecting deposit request")
            self._fire(on_done, False, "System busy, try again in a moment.")
            return

        t = threading.Thread(
            target=self._deposit_worker,
            args=(tool, confidence, on_done),
            daemon=True,
        )
        t.start()

    def _deposit_worker(self, tool, confidence, on_done):
        success = False
        error   = ""
        try:
            _log(f"DEPOSIT start  tool={tool}  conf={confidence:.2f}")

            # 1. Open the flap (no auto-close; we close it ourselves).
            if not self.servo.open_flap(tool, auto_close=False):
                raise RuntimeError(f"Could not open flap for {tool}")

            # 2. Let it settle.
            time.sleep(FLAP_OPEN_SETTLE_SECS)

            # 3. Run the slide (blocking — this IS the "tool goes down" step).
            self.servo.run_slide()

            # 4. Let the tool finish settling in its bin.
            time.sleep(SLIDE_RETURN_SETTLE)

            # 5. Close the flap.
            self.servo.close_flap(tool)

            success = True
            _log(f"DEPOSIT done   tool={tool}")
        except Exception as e:
            error = str(e)
            _log(f"DEPOSIT FAILED  {e}")
            traceback.print_exc()
            # Defensive: try to close the flap so we don't leave hardware open.
            try:
                self.servo.close_flap(tool)
            except Exception:
                pass
        finally:
            self._release()
            self._fire(on_done, success, error)

    # ═══════════════════════════════════════════════════════════
    #  TAKE — trivial, included here for symmetry
    # ═══════════════════════════════════════════════════════════
    def run_take_sequence(self, tool, on_done=None):
        """
        Open the flap and let its internal auto-close timer handle the rest.
        This is fire-and-forget, so we don't need a worker thread — but we
        still route the callback through the UI scheduler for consistency.
        """
        try:
            ok = self.servo.open_flap(tool, auto_close=True)
            err = "" if ok else f"No servo mapped for '{tool}'"
            _log(f"TAKE   tool={tool}  ok={ok}")
            self._fire(on_done, ok, err)
        except Exception as e:
            _log(f"TAKE FAILED {e}")
            self._fire(on_done, False, str(e))

    # ═══════════════════════════════════════════════════════════
    #  Internals
    # ═══════════════════════════════════════════════════════════
    def _try_acquire(self):
        with self._busy_lock:
            if self._busy:
                return False
            self._busy = True
            return True

    def _release(self):
        with self._busy_lock:
            self._busy = False

    def _fire(self, cb, success, error):
        if cb is None:
            return
        try:
            self._ui(lambda: cb(success, error))
        except Exception as e:
            _log(f"callback scheduling failed: {e}")

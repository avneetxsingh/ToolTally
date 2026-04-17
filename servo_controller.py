# ── servo_controller.py ──────────────────────────────────────────────
# PCA9685-based servo controller for ToolTally.
#
# Hardware: Adafruit-style PCA9685 16-channel PWM driver over I²C.
# Library:  adafruit-circuitpython-pca9685 + adafruit-circuitpython-motor
#           (same stack as servo_test.py)
#
# Channel layout (from config.SERVO_CHANNELS and config.SLIDE_CHANNEL):
#     pliers flap      → ch 0
#     screwdriver flap → ch 12
#     wrench flap      → ch 15
#     slide mechanism  → ch 8
#
# Public API:
#     ServoController()
#     .open_flap(tool, auto_close=True)      → bool
#     .close_flap(tool)
#     .run_slide()                           → bool      (channel 8 sweep)
#     .close_all_flaps()
#     .cleanup()
#     .available                             → bool property
#
# Backward-compat shims (so main_ui_2 does not break mid-refactor):
#     .open(tool, auto_close=True)           → same as open_flap
#     .close(tool)                           → same as close_flap
#
# If the PCA9685 or its libraries are not available and
# config.ALLOW_SIMULATION is True, every method becomes a logged no-op
# so you can develop the UI on a laptop.
# ─────────────────────────────────────────────────────────────────────

import time
import threading

from config import (SERVO_CHANNELS, SLIDE_CHANNEL, PCA_FREQUENCY,
                    FLAP_CLOSED_ANGLE, FLAP_OPEN_ANGLE,
                    FLAP_ANGLE_OVERRIDES,
                    SLIDE_REST_ANGLE, SLIDE_ACTIVE_ANGLE,
                    SLIDE_ACTIVE_SECS,
                    FLAP_HOLD_OPEN_SECS,
                    ALLOW_SIMULATION, VERBOSE_LOGS)


def _log(msg):
    if VERBOSE_LOGS:
        print(f"[SERVO] {msg}")


# ── Optional hardware imports ──────────────────────────────────────
_HW_OK = False
_HW_IMPORT_ERROR = None
try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    from adafruit_motor import servo as adafruit_servo
    _HW_OK = True
except Exception as e:                # ImportError on laptops, RuntimeError on bad I²C
    _HW_IMPORT_ERROR = e
    _log(f"Hardware libs unavailable ({e}). Will try simulation mode.")


# ═══════════════════════════════════════════════════════════════════
#  ServoController
# ═══════════════════════════════════════════════════════════════════
class ServoController:
    """
    Owns the PCA9685, all flap servos, and the slide servo.

    Thread-safe enough for our use: a single _lock serialises writes so
    the UI thread and the workflow thread never clobber each other.
    """

    def __init__(self):
        self._lock       = threading.Lock()
        self._timers     = {}         # tool_name → Timer (for TAKE auto-close)
        self._pca        = None
        self._flap_servos  = {}       # tool_name → adafruit servo.Servo
        self._slide_servo  = None
        self.available   = False      # True iff we talk to real hardware
        self._init_hardware()

    # ── Hardware init ────────────────────────────────────────────
    def _init_hardware(self):
        if not _HW_OK:
            if not ALLOW_SIMULATION:
                raise RuntimeError(
                    f"Servo hardware libs not available: {_HW_IMPORT_ERROR}"
                )
            _log("SIMULATION mode — no PCA9685 calls will be made.")
            return

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c)
            self._pca.frequency = PCA_FREQUENCY

            for tool, ch in SERVO_CHANNELS.items():
                self._flap_servos[tool] = adafruit_servo.Servo(self._pca.channels[ch])

            self._slide_servo = adafruit_servo.Servo(self._pca.channels[SLIDE_CHANNEL])

            # Move everything to its safe rest position.
            for tool in SERVO_CHANNELS:
                self._write_angle(self._flap_servos[tool], self._closed_angle(tool))
            self._write_angle(self._slide_servo, SLIDE_REST_ANGLE)

            self.available = True
            _log(f"PCA9685 ready @ {PCA_FREQUENCY} Hz. "
                 f"Flaps={list(SERVO_CHANNELS)}, slide=ch{SLIDE_CHANNEL}.")
        except Exception as e:
            _log(f"PCA9685 init failed: {e}")
            if not ALLOW_SIMULATION:
                raise
            self._pca = None
            self.available = False
            _log("Falling back to SIMULATION mode.")

    # ── Low-level helpers ────────────────────────────────────────
    def _open_angle(self, tool):
        override = FLAP_ANGLE_OVERRIDES.get(tool, {})
        return override.get("open", FLAP_OPEN_ANGLE)

    def _closed_angle(self, tool):
        override = FLAP_ANGLE_OVERRIDES.get(tool, {})
        return override.get("closed", FLAP_CLOSED_ANGLE)

    def _write_angle(self, servo_obj, angle):
        """Clamp and write an angle. Runs under the caller's lock."""
        angle = max(0, min(180, int(angle)))
        try:
            servo_obj.angle = angle
        except Exception as e:
            _log(f"angle write failed ({angle}°): {e}")

    # ═══════════════════════════════════════════════════════════
    #  Flap API
    # ═══════════════════════════════════════════════════════════
    def open_flap(self, tool, auto_close=True):
        """
        Open the flap for `tool`. If auto_close=True a background timer
        will close it after FLAP_HOLD_OPEN_SECS. If auto_close=False the
        caller is responsible for calling close_flap() later — this is
        what the deposit workflow uses so it can coordinate with the slide.
        """
        if tool not in SERVO_CHANNELS:
            _log(f"open_flap: unknown tool '{tool}'")
            return False

        with self._lock:
            # Cancel any previous auto-close timer for this tool.
            t = self._timers.pop(tool, None)
            if t:
                t.cancel()

            angle = self._open_angle(tool)
            _log(f"open flap  '{tool}'  (ch{SERVO_CHANNELS[tool]}, {angle}°)")

            if self.available:
                self._write_angle(self._flap_servos[tool], angle)

            if auto_close:
                timer = threading.Timer(
                    FLAP_HOLD_OPEN_SECS, self.close_flap, args=[tool]
                )
                timer.daemon = True
                timer.start()
                self._timers[tool] = timer

        return True

    def close_flap(self, tool):
        """Close the flap for `tool`. Idempotent."""
        if tool not in SERVO_CHANNELS:
            return False

        with self._lock:
            t = self._timers.pop(tool, None)
            if t:
                t.cancel()

            angle = self._closed_angle(tool)
            _log(f"close flap '{tool}' (ch{SERVO_CHANNELS[tool]}, {angle}°)")

            if self.available:
                self._write_angle(self._flap_servos[tool], angle)

        return True

    def close_all_flaps(self):
        for tool in SERVO_CHANNELS:
            self.close_flap(tool)

    # ═══════════════════════════════════════════════════════════
    #  Slide API (channel 8)
    # ═══════════════════════════════════════════════════════════
    def run_slide(self, active_secs=None):
        """
        Sweep the slide servo to SLIDE_ACTIVE_ANGLE, hold for
        `active_secs` seconds, then return to SLIDE_REST_ANGLE.

        BLOCKING. Call from the workflow thread, not the UI thread.
        """
        if active_secs is None:
            active_secs = SLIDE_ACTIVE_SECS

        _log(f"slide: ch{SLIDE_CHANNEL} → {SLIDE_ACTIVE_ANGLE}° "
             f"(hold {active_secs}s) → {SLIDE_REST_ANGLE}°")

        with self._lock:
            if self.available:
                self._write_angle(self._slide_servo, SLIDE_ACTIVE_ANGLE)

        # Hold outside the lock so we don't block flap commands.
        time.sleep(active_secs)

        with self._lock:
            if self.available:
                self._write_angle(self._slide_servo, SLIDE_REST_ANGLE)

        _log("slide: return complete")
        return True

    # ═══════════════════════════════════════════════════════════
    #  Backward-compat shims for main_ui_2.py
    # ═══════════════════════════════════════════════════════════
    def open(self, tool, auto_close=True):
        return self.open_flap(tool, auto_close=auto_close)

    def close(self, tool):
        return self.close_flap(tool)

    def close_all(self):
        self.close_all_flaps()

    # ═══════════════════════════════════════════════════════════
    #  Shutdown
    # ═══════════════════════════════════════════════════════════
    def cleanup(self):
        """Close every flap, park the slide, and release PWM."""
        _log("cleanup()")
        # Cancel any pending auto-close timers.
        with self._lock:
            for t in list(self._timers.values()):
                t.cancel()
            self._timers.clear()

        self.close_all_flaps()
        time.sleep(0.3)

        with self._lock:
            if self.available and self._pca is not None:
                try:
                    self._write_angle(self._slide_servo, SLIDE_REST_ANGLE)
                    # Disable PWM on every channel we used.
                    for ch in list(SERVO_CHANNELS.values()) + [SLIDE_CHANNEL]:
                        self._pca.channels[ch].duty_cycle = 0
                    self._pca.deinit()
                except Exception as e:
                    _log(f"cleanup error: {e}")


# ═══════════════════════════════════════════════════════════════════
#  Module-level convenience (for quick REPL tests)
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    sc = ServoController()
    print("Available:", sc.available)
    for tool in SERVO_CHANNELS:
        print(f"  open  {tool}"); sc.open_flap(tool, auto_close=False); time.sleep(1)
        print(f"  close {tool}"); sc.close_flap(tool);                   time.sleep(1)
    print("  slide"); sc.run_slide()
    sc.cleanup()

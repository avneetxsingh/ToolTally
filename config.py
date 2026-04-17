# ── config.py ────────────────────────────────────────────────────────
# All tunable constants for the ToolTally system.
# Edit these values before running on your Pi.
# ─────────────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════
#  SUPABASE
# ═══════════════════════════════════════════════════════════════════
# From your Supabase project → Settings → API
SUPABASE_URL = "https://xifcjijtpjrmlyxvtfoy.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhpZmNqaWp0cGpybWx5eHZ0Zm95Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3NTE3NjYsImV4cCI6MjA5MTMyNzc2Nn0.wsvL2uI07UagqElyhxewnH2xKkTSMwMvNhTjEj7wMIM"
SUPABASE_USERS_TABLE = "users"
SUPABASE_LOGS_TABLE  = "logs"

# Local offline-first database path.
LOCAL_DB_PATH = "data/tooltally.db"

# Background sync tuning.
SYNC_ENABLED = True
SYNC_INTERVAL_SECS = 5
SYNC_MAX_RETRIES = 20


# ═══════════════════════════════════════════════════════════════════
#  MODEL / CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════
MODEL_PATH   = "best.onnx"

# Class names — must match training order exactly.
# "white" = empty compartment / no tool present.
CLASS_NAMES  = ["pliers", "screwdriver", "white", "wrench"]
EMPTY_CLASS  = "white"

# Minimum confidence to accept a detection in the UI.
CONFIDENCE   = 0.60

# Require N consecutive stable frames of the same class before the
# Confirm button enables, to avoid flicker.
STABLE_FRAMES = 3


# ═══════════════════════════════════════════════════════════════════
#  CAMERA
# ═══════════════════════════════════════════════════════════════════
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480
FRAMERATE    = 15
IMG_SIZE     = 320        # model input resolution (matches training)


# ═══════════════════════════════════════════════════════════════════
#  SERVOS — PCA9685
# ═══════════════════════════════════════════════════════════════════
# The PCA9685 is an I²C PWM driver. Each servo plugs into a channel
# (0–15) on the board, NOT a Pi GPIO pin.
#
# Wiring (as defined by servo_test.py):
#   Pliers flap       → PCA channel 0
#   Screwdriver flap  → PCA channel 12
#   Wrench flap       → PCA channel 15
#   Slide mechanism   → PCA channel 8     (shared across all tools)
# ─────────────────────────────────────────────────────────────────────

# Map each tool to its flap servo channel.
SERVO_CHANNELS = {
    "pliers":      0,
    "screwdriver": 12,
    "wrench":      15,
}

# The slide servo — runs AFTER a flap opens to send the tool down the chute.
SLIDE_CHANNEL  = 8

# PCA9685 PWM frequency (50 Hz is standard for hobby servos).
PCA_FREQUENCY  = 50

# ── Flap angles ─────────────────────────────────────────────────────
# Adjust these on real hardware; different flaps may need different angles.
FLAP_CLOSED_ANGLE = 0
FLAP_OPEN_ANGLE   = 90

# Per-tool overrides — leave empty to use the defaults above, or add
# entries like: "wrench": {"open": 100, "closed": 5}
FLAP_ANGLE_OVERRIDES = {
    # "pliers":      {"open": 90, "closed": 0},
    # "screwdriver": {"open": 85, "closed": 5},
    # "wrench":      {"open": 95, "closed": 0},
}

# ── Slide angles ────────────────────────────────────────────────────
SLIDE_REST_ANGLE   = 0      # default/resting position
SLIDE_ACTIVE_ANGLE = 180    # swept position that pushes the tool

# ── Timings (seconds) ───────────────────────────────────────────────
FLAP_OPEN_SETTLE_SECS  = 0.6   # wait after flap opens before slide moves
SLIDE_ACTIVE_SECS      = 2.0   # how long the slide stays in active position
SLIDE_RETURN_SETTLE    = 0.6   # wait after slide returns before flap closes
FLAP_HOLD_OPEN_SECS    = 5.0   # TAKE flow: how long the flap stays open

# When using admin "manual open", how long to hold before auto-close.
ADMIN_HOLD_OPEN_SECS   = 5.0


# ═══════════════════════════════════════════════════════════════════
#  UI
# ═══════════════════════════════════════════════════════════════════
SCREEN_W = 800
SCREEN_H = 480


# ═══════════════════════════════════════════════════════════════════
#  LOGGING / DEBUG
# ═══════════════════════════════════════════════════════════════════
# If True, servo_controller and workflow_controller will fall back to a
# fully simulated mode when hardware libraries or the PCA9685 are missing.
# Useful for developing the UI on a laptop without a Pi attached.
ALLOW_SIMULATION = True
VERBOSE_LOGS     = True

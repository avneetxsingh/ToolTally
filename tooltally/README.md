# ToolTally

A Raspberry Pi–based smart tool cabinet. The UI is a touchscreen Tkinter app; the camera is driven by `rpicam-vid`; tool classification uses a trained ONNX model via OpenCV DNN; and the servos are driven through a PCA9685 over I²C.

## What the system does

- **TAKE**: user logs in, taps the tool they want, the matching flap opens for 5 s, then auto-closes.
- **DEPOSIT**: user logs in, places a tool in front of the camera, the ONNX model classifies it, the user confirms, then:
  1. flap for that tool opens
  2. channel-8 slide servo sweeps to send the tool down the chute and returns
  3. flap closes
  4. action is logged to Supabase

## File layout

| File | Role |
|---|---|
| `main.py` | Entry point — just launches `main_ui_2.App` |
| `main_ui_2.py` | Tkinter UI (Login, Action, SelectTool, Deposit, Result, Admin pages) |
| `config.py` | All tunable constants — PCA channels, angles, timings, confidence thresholds |
| `servo_controller.py` | PCA9685 driver — flaps + slide servo |
| `camera_detector.py` | Background `rpicam-vid` MJPEG stream + cv2.dnn classification |
| `workflow_controller.py` | Sequences the deposit choreography on a worker thread |
| `database.py` | Supabase CRUD (users + logs), with in-memory fallback |
| `high_res_classification.py` | Standalone bench script (picamera2 + cv2.dnn) |
| `servo_test.py` | Original raw PCA9685 test |
| `tools/test_servos.py` | Cycles every flap + the slide |
| `tools/test_camera.py` | Prints the model's top detection for 15 s |
| `tools/test_workflow.py` | Runs a full deposit sequence without the UI |
| `requirements.txt` | Python deps |

## Tool → servo map

| Tool | PCA9685 channel |
|---|---|
| pliers | 0 |
| screwdriver | 12 |
| wrench | 15 |
| slide (shared) | **8** |

Change these in `config.SERVO_CHANNELS` / `config.SLIDE_CHANNEL` if your wiring differs.

## Setup on the Raspberry Pi

### 1. System packages
```bash
sudo apt update
sudo apt install -y python3-pip python3-tk rpicam-apps i2c-tools
sudo raspi-config         # → Interface Options → I²C → Enable
```

Verify the PCA9685 appears on the bus (default address `0x40`):
```bash
sudo i2cdetect -y 1
```

### 2. Python packages
```bash
cd tooltally
pip install -r requirements.txt
```

If `adafruit-blinka` complains, run `sudo pip install adafruit-blinka` — it needs some system-level hooks.

### 3. ONNX model
Put `best.onnx` next to `main.py` (or change `MODEL_PATH` in `config.py`).

### 4. Supabase tables
Run this once in the Supabase SQL editor:

```sql
create table if not exists users (
    id          bigserial primary key,
    user_id     text unique not null,
    name        text not null,
    role        text not null default 'user',
    created_at  timestamptz default now()
);

create table if not exists logs (
    id             bigserial primary key,
    user_db_id     bigint references users(id) on delete set null,
    user_name      text,
    tool           text,
    action         text,
    detected_tool  text,
    confidence     double precision,
    timestamp      timestamptz default now()
);

-- at least one admin:
insert into users (user_id, name, role) values ('9999', 'Admin', 'admin')
on conflict (user_id) do nothing;
```

## Running

Full system:
```bash
cd tooltally
python3 main.py
```
The UI opens fullscreen. Press `Esc` to exit fullscreen, or close the window.

Bench tests (order I suggest):
```bash
python3 tools/test_servos.py      # does every flap move? does ch 8 sweep?
python3 tools/test_camera.py      # is the model classifying live frames?
python3 tools/test_workflow.py wrench   # does the full sequence work?
python3 main.py                   # full app
```

## Behaviour in simulation mode

If the PCA9685 or its I²C bus isn't available **and** `config.ALLOW_SIMULATION` is `True`, the `ServoController` logs every movement instead of driving hardware, so you can develop the UI on a laptop. The camera still requires `rpicam-vid`, so the Deposit page will just sit on "Waiting for tool…" off-Pi — that's expected.

## Things to adjust on real hardware

- **`FLAP_OPEN_ANGLE` / `FLAP_CLOSED_ANGLE`**: different flap linkages need different angles. If a single pair doesn't work for all three, use `FLAP_ANGLE_OVERRIDES` in `config.py`.
- **`SLIDE_ACTIVE_ANGLE` / `SLIDE_REST_ANGLE` / `SLIDE_ACTIVE_SECS`**: tune until one sweep reliably ejects a tool.
- **`FLAP_OPEN_SETTLE_SECS` / `SLIDE_RETURN_SETTLE`**: raise these if your flap or chute needs more time.
- **`CONFIDENCE`**: raise to 0.75 if you see false-positives; lower to 0.5 if good tools are being rejected.
- **`STABLE_FRAMES`**: the number of consecutive stable frames before Confirm lights up. 3 is conservative; drop to 2 if the UI feels sluggish.

## Troubleshooting

- **"ONNX model load failed"** → `best.onnx` not in the working directory, or trained with an op cv2.dnn can't import. Re-export from the training pipeline targeting opset 12.
- **"rpicam-vid not found"** → install `rpicam-apps` (or `libcamera-apps` on older Pi OS).
- **"I²C bus permission denied"** → add your user to the `i2c` group: `sudo usermod -aG i2c $USER`, then log out and back in.
- **PCA9685 not detected** → check wiring (SDA → GPIO 2, SCL → GPIO 3, VCC → 3V3, GND → GND). Servo power should be on a separate 5–6 V supply, **never** the Pi's 5 V rail.
- **UI freezes during deposit** → it shouldn't — the sequence runs on a worker thread. If you see this, check the console for a traceback from `workflow_controller`.

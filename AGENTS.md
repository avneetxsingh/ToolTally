# Repository Guidelines

## Project Structure & Module Organization
ToolTally is a Raspberry Pi Python application that combines UI, camera inference, and servo actuation.

- `main.py`: app entrypoint (launches Tkinter UI).
- `main_ui_2.py`: primary touchscreen UI flow.
- `camera_detector.py`, `high_res_classification.py`: camera + ONNX classification logic.
- `servo_controller.py`, `workflow_controller.py`: servo control and deposit choreography.
- `database.py`: Supabase reads/writes with fallback behavior.
- `config.py`: central constants for model path, channels, timings, thresholds.
- `tools/`: bench scripts (`test_servos.py`, `test_camera.py`, `test_workflow.py`).
- `best.onnx`: model artifact expected at repo root.

Keep modules single-purpose. If you add a new feature, prefer extending the existing domain module (camera/servo/workflow/db/ui) rather than adding cross-cutting logic to `main.py`.

## Architecture Overview
High-level runtime flow:

1. `main.py` creates `App` from `main_ui_2.py`.
2. `App` initializes hardware-facing services (camera detector, servo controller, workflow controller).
3. TAKE flow opens/closes a specific flap and logs the action.
4. DEPOSIT flow classifies a tool, asks for confirmation, runs workflow choreography, then logs to DB.

Threading note: deposit choreography runs in worker-thread style code in `workflow_controller.py`; avoid blocking Tkinter UI callbacks with long-running I/O or sleep loops.

## Build, Test, and Development Commands
- `python3 -m pip install -r requirements.txt`: install Python dependencies.
- `python3 main.py`: run the full UI application.
- `python3 tools/test_servos.py`: verify flap and slide movement by channel.
- `python3 tools/test_camera.py`: validate live model predictions from camera feed.
- `python3 tools/test_workflow.py wrench`: test full deposit sequence without UI.
- `python3 servo_test.py`: low-level PCA9685 smoke check.

Run hardware-facing commands on Pi with I2C enabled. On non-Pi systems, simulation behavior depends on `ALLOW_SIMULATION` in `config.py`.

Recommended local verification order after hardware-related changes:

1. `python3 tools/test_servos.py`
2. `python3 tools/test_camera.py`
3. `python3 tools/test_workflow.py pliers`
4. `python3 main.py`

## Coding Style & Naming Conventions
- Follow existing Python style: 4-space indentation, snake_case for functions/variables, UPPER_CASE for config constants.
- Keep modules focused by hardware/domain responsibility (UI, camera, servo, workflow, DB).
- Prefer small, explicit functions and readable logging over compact one-liners.
- Keep tunables in `config.py` instead of hardcoding.

Naming patterns to keep consistent:

- test scripts: `tools/test_<feature>.py`
- controllers/services: `<domain>_controller.py` / `<domain>_detector.py`
- constants: `FLAP_OPEN_ANGLE`, `STABLE_FRAMES`

If you introduce new configuration values, add clear comments in `config.py` for units and expected range (example: seconds, angle degrees, confidence 0.0-1.0).

## Testing Guidelines
There is no formal `pytest` suite yet; testing is script-based and hardware-aware.

- Name new bench checks as `tools/test_<feature>.py`.
- Include direct CLI usage at the top of each test script.
- For hardware changes, validate in this order: servos -> camera -> workflow -> full app.

When adding logic that can be isolated from hardware (for example mapping or timing decisions), prefer extracting pure functions so they can be unit-tested later.

For UI behavior changes:

- document manual steps in your PR (screen, button press, expected status text);
- include screenshots or short recordings for changed pages/states.

## Commit & Pull Request Guidelines
Current history has short messages (for example, `Manual mode`, `Add files via upload`). Keep future commits concise, imperative, and more descriptive.

- Recommended format: `<scope>: <what changed>` (example: `workflow: add timeout guard`).
- One logical change per commit.
- PRs should include: summary, affected files/modules, hardware impact, manual test steps run, and screenshots/video for UI changes.

Good commit examples:

- `camera: debounce unstable classification labels`
- `servo: clamp flap angles before write`
- `ui: show retry hint on deposit timeout`

## Security & Configuration Tips
- Do not commit production secrets.
- For shared/deployed setups, move Supabase credentials out of `config.py` into environment variables.
- Verify `SERVO_CHANNELS`, angle limits, and timing constants before running on physical hardware.

Hardware safety checks before merging servo-related edits:

1. Confirm servo channel mapping matches wiring (`SERVO_CHANNELS`, `SLIDE_CHANNEL`).
2. Confirm angle limits do not bind mechanical linkages.
3. Confirm hold/open timings are safe for repeated cycles.
4. Run at least one end-to-end TAKE and DEPOSIT cycle on target hardware.

## Contributor Workflow
Use this lightweight flow for most changes:

1. Update code in the relevant module (`camera_detector.py`, `workflow_controller.py`, etc.).
2. Adjust `config.py` only when defaults must change.
3. Run the applicable `tools/test_*.py` scripts.
4. Run `python3 main.py` for final UI validation.
5. Submit PR with clear test evidence and hardware notes.

Avoid broad refactors mixed with behavior changes in the same PR; keep review scope small and verifiable.

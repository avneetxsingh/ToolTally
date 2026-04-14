# Repository Guidelines

## Product Scope
ToolTally is an AI-powered toolbox organizer for **Raspberry Pi 4 (Debian)**.
Current detection classes:
- `white`: no tool present (background class).
- `pliers` (model label; maps to plier flap/drawer)
- `screwdriver`
- `wrench`

Physical mapping:
- 3 flaps: flap1=plier, flap2=screwdriver, flap3=wrench.
- 3 sliding drawers: one drawer per tool type.
- Each drawer has a solenoid lock.

## Core Runtime Flow
1. Camera model detects tool class.
2. If class is `white`, do nothing.
3. If tool detected, open mapped flap for a controlled duration, then close.
4. Tool drops into mapped drawer path.
5. User enters last 4 digits of employee ID on touchscreen numpad.
6. UI shows allowed/requested tool drawer.
7. Unlock mapped solenoid for a fixed timeout, then relock.
8. Log all events (detect, flap open/close, unlock/relock, user ID, timestamps).

## Project Structure & Module Organization
- `main.py`: single system entrypoint (startup, bootstrap, runtime loop).
- `config/settings.yaml`: timing, hardware mode, GPIO pin map, runtime settings.
- `src/detection/`: detection provider interfaces/adapters.
- `src/hardware/`: GPIO drivers for flap actuators and solenoids.
- `src/control/`: timing/state machine (detection -> flap -> drawer lock flow).
- `src/ui/`: touchscreen UI and numpad flow.
- `src/data/`: database access and audit logging.
- `deploy/tooltally.service`: systemd unit for boot auto-start.
- `tests/`: unit and integration tests.

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`
- `python3 -m pip install -r requirements.txt`
- `python3 main.py --config config/settings.yaml` (run full system in `mock` mode)
- Set `detection.mode` in `config/settings.yaml` to `manual` or `camera`.
- `python3 -m pytest -q`
- Pi packages as needed: `sudo apt install -y libcamera-apps v4l-utils`
- In `raspberry_pi` mode, flap servos use `pigpio` (daemon must be running).

## Coding & Safety Standards
- Python, PEP 8, 4-space indentation, type hints for public APIs.
- Use deterministic state transitions; no blocking sleeps in UI thread.
- Hardware fail-safe default: flaps closed, solenoids locked on error/restart.
- Make timing configurable (env/config), not hardcoded.

## Database Guidance
Default to **SQLite on-device** for reliability/offline operation and simple deployment on Pi. Add cloud sync later only if remote reporting is required. Store employees (ID suffix hash/reference), tool events, drawer access events, and error logs.

## Commit & PR Guidelines
- Commit format: `type(scope): summary` (example: `feat(control): add flap timing state machine`).
- PRs must include: behavior summary, test evidence, hardware impact notes, and rollback/fail-safe notes.

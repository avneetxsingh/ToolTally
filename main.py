#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

from src.config import load_config
from src.detection.providers import CameraDetectionProvider, ManualInputDetectionProvider
from src.hardware.controller import MockHardwareController, RaspberryPiHardwareController
from src.models import ToolClass


def build_hardware(config):
    if config.hardware.mode == "raspberry_pi":
        return RaspberryPiHardwareController(
            flap_pins=config.hardware.flap_pins,
            solenoid_pins=config.hardware.solenoid_pins,
            active_low=config.hardware.active_low,
            servo_open_angle=config.hardware.servo_open_angle,
            servo_close_angle=config.hardware.servo_close_angle,
            servo_open_secs=config.timing.flap_open_seconds,
        )
    return MockHardwareController(
        flap_pins=config.hardware.flap_pins,
        solenoid_pins=config.hardware.solenoid_pins,
    )


def build_detector(config):
    if config.detection.mode == "camera":
        return CameraDetectionProvider(
            camera_index=config.detection.camera_index,
            show_preview=config.detection.show_preview,
        )
    return ManualInputDetectionProvider()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ToolTally minimal runtime: detect tool and open mapped flap"
    )
    parser.add_argument(
        "--config",
        default="config/settings.yaml",
        help="Path to app config file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    hardware = build_hardware(cfg)
    detector = build_detector(cfg)

    print("[SYS] Starting ToolTally minimal mode")
    print("[SYS] Flow: detection -> flap open -> flap close")

    try:
        hardware.initialize_safe_state()
        while True:
            event = detector.next_event()
            if event.tool == ToolClass.WHITE:
                continue

            print(f"[SYS] Detected: {event.tool.value} ({event.confidence:.2f})")
            hardware.open_flap(event.tool)
            time.sleep(cfg.timing.flap_open_seconds)
            hardware.close_all_flaps()
            time.sleep(cfg.timing.flap_settle_seconds)
    except KeyboardInterrupt:
        print("\n[SYS] Shutting down")
    except ValueError as exc:
        print(f"[WARN] {exc}")
    finally:
        if hasattr(detector, "cleanup"):
            detector.cleanup()
        hardware.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import time

from src.config import AppConfig
from src.data.database import Database
from src.detection.providers import DetectionProvider
from src.hardware.controller import HardwareController
from src.models import TOOL_CLASSES, ToolClass
from src.ui.console import ConsoleUI


class ToolTallyController:
    def __init__(
        self,
        config: AppConfig,
        db: Database,
        hardware: HardwareController,
        detector: DetectionProvider,
        ui: ConsoleUI,
    ) -> None:
        self.config = config
        self.db = db
        self.hardware = hardware
        self.detector = detector
        self.ui = ui
        self._last_detection_time = 0.0

    def bootstrap(self) -> None:
        self.db.seed_allowed_pins(self.config.runtime.allowed_pin_suffixes)
        self.hardware.initialize_safe_state()
        self.db.log_system_event("info", "System initialized in safe state")
        self.ui.show_status("ToolTally is ready")

    def run_forever(self) -> None:
        while True:
            event = self.detector.next_event()
            self.db.log_tool_event(event)

            if event.tool == ToolClass.WHITE:
                continue
            if event.tool not in TOOL_CLASSES:
                self.db.log_system_event("warning", f"Unknown tool class: {event.tool}")
                continue

            now = time.monotonic()
            if now - self._last_detection_time < self.config.timing.detection_cooldown_seconds:
                self.ui.show_status("Detection ignored (cooldown)")
                continue
            self._last_detection_time = now

            self._process_tool(event.tool)

    def _process_tool(self, tool: ToolClass) -> None:
        self.ui.show_status(f"Detected {tool.value}. Opening flap.")
        self.hardware.open_flap(tool)

        pin = self.ui.request_pin_suffix(tool)
        if len(pin) != 4 or not pin.isdigit():
            self.db.log_access_event(tool, pin or None, "invalid_pin_format")
            self.ui.show_status("Invalid PIN format.")
            return

        if not self.db.is_valid_employee_pin(pin):
            self.db.log_access_event(tool, pin, "denied")
            self.ui.show_status("Access denied.")
            return

        self.db.log_access_event(tool, pin, "approved")
        self.ui.show_status(f"Access approved. Unlocking {tool.value} drawer.")
        self.hardware.unlock_drawer(tool)
        time.sleep(self.config.timing.drawer_unlock_seconds)
        self.hardware.lock_drawer(tool)
        self.ui.show_status("Drawer locked.")

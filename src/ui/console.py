from __future__ import annotations

from src.models import ToolClass


class ConsoleUI:
    def show_status(self, message: str) -> None:
        print(f"[UI] {message}")

    def request_pin_suffix(self, tool: ToolClass) -> str:
        return input(f"Enter last 4 digits for {tool.value}: ").strip()

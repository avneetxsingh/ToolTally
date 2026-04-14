from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.models import ToolClass, ToolEvent


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pin_suffix TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool TEXT NOT NULL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS access_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool TEXT NOT NULL,
    pin_suffix TEXT,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass
class Database:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def seed_allowed_pins(self, pins: Iterable[str]) -> None:
        clean = [p.strip() for p in pins if p and len(p.strip()) == 4 and p.strip().isdigit()]
        if not clean:
            return
        with self.connect() as conn:
            for pin in clean:
                conn.execute(
                    "INSERT OR IGNORE INTO employees(pin_suffix, created_at) VALUES (?, ?)",
                    (pin, utc_now()),
                )
            conn.commit()

    def is_valid_employee_pin(self, pin_suffix: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM employees WHERE pin_suffix = ? AND active = 1 LIMIT 1",
                (pin_suffix,),
            ).fetchone()
            return row is not None

    def log_tool_event(self, event: ToolEvent) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO tool_events(tool, confidence, source, created_at) VALUES (?, ?, ?, ?)",
                (event.tool.value, event.confidence, event.source, utc_now()),
            )
            conn.commit()

    def log_access_event(self, tool: ToolClass, pin_suffix: str | None, result: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO access_events(tool, pin_suffix, result, created_at) VALUES (?, ?, ?, ?)",
                (tool.value, pin_suffix, result, utc_now()),
            )
            conn.commit()

    def log_system_event(self, level: str, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO system_events(level, message, created_at) VALUES (?, ?, ?)",
                (level.upper(), message, utc_now()),
            )
            conn.commit()

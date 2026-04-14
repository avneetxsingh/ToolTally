from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ToolClass(str, Enum):
    WHITE = "white"
    PLIER = "plier"
    SCREWDRIVER = "screwdriver"
    WRENCH = "wrench"


TOOL_CLASSES = {ToolClass.PLIER, ToolClass.SCREWDRIVER, ToolClass.WRENCH}

TOOL_LABEL_ALIASES = {
    "plier": ToolClass.PLIER,
    "pliers": ToolClass.PLIER,
    "screwdriver": ToolClass.SCREWDRIVER,
    "white": ToolClass.WHITE,
    "wrench": ToolClass.WRENCH,
}


def tool_from_label(label: str) -> Optional[ToolClass]:
    return TOOL_LABEL_ALIASES.get(label.strip().lower())


@dataclass(frozen=True)
class ToolEvent:
    tool: ToolClass
    confidence: float
    source: str

"""CallState: LangGraph state schema (skeleton — Wave 1 fills behaviour).

CallState IS the StateGraph state schema (single source of truth, BLUEPRINT §1A).
Fields are declared here; the turn loop that mutates them is Wave 1 (TASK-A13).
"""
from __future__ import annotations

from pydantic import BaseModel

from callbot.models.schemas import Category, Slot


class CallState(BaseModel):
    category: Category | None = None
    slots: dict[str, Slot] = {}
    emergency: bool = False
    failed_turns: int = 0
    transcript: list[str] = []
    turn_index: int = 0

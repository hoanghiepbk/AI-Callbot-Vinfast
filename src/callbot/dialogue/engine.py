# FROZEN CONTRACT — TASK-003 Wave 0.
"""DialogueEngine: public seam between Track A and Track B. Frozen at Wave 0.
Changes require both tracks to agree (WORKFLOW §5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from callbot.models.schemas import FinalOutput

if TYPE_CHECKING:
    from callbot.llm.base import LLM
    from callbot.normalization.base import Normalizer


class TurnResult(BaseModel):
    reply: str
    done: bool = False
    state: dict  # snapshot of CallState for display/debug


class DialogueEngine:
    def __init__(self, llm: "LLM", normalizer: "Normalizer") -> None:
        raise NotImplementedError("Track A implements this")

    def process(self, user_text: str) -> TurnResult:  # one turn
        raise NotImplementedError("Track A implements this")

    def finalize(self) -> FinalOutput:  # assemble final JSON (also on hangup)
        raise NotImplementedError("Track A implements this")

    def reset(self) -> None:  # new call
        raise NotImplementedError("Track A implements this")

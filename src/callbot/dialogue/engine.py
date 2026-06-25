"""DialogueEngine: public seam (process/finalize/reset) over the graph.

Skeleton only — the turn loop is Wave 1 (TASK-A13). The seam signature is FROZEN
per BLUEPRINT §3 and must not change (it is the Track A<->B boundary).
"""

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
    def __init__(self, llm: "LLM", normalizer: "Normalizer") -> None: ...

    def process(self, user_text: str) -> TurnResult:  # one turn
        raise NotImplementedError  # Wave 1 (TASK-A13)

    def finalize(self) -> FinalOutput:  # assemble final JSON (also on hangup)
        raise NotImplementedError  # Wave 1 (TASK-A13)

    def reset(self) -> None:  # new call
        raise NotImplementedError  # Wave 1 (TASK-A13)

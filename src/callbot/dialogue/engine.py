# FROZEN CONTRACT (seam) — TASK-003 Wave 0. Signatures of TurnResult + DialogueEngine
# may not change without both tracks agreeing (WORKFLOW §5). TASK-A13 fills the bodies.
"""DialogueEngine: the public seam between Track A (brain) and Track B (senses).

One turn = one graph.invoke (BLUEPRINT law #3). The engine owns the persistent CallState
in memory (no checkpointer); each process() resets the transient turn fields, invokes the
graph, and carries the result forward.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from callbot.dialogue.categories import fields_for
from callbot.dialogue.graph import build_graph
from callbot.dialogue.state import CallState
from callbot.models.schemas import FinalOutput, IntentSignals, PostCall, SlotStatus

if TYPE_CHECKING:
    from callbot.llm.base import LLM
    from callbot.normalization.base import Normalizer

_FILLED = {SlotStatus.CONFIRMED, SlotStatus.CORRECTED}


class TurnResult(BaseModel):
    reply: str
    done: bool = False
    state: dict  # snapshot of CallState for display/debug


class DialogueEngine:
    def __init__(self, llm: "LLM", normalizer: "Normalizer") -> None:
        self._app = build_graph(llm, normalizer)
        self._state = CallState()

    def process(self, user_text: str) -> TurnResult:  # one turn
        turn_input = self._state.model_copy(
            update={
                "user_text": user_text,
                "turn_index": self._state.turn_index + 1,
                "transcript": [*self._state.transcript, user_text],
                # reset the transient turn fields so a node never sees stale values
                "extracted": {},
                "corrected": {},
                "signals": IntentSignals(),
                "nlu_category": None,
                "need_clarify": False,
                "turn_failed": False,
                "offer_human": False,
                "current_field": None,
                "reply": "",
                "done": False,
            }
        )
        out: dict[str, Any] = self._app.invoke(turn_input)
        self._state = CallState.model_validate(out)
        return TurnResult(
            reply=self._state.reply,
            done=self._state.done,
            state=self._state.model_dump(mode="json"),
        )

    def finalize(self) -> FinalOutput:  # assemble final JSON (also on hangup)
        state = self._state
        fields: dict[str, str | None] = {}
        if state.category is not None:
            # Every field of the locked category; unconfirmed/unfilled -> null (#8).
            for spec in fields_for(state.category):
                slot = state.slots.get(spec.name)
                fields[spec.name] = slot.value if slot and slot.status in _FILLED else None
        else:
            for name, slot in state.slots.items():
                fields[name] = slot.value if slot.status in _FILLED else None
        post_call = PostCall(
            short_summary="",  # A14 fills summary + sentiment; emergency is known now
            sentimental_analysis="",
            emergency="yes" if state.emergency else "no",
        )
        return FinalOutput(category=state.category, fields=fields, post_call=post_call)

    def reset(self) -> None:  # new call
        self._state = CallState()

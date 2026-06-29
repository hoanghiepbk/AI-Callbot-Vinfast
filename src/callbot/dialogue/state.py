"""CallState: the LangGraph StateGraph schema and single source of truth (BLUEPRINT §1A).

Persistent fields carry across turns (the call's memory); transient fields are written
by the nodes within ONE turn and reset by the engine before the next invoke. Nodes are
pure `(state) -> dict_update` functions — they never mutate this object in place.
"""

from __future__ import annotations

from pydantic import BaseModel

from callbot.models.schemas import Category, IntentSignals, Slot


class CallState(BaseModel):
    # ---- persistent (the call's memory) ----
    category: Category | None = None
    slots: dict[str, Slot] = {}
    emergency: bool = False
    emergency_announced: bool = False  # hotline message already spoken once
    failed_turns: int = 0  # consecutive garbled/ambiguous turns (#7 stuck)
    turn_index: int = 0
    transcript: list[str] = []
    pending_field: str | None = None  # field awaiting readback/repeat confirmation
    pending_reason: str | None = None  # "readback" (D10) | "garbled" (#5)
    last_asked_field: str | None = None  # field the bot asked last turn (answer-binding backstop)

    # ---- transient (one turn; reset by engine before each invoke) ----
    user_text: str = ""
    extracted: dict[str, str] = {}
    corrected: dict[str, str] = {}
    signals: IntentSignals = IntentSignals()
    nlu_category: Category | None = None
    need_clarify: bool = False  # ambiguous, ask one clarifying question (#3)
    turn_failed: bool = False  # this turn made no progress (garbled/ambiguous)
    offer_human: bool = False  # escalate to a human (#7)
    current_field: str | None = None  # next field to ask
    reply: str = ""
    done: bool = False

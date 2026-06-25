"""LangGraph StateGraph: 7 pure nodes wired into the slot-filling turn loop (TASK-A13).

One turn = one graph.invoke. Nodes are pure `(state) -> dict_update`: they read CallState
and return the fields to change, never mutating state or globals. The llm/normalizer
dependencies are closed over by build_graph (injection), not stored on the state.

Topology is a straight chain — branching lives inside `respond`, which reads the flags the
earlier nodes set. That keeps the graph trivial to lift back to a plain loop if LangGraph
is ever dropped (BLUEPRINT §1A insurance).
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from callbot.dialogue import response as tmpl
from callbot.dialogue.categories import next_missing_field, requires_readback
from callbot.dialogue.extraction import nlu_node
from callbot.dialogue.state import CallState
from callbot.llm.base import LLM
from callbot.models.schemas import Slot, SlotStatus
from callbot.normalization.base import Normalizer

# Deterministic backstop for the hybrid emergency rule (FIX3): even if the LLM misses it,
# these words flip emergency on. Sentiment=='urgent' is added later by post-call (A14).
_EMERGENCY_KEYWORDS = (
    "tai nạn",
    "tông",
    "đâm",
    "lật xe",
    "cháy",
    "bốc khói",
    "khói",
    "kẹt giữa",
    "cao tốc",
    "chết máy",
    "không nổ được",
    "mắc kẹt",
)

_FILLED = {SlotStatus.CONFIRMED, SlotStatus.CORRECTED}


def _keyword_emergency(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _EMERGENCY_KEYWORDS)


def build_graph(llm: LLM, normalizer: Normalizer) -> Any:
    """Compile the turn-loop graph with llm/normalizer injected into the nodes."""

    def nlu(state: CallState) -> dict[str, Any]:
        res = nlu_node(llm, state.user_text, state.category)
        return {
            "extracted": res.extracted_fields,
            "corrected": res.corrected_fields,
            "signals": res.signals,
            "nlu_category": res.category,
        }

    def apply_signals(state: CallState) -> dict[str, Any]:
        # Hybrid emergency: LLM flag OR keyword backstop (sticky once true).
        emergency = (
            state.emergency or state.signals.emergency or _keyword_emergency(state.user_text)
        )
        return {"emergency": emergency}

    def route(state: CallState) -> dict[str, Any]:
        if state.category is not None:
            return {}  # category already locked, keep it
        if state.nlu_category is not None:
            return {"category": state.nlu_category}
        # No category yet and the model couldn't pick one -> ask one clarifying question.
        return {"need_clarify": True}

    def slot_update(state: CallState) -> dict[str, Any]:
        if state.category is None:
            return {}
        slots = dict(state.slots)
        provided = {**state.extracted, **state.corrected}  # corrections are values too
        new_pending: str | None = None
        new_reason: str | None = None
        turn_failed = False

        # 1. A readback we asked last turn that the caller did NOT re-provide = confirmed.
        if (
            state.pending_field is not None
            and state.pending_reason == "readback"
            and state.pending_field not in provided
            and not state.signals.correction
        ):
            slot = slots[state.pending_field]
            slots[state.pending_field] = slot.model_copy(
                update={"status": SlotStatus.CONFIRMED, "confirmed_at": state.turn_index}
            )

        # 2. Normalize + store every field provided this turn.
        for field, raw in provided.items():
            norm = normalizer.normalize_field(field, raw)
            if norm.parse_failed:
                slots[field] = Slot(value=None, status=SlotStatus.PENDING, raw_utterance=raw)
                if new_pending is None:
                    new_pending, new_reason = field, "garbled"  # (#5)
                turn_failed = True
                continue
            needs_readback = requires_readback(field) and not state.emergency  # D10
            is_correction = field in state.corrected
            if needs_readback:
                slots[field] = Slot(value=norm.value, status=SlotStatus.PENDING, raw_utterance=raw)
                if new_pending is None:
                    new_pending, new_reason = field, "readback"
            else:
                status = SlotStatus.CORRECTED if is_correction else SlotStatus.CONFIRMED
                slots[field] = Slot(
                    value=norm.value,
                    status=status,
                    raw_utterance=raw,
                    confirmed_at=state.turn_index,
                )

        return {
            "slots": slots,
            "pending_field": new_pending,
            "pending_reason": new_reason,
            "turn_failed": turn_failed,
        }

    def next_field(state: CallState) -> dict[str, Any]:
        if state.category is None:
            return {"current_field": None}
        filled = [name for name, slot in state.slots.items() if slot.status in _FILLED]
        nf = next_missing_field(state.category, filled, state.emergency)
        return {"current_field": nf.name if nf is not None else None}

    def stuck_check(state: CallState) -> dict[str, Any]:
        failed = state.turn_failed or state.need_clarify
        failed_turns = state.failed_turns + 1 if failed else 0
        return {"failed_turns": failed_turns, "offer_human": failed_turns >= 2}

    def respond(state: CallState) -> dict[str, Any]:
        ti = state.turn_index
        # Emergency hotline message: spoken once, then prefixed onto the working reply.
        prefix = ""
        announced = state.emergency_announced
        if state.emergency and not state.emergency_announced:
            prefix = tmpl.emergency_msg() + " "
            announced = True

        def out(reply: str, done: bool = False) -> dict[str, Any]:
            return {"reply": prefix + reply, "done": done, "emergency_announced": announced}

        if state.signals.hangup:  # (#8) caller wants to stop -> goodbye, engine finalizes
            return {"reply": tmpl.closing_goodbye(ti), "done": True}
        if state.signals.out_of_scope and state.category is None:
            return out(tmpl.redirect(ti))
        if state.offer_human:  # (#7) stuck
            return out(tmpl.offer_human(ti))
        if state.pending_field is not None:
            if state.pending_reason == "garbled":
                return out(tmpl.garbled_repeat(state.pending_field, ti))
            value = state.slots[state.pending_field].value or ""
            return out(tmpl.readback(state.pending_field, value, ti))
        if state.need_clarify:  # (#3) ambiguous
            return out(tmpl.clarify(ti))
        if state.current_field is not None:
            return out(tmpl.ask_field(state.current_field, ti))
        return out(tmpl.closing_done(ti), done=True)  # all required fields collected

    graph = StateGraph(CallState)
    graph.add_node("nlu", nlu)
    graph.add_node("apply_signals", apply_signals)
    graph.add_node("route", route)
    graph.add_node("slot_update", slot_update)
    graph.add_node("next_field", next_field)
    graph.add_node("stuck_check", stuck_check)
    graph.add_node("respond", respond)

    graph.add_edge(START, "nlu")
    graph.add_edge("nlu", "apply_signals")
    graph.add_edge("apply_signals", "route")
    graph.add_edge("route", "slot_update")
    graph.add_edge("slot_update", "next_field")
    graph.add_edge("next_field", "stuck_check")
    graph.add_edge("stuck_check", "respond")
    graph.add_edge("respond", END)
    return graph.compile()

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

# Deterministic denial detection for readback (R1). A readback must be able to CATCH a
# wrong value (D10): when the caller rejects it we must NOT confirm. Phrases are clear
# rejections; bare standalone "không" counts too, but "không" embedded in a longer reply
# (e.g. "không sao, đúng rồi") does NOT, to avoid false denials on affirmations.
_DENY_PHRASES = (
    "không đúng",
    "không phải",
    "không chính xác",
    "sai rồi",
    "sai",
    "nhầm",
    "chưa đúng",
    "đọc lại",
    "nhập lại",
    "đọc nhầm",
)
_DENY_EXACT = {"không", "không ạ", "không đâu", "ko", "hông", "hổng"}


def _keyword_emergency(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _EMERGENCY_KEYWORDS)


def _is_denial(text: str) -> bool:
    low = text.strip().lower().rstrip(".!,? ")
    if low in _DENY_EXACT:
        return True
    return any(phrase in low for phrase in _DENY_PHRASES)


# Social greeting / call-opener — handled deterministically so an opening "chào em / alo"
# is greeted back, NOT treated as a no-progress (stuck) turn that escalates to a human (#7).
_GREETINGS = ("chào", "alo", "a lô", "a lo", "xin chào", "hello")


def _is_greeting(text: str) -> bool:
    low = text.strip().lower()
    return low in {"hi", "hey"} or any(g in low for g in _GREETINGS)


# Deterministic category backstop. When the LLM returns no category (qwen3 under-classifies —
# its prompt is tuned to prefer null), these keyword cues route a CLEAR intent to its category
# anyway — the same hybrid (LLM OR keyword) rule used for emergency. Fires ONLY on an LLM null,
# so it can never override the model; it just prevents a clear request being escalated to a
# human (#7). Phrases are domain-specific (incl. common ASR slips) and ordered by precedence.
_RESCUE_KEYWORDS = (  # G_1 roadside rescue — breakdown / danger
    "cứu hộ",
    "cứu họ",  # ASR slip
    "cẩu kéo",
    "kéo xe",
    "chết máy",
    "chết ở giữa",
    "chết giữa đường",
    "hỏng giữa đường",
    "nằm giữa đường",
    "kẹt giữa đường",
    "hết xăng",
    "thủng lốp",
    "nổ lốp",
    "không nổ máy",
    "không nổ được máy",
)
_TECH_KEYWORDS = (  # G_5 remote tech support — software / app / screen
    "phần mềm",
    "ứng dụng",
    "màn hình",
    "kết nối",
    "cập nhật",
    "định vị",
    "lỗi app",
    "không lên màn",
)
_ORDER_KEYWORDS = (  # G_3 order status / purchase / dealer
    "đơn hàng",
    "đặt cọc",
    "đơn đặt",
    "đặt mua",
    "đại lý",
    "mã đơn",
    "tình trạng đơn",
    "giao xe",
    "nhận xe",
    "mua xe",
)
_WARRANTY_KEYWORDS = (  # G_2 (car) / G_4 (motorbike) — service / warranty / booking
    "bảo hành",
    "giảo hành",  # ASR slip
    "bảo dưỡng",
    "bảo trì",
    "sửa chữa",
    "sửa xe",
    "đặt lịch",
    "trung tâm dịch vụ",
    "kiểm tra xe",
)
_MOTORBIKE_WORDS = (  # disambiguates warranty: motorbike -> G_4, else car -> G_2
    "xe máy",
    "xe điện máy",
    "klara",
    "vento",
    "feliz",
    "evo",
    "theon",
    "ludo",
    "impes",
)


# Lead-ins stripped from a bound free-text answer so the slot stores the value, not the framing
# ("Mình là Nguyễn Mai Phương" -> "Nguyễn Mai Phương"). Longest-match first.
_ANSWER_PREFIXES = (
    "họ và tên của mình là",
    "họ và tên của em là",
    "họ và tên mình là",
    "họ tên của mình là",
    "tên của mình là",
    "tên của em là",
    "số của mình là",
    "số mình là",
    "vị trí của mình là",
    "địa chỉ của mình là",
    "mình tên là",
    "em tên là",
    "tên mình là",
    "mình là",
    "em là",
    "tôi là",
    "dạ",
)


def _strip_answer_prefix(text: str) -> str:
    stripped = text.strip()
    low = stripped.lower()
    for prefix in sorted(_ANSWER_PREFIXES, key=len, reverse=True):
        if low.startswith(prefix):
            rest = stripped[len(prefix) :].strip(" ,.:;")
            return rest or stripped  # never bind to empty
    return stripped


# Confusion / filler replies that are NOT an answer — must not be bound to the asked field
# (otherwise a baffled caller's "hả?" would fill a slot and dodge the stuck escalation #7).
_NON_ANSWERS = {
    "huh",
    "hả",
    "gì",
    "gì cơ",
    "gì vậy",
    "gì thế",
    "sao",
    "sao cơ",
    "um",
    "ừm",
    "ờ",
    "à",
    "ơ",
    "dạ",
    "vâng",
    "không biết",
    "hổng biết",
    "chịu",
    "?",
}


# Hesitation/stalling openers: an utterance that IS one of these, or starts with one as a word,
# is a stall ("ừm để xem", "để xem sao"), not an answer — so it must not be bound (keeps the
# stuck escalation #7 working on a stalling caller).
_HESITATION_STEMS = (
    "ừm",
    "ờ",
    "à",
    "ơ",
    "ừ",
    "hmm",
    "để xem",
    "để tôi",
    "để em",
    "để mình",
    "khoan",
    "đợi",
    "chưa nghĩ",
    "chưa biết",
)


def _is_non_answer(text: str) -> bool:
    low = text.strip().lower().rstrip(".!,? ")
    if low in _NON_ANSWERS:
        return True
    return any(low == stem or low.startswith(stem + " ") for stem in _HESITATION_STEMS)


def _keyword_category(text: str) -> str | None:
    low = text.lower()
    if any(kw in low for kw in _RESCUE_KEYWORDS):
        return "G_1"
    if any(kw in low for kw in _TECH_KEYWORDS):
        return "G_5"
    if any(kw in low for kw in _ORDER_KEYWORDS):
        return "G_3"
    is_motorbike = any(m in low for m in _MOTORBIKE_WORDS)
    if any(kw in low for kw in _WARRANTY_KEYWORDS):
        return "G_4" if is_motorbike else "G_2"
    if is_motorbike:  # motorbike mentioned without an explicit service word
        return "G_4"
    return None


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
        # LLM returned no category. Deterministic rescue backstop before giving up: a clear
        # breakdown ("chết máy", "cần cứu hộ"…) routes to G_1. Set nlu_category too so this
        # counts as a classified turn (not a no-progress failure in slot_update / stuck_check).
        kw_cat = _keyword_category(state.user_text)
        if kw_cat is not None:
            return {"category": kw_cat, "nlu_category": kw_cat}
        # Still nothing -> ask one clarifying question (#3).
        return {"need_clarify": True}

    def slot_update(state: CallState) -> dict[str, Any]:
        if state.category is None:
            return {}
        slots = dict(state.slots)
        provided = {**state.extracted, **state.corrected}  # corrections are values too

        # Answer-binding backstop: the bot asked for a specific field last turn but the LLM
        # extracted nothing for it. If the caller's reply is a direct answer (not a denial /
        # correction / topic change / digression), bind the (de-prefixed) utterance to that
        # field so a weak extractor cannot stall the call and escalate. Read-back numeric fields
        # still flow through normalize + confirm below.
        asked = state.last_asked_field
        if (
            asked is not None
            and not provided  # bind ONLY when the LLM extracted nothing (else trust the LLM)
            and state.user_text.strip()
            and not _is_non_answer(state.user_text)
            and not _is_denial(state.user_text)
            and not state.signals.correction
            and not state.signals.out_of_scope
            and not state.signals.hangup
            and not _is_greeting(state.user_text)
            and state.nlu_category in (None, state.category)
        ):
            provided = {asked: _strip_answer_prefix(state.user_text)}

        new_pending: str | None = None
        new_reason: str | None = None
        turn_failed = False
        progressed = False  # did this turn advance slot-filling at all? (#7 stuck)

        # 1. Resolve an outstanding readback from last turn, when the caller did NOT
        #    re-provide that field. Default is confirm (silence = yes), BUT an explicit
        #    denial/correction keeps it PENDING and re-asks — readback exists to CATCH a
        #    wrong value (D10, R1), so when in doubt we do NOT confirm.
        pending = state.pending_field
        if (
            pending is not None
            and state.pending_reason in ("readback", "denied")
            and pending not in provided
        ):
            if _is_denial(state.user_text) or state.signals.correction:
                new_pending, new_reason = pending, "denied"  # ask again, do NOT confirm
                turn_failed = True
            else:
                slots[pending] = slots[pending].model_copy(
                    update={"status": SlotStatus.CONFIRMED, "confirmed_at": state.turn_index}
                )
                progressed = True

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
            progressed = True

        # 3. No-progress turn (#7): category locked but nothing advanced — not a field,
        #    not a readback resolution, not even a (re)stated intent. Count it as a failed
        #    turn so repeated dead ends (empty NLU, nothing extracted) escalate to a human.
        #    OOS/hangup turns are deliberate digressions, not failures; a bare social greeting
        #    is greeted back (handled in respond), never counted as stuck — same rule as
        #    stuck_check, applied here too so a mid-call "alo/chào" can't escalate (#7).
        if not turn_failed and not progressed and state.nlu_category is None:
            digression = state.signals.out_of_scope or state.signals.hangup
            if not digression and not _is_greeting(state.user_text):
                turn_failed = True

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
        # A bare greeting is a clarify turn but NOT "stuck" — never let it count toward (#7).
        clarify_failed = state.need_clarify and not _is_greeting(state.user_text)
        failed = state.turn_failed or clarify_failed
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

        def out(reply: str, done: bool = False, asked: str | None = None) -> dict[str, Any]:
            # `asked` = the field this reply requests, remembered for next turn's answer-binding.
            return {
                "reply": prefix + reply,
                "done": done,
                "emergency_announced": announced,
                "last_asked_field": asked,
            }

        if state.signals.hangup:  # (#8) caller wants to stop -> goodbye, engine finalizes
            return {"reply": tmpl.closing_goodbye(ti), "done": True, "last_asked_field": None}
        if state.signals.out_of_scope:  # (#4) redirect at ANY point, keep collected state
            return out(tmpl.redirect(ti))
        if state.offer_human:  # (#7) stuck -> offer human, then END the call (transfer).
            # done=True so the engine finalizes partial JSON instead of repeating the offer
            # forever — a stuck call cannot make progress, so handing off is terminal.
            return out(tmpl.offer_human(ti), done=True)
        if state.pending_field is not None:
            if state.pending_reason == "garbled":
                return out(tmpl.garbled_repeat(state.pending_field, ti))
            if state.pending_reason == "denied":  # caller rejected the readback (R1)
                return out(tmpl.readback_denied(state.pending_field, ti))
            value = state.slots[state.pending_field].value or ""
            return out(tmpl.readback(state.pending_field, value, ti))
        if state.need_clarify:  # greeting -> greet back; otherwise (#3) ambiguous -> clarify
            if _is_greeting(state.user_text):
                return out(tmpl.greeting(ti))
            return out(tmpl.clarify(ti))
        if state.current_field is not None:
            # Remember the asked field so next turn can bind a bare answer to it.
            return out(tmpl.ask_field(state.current_field, ti), asked=state.current_field)
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

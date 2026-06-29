"""A greeting must be greeted back, never escalated to a human as a 'stuck' turn (#7)."""

from __future__ import annotations

from callbot.dialogue import response as tmpl
from callbot.dialogue.engine import DialogueEngine
from callbot.llm.base import LLMResult
from callbot.normalization.vietnamese_numbers import VietnameseNormalizer

_NULL_NLU = (
    '{"category":null,"extracted_fields":{},"corrected_fields":{},'
    '"signals":{"emergency":false,"out_of_scope":false,"correction":false,"hangup":false}}'
)


_G3_NLU = (
    '{"category":"G_3","extracted_fields":{},"corrected_fields":{},'
    '"signals":{"emergency":false,"out_of_scope":false,"correction":false,"hangup":false}}'
)


class _NullLLM:
    """NLU returns null category / no fields (what the model emits for a bare greeting)."""

    def complete(self, system: str, user: str, json_schema=None) -> LLMResult:
        if "tổng kết" in system:  # post-call summary
            return LLMResult(
                text='{"short_summary":"x","sentimental_analysis":"calm"}', latency_ms=0.0
            )
        return LLMResult(text=_NULL_NLU, latency_ms=0.0)


class _LockThenNullLLM:
    """Locks G_3 on the first utterance, then emits null NLU (a bare greeting) thereafter."""

    def __init__(self) -> None:
        self._locked = False

    def complete(self, system: str, user: str, json_schema=None) -> LLMResult:
        if "tổng kết" in system:  # post-call summary
            return LLMResult(
                text='{"short_summary":"x","sentimental_analysis":"calm"}', latency_ms=0.0
            )
        if not self._locked:
            self._locked = True
            return LLMResult(text=_G3_NLU, latency_ms=0.0)
        return LLMResult(text=_NULL_NLU, latency_ms=0.0)


def _engine() -> DialogueEngine:
    return DialogueEngine(_NullLLM(), VietnameseNormalizer())


def test_greeting_is_greeted_not_escalated():
    engine = _engine()
    res = engine.process("chào em")
    assert res.reply in tmpl._GREETING_SHELLS  # greets back (not clarify / offer-human)
    assert res.state["offer_human"] is False
    assert res.state["failed_turns"] == 0  # greeting is not a stuck turn


def test_repeated_greeting_never_offers_human():
    engine = _engine()
    for _ in range(3):
        res = engine.process("chào em")
    assert res.state["offer_human"] is False  # the reported bug: must NOT happen


def test_genuinely_stuck_still_offers_human():
    # Non-greeting empty/ambiguous turns must still escalate after 2 (#7 intact).
    engine = _engine()
    engine.process("ờ")
    res = engine.process("ừm")
    assert res.state["offer_human"] is True


def test_midcall_greeting_with_locked_category_never_escalates():
    # Category already locked, then bare greetings: the no-progress (#7) branch must NOT
    # count them as stuck either (same exemption as the clarify branch).
    engine = DialogueEngine(_LockThenNullLLM(), VietnameseNormalizer())
    engine.process("em hỏi đơn hàng")  # locks G_3
    for _ in range(3):
        res = engine.process("alo")
    assert res.state["offer_human"] is False
    assert res.state["failed_turns"] == 0

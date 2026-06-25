"""Tests for post-call generation (TASK-A14). LLM mocked; live test skipped."""

from __future__ import annotations

import json
import logging

import pytest

from callbot.dialogue.engine import DialogueEngine
from callbot.dialogue.post_call import detect_missed_emergency, generate_post_call
from callbot.dialogue.state import CallState
from callbot.llm.base import LLMResult
from callbot.models.schemas import PostCall
from callbot.normalization.vietnamese_numbers import VietnameseNormalizer


def _summary_json(short_summary: str, sentiment: str) -> str:
    return json.dumps({"short_summary": short_summary, "sentimental_analysis": sentiment})


class FixedLLM:
    """Always returns the same summary JSON (for post-call unit tests)."""

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, system: str, user: str, json_schema=None) -> LLMResult:
        return LLMResult(text=self.text, latency_ms=0.0)


def test_generate_post_call_returns_three_fields():
    llm = FixedLLM(_summary_json("Khách hỏi đơn hàng, đã ghi nhận.", "calm"))
    state = CallState(emergency=False)

    pc = generate_post_call(llm, ["em hỏi đơn hàng"], state)

    assert isinstance(pc, PostCall)
    assert pc.short_summary == "Khách hỏi đơn hàng, đã ghi nhận."
    assert pc.sentimental_analysis == "calm"
    assert pc.emergency == "no"


def test_emergency_taken_from_state_not_llm():
    # LLM summary says nothing about emergency; the flag comes purely from state.
    llm = FixedLLM(_summary_json("Cứu hộ trên cao tốc.", "urgent"))

    pc_yes = generate_post_call(llm, ["xe tai nạn"], CallState(emergency=True))
    assert pc_yes.emergency == "yes"

    llm_calm = FixedLLM(_summary_json("Hỏi bảo hành.", "calm"))
    pc_no = generate_post_call(llm_calm, ["hỏi bảo hành"], CallState(emergency=False))
    assert pc_no.emergency == "no"


def test_detect_missed_emergency_helper():
    assert detect_missed_emergency("urgent", emergency_happened=False) is True
    assert detect_missed_emergency("URGENT", emergency_happened=False) is True
    assert detect_missed_emergency("urgent", emergency_happened=True) is False
    assert detect_missed_emergency("calm", emergency_happened=False) is False


def test_cross_check_logs_possible_missed_emergency(caplog):
    # sentiment=urgent but emergency never fired in-call -> warn (eval signal), no flip.
    llm = FixedLLM(_summary_json("Khách có vẻ gấp gáp.", "urgent"))
    state = CallState(emergency=False)

    with caplog.at_level(logging.WARNING):
        pc = generate_post_call(llm, ["xe của em hỏng"], state)

    assert pc.emergency == "no"  # NOT flipped on by sentiment
    assert any("possible_missed_emergency" in r.message for r in caplog.records)


def test_malformed_summary_falls_back_safely():
    llm = FixedLLM("")  # A10 exhausted retries
    pc = generate_post_call(llm, ["gì đó"], CallState(emergency=True))

    assert pc.short_summary == ""
    assert pc.sentimental_analysis == "unknown"
    assert pc.emergency == "yes"  # still recorded from state


# --- end-to-end through the engine ---
def _nlu_payload(category=None, extracted=None, hangup=False) -> str:
    return json.dumps(
        {
            "category": category,
            "extracted_fields": extracted or {},
            "corrected_fields": {},
            "signals": {
                "emergency": False,
                "out_of_scope": False,
                "correction": False,
                "hangup": hangup,
            },
        }
    )


class ScriptedLLM:
    """Routes NLU turns vs the post-call summary by a marker in the system prompt."""

    def __init__(self, nlu_script: dict[str, str], summary_json: str) -> None:
        self.nlu_script = nlu_script
        self.summary_json = summary_json

    def complete(self, system: str, user: str, json_schema=None) -> LLMResult:
        if "tổng kết" in system:  # post-call summarizer prompt
            return LLMResult(text=self.summary_json, latency_ms=0.0)
        return LLMResult(text=self.nlu_script.get(user, _nlu_payload()), latency_ms=0.0)


def test_finalize_end_to_end_fills_post_call():
    nlu_script = {
        "intro": _nlu_payload(category="G_3"),
        "name": _nlu_payload(extracted={"full_name": "Tran Van Hung"}),
        "bye": _nlu_payload(hangup=True),
    }
    llm = ScriptedLLM(nlu_script, _summary_json("Khách hỏi đơn, cung cấp tên.", "calm"))
    engine = DialogueEngine(llm, VietnameseNormalizer())

    engine.process("intro")
    engine.process("name")
    engine.process("bye")
    final = engine.finalize()

    assert final.category == "G_3"
    assert final.post_call.short_summary == "Khách hỏi đơn, cung cấp tên."
    assert final.post_call.sentimental_analysis == "calm"
    assert final.post_call.emergency == "no"
    assert final.fields["full_name"] == "Tran Van Hung"


# --- live (skipped without Ollama) ---
def _ollama_up() -> bool:
    try:
        import ollama

        ollama.Client().list()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _ollama_up(), reason="needs live Ollama + qwen3:8b")
def test_generate_post_call_live():
    from callbot.llm.ollama_client import OllamaClient

    pc = generate_post_call(
        OllamaClient(),
        ["xe em chết máy giữa cao tốc", "biển số 30A-12345"],
        CallState(emergency=True),
    )
    assert pc.emergency == "yes"
    assert isinstance(pc.short_summary, str) and pc.short_summary

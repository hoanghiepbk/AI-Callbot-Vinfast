"""Unit tests for nlu_node (TASK-A12). LLM is stubbed; a live regression is skipped
unless Ollama is reachable."""

from __future__ import annotations

import json

import pytest

from callbot.dialogue.extraction import build_system, nlu_node
from callbot.llm.base import LLMResult
from callbot.models.schemas import NLUResult


def _nlu_json(**overrides) -> str:
    payload = {
        "category": None,
        "extracted_fields": {},
        "corrected_fields": {},
        "signals": {
            "emergency": False,
            "out_of_scope": False,
            "correction": False,
            "hangup": False,
        },
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


class _StubLLM:
    """Records the args it was called with and returns a fixed completion."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[tuple[str, str, dict | None]] = []

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult:
        self.calls.append((system, user, json_schema))
        return LLMResult(text=self._text, latency_ms=1.0)


def test_parses_llm_json_into_nluresult():
    llm = _StubLLM(_nlu_json(category="G_3", extracted_fields={"vehicle_model": "vf ba"}))

    res = nlu_node(llm, "đơn vf ba tới đâu rồi")

    assert isinstance(res, NLUResult)
    assert res.category == "G_3"
    assert res.extracted_fields == {"vehicle_model": "vf ba"}
    assert llm.calls[0][2] is not None  # schema passed -> OllamaClient runs think=False


def test_identity_utterance_not_emergency():
    # Regression for the M2 bug: bare phone/name must not fire G_1 + emergency.
    llm = _StubLLM(_nlu_json(extracted_fields={"phone": "không chín không một"}))

    res = nlu_node(llm, "số em là không chín không một")

    assert res.category is None
    assert res.signals.emergency is False


def test_correction_signal():
    llm = _StubLLM(
        _nlu_json(
            corrected_fields={"phone": "bảy tám"},
            signals={
                "emergency": False,
                "out_of_scope": False,
                "correction": True,
                "hangup": False,
            },
        )
    )

    res = nlu_node(llm, "à nhầm bảy tám chứ không phải sáu tám")

    assert res.signals.correction is True
    assert res.corrected_fields == {"phone": "bảy tám"}


def test_bad_json_returns_safe_empty():
    res = nlu_node(_StubLLM("not json at all"), "bất kỳ")  # A10 exhausted retries

    assert res.category is None
    assert res.signals.emergency is False
    assert res.extracted_fields == {}


def test_locked_category_pinned_in_prompt():
    llm = _StubLLM(_nlu_json(category="G_2"))

    nlu_node(llm, "thế còn cái lốp thì sao", current_category="G_2")

    system = llm.calls[0][0]
    assert "G_2" in system
    assert "NGỮ CẢNH" in system  # the pin line was appended


def test_build_system_no_context_has_no_pin():
    assert "NGỮ CẢNH" not in build_system(None)


# --- Live regression: the actual prompt fix can only be proven against real Ollama ---
def _ollama_up() -> bool:
    try:
        import ollama

        ollama.Client().list()
        return True
    except Exception:  # noqa: BLE001 - any failure => not available, skip
        return False


@pytest.mark.skipif(not _ollama_up(), reason="needs live Ollama + qwen3:8b")
def test_identity_cases_not_emergency_live():
    from callbot.llm.ollama_client import OllamaClient

    llm = OllamaClient()
    identity_cases = [
        "số em là không chín không một hai ba bốn năm sáu bảy",
        "biển số xe là ba mươi a chấm một hai ba bốn",
        "em tên là nguyễn văn an",
    ]
    for text in identity_cases:
        res = nlu_node(llm, text)
        assert res.signals.emergency is False, f"over-fired emergency on: {text!r}"

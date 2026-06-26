"""Offline tests for the A31 ablation plumbing (patch/restore, JSON counter, factory).

These never touch Ollama — the real-Ollama measurement runs via `python -m eval.ablation`.
"""

from __future__ import annotations

from callbot.dialogue import extraction, graph
from callbot.dialogue.graph import _keyword_emergency
from callbot.llm.base import LLMResult
from eval.ablation import (
    _CALM_CASES,
    _json_valid_pct,
    _JSONCount,
    _no_glossary_build_system,
    _rate,
    counting_factory,
    glossary_off,
    keyword_off,
)


def test_glossary_off_prompt_drops_canonical_glossary():
    # Production prompt teaches canonical names; the ablation prompt must not.
    assert "order_code_dealer" in extraction.build_system("G_3")
    assert "order_code_dealer" not in _no_glossary_build_system("G_3")
    assert "customer_type" not in _no_glossary_build_system("G_3")


def test_glossary_off_patches_and_restores():
    original = extraction.build_system
    with glossary_off():
        assert extraction.build_system is _no_glossary_build_system
        # nlu_node resolves build_system from the module global, so it sees the patch.
        assert "order_code_dealer" not in extraction.build_system("G_3")
    assert extraction.build_system is original


def test_keyword_off_disables_backstop_and_restores():
    original = graph._keyword_emergency
    assert graph._keyword_emergency("xe em chết máy giữa cao tốc") is True
    with keyword_off():
        assert graph._keyword_emergency("xe em chết máy giữa cao tốc") is False
    assert graph._keyword_emergency is original
    assert graph._keyword_emergency("xe em chết máy giữa cao tốc") is True


class _FakeLLM:
    def __init__(self, texts: list[str]) -> None:
        self._texts = iter(texts)

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult:
        return LLMResult(text=next(self._texts), latency_ms=0.0)


def test_json_counter_counts_only_structured_valid():
    stats = {"total": 0, "valid": 0}
    client = _JSONCount(_FakeLLM(['{"a": 1}', "not json", "ignored"]), stats)
    client.complete("s", "u", json_schema={})  # valid
    client.complete("s", "u", json_schema={})  # invalid
    client.complete("s", "u", json_schema=None)  # unstructured -> not counted
    assert stats == {"total": 2, "valid": 1}
    assert _json_valid_pct(stats) == 50.0


def test_counting_factory_shares_stats_across_clients():
    factory, stats = counting_factory(lambda: _FakeLLM(['{"x": 1}']))
    factory().complete("s", "u", json_schema={})
    factory().complete("s", "u", json_schema={})
    assert stats["total"] == 2 and stats["valid"] == 2


def test_json_valid_pct_handles_empty():
    assert _json_valid_pct({"total": 0, "valid": 0}) == 0.0


def test_rate_helper():
    assert _rate(3, 4) == 75.0
    assert _rate(0, 0) == 0.0  # no division by zero


def test_first_three_calm_cases_have_no_emergency_keyword():
    # The first-attempt test isolates the LLM flag, so the leading calm cases must carry no
    # keyword the engine backstop could otherwise catch.
    for case in _CALM_CASES[:3]:
        assert not _keyword_emergency(case)

"""Eval harness (TASK-A21): run golden scenarios through the real DialogueEngine.

Two modes:
- scripted (default, CI): a FakeLLM returns the per-turn `nlu` written in the scenario,
  so routing/slot-filling of the ENGINE are measured deterministically (no Ollama).
- real (`run_all(..., llm_factory=lambda: OllamaClient())`): the live LLM does extraction;
  used locally for end-to-end numbers (CI skips it).

Testing is TURN-LEVEL: each turn's `expect` is checked right after process(), so bugs in
the middle of a conversation (re-asking a filled field, confirming a denied readback) are
caught — not only the final JSON.

Metrics are PLUGGABLE: a metric is a function `(list[ScenarioResult]) -> dict`. A30 adds
emergency-recall / latency / judge metrics by appending to the list, without touching this
harness (ScenarioResult already carries both expected and predicted).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from callbot.dialogue.engine import DialogueEngine
from callbot.dialogue.response import FIELD_LABELS
from callbot.llm.base import LLMResult
from callbot.normalization.vietnamese_numbers import VietnameseNormalizer

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "eval"
_SUMMARY_JSON = json.dumps({"short_summary": "eval", "sentimental_analysis": "calm"})


def _full_nlu(partial: dict[str, Any] | None) -> str:
    """Expand a partial per-turn `nlu` spec into a full NLUResult JSON string."""
    partial = partial or {}
    signals = {"emergency": False, "out_of_scope": False, "correction": False, "hangup": False}
    signals.update(partial.get("signals", {}))
    return json.dumps(
        {
            "category": partial.get("category"),
            "extracted_fields": partial.get("extracted_fields", {}),
            "corrected_fields": partial.get("corrected_fields", {}),
            "signals": signals,
        }
    )


class ScriptedLLM:
    """Returns the scenario's scripted NLU per user utterance; fixed post-call summary."""

    def __init__(self, turn_map: dict[str, str]) -> None:
        self._map = turn_map

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult:
        if "tổng kết" in system:  # post-call summarizer prompt
            return LLMResult(text=_SUMMARY_JSON, latency_ms=0.0)
        return LLMResult(text=self._map.get(user, _full_nlu(None)), latency_ms=0.0)


@dataclass
class TurnFailure:
    index: int
    detail: str


@dataclass
class ScenarioResult:
    id: str
    tier: str
    category_expected: str | None
    category_predicted: str | None
    fields_expected: dict[str, str | None]
    fields_predicted: dict[str, str | None]
    turn_failures: list[TurnFailure] = field(default_factory=list)
    done: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.category_predicted == self.category_expected
            and not self.turn_failures
            and self._fields_match()
        )

    def _fields_match(self) -> bool:
        for name, expected in self.fields_expected.items():
            if not _value_match(self.fields_predicted.get(name), expected):
                return False
        return True


def _value_match(predicted: str | None, expected: str | None) -> bool:
    if expected is None:
        return predicted is None
    if predicted is None:
        return False
    return " ".join(predicted.lower().split()) == " ".join(expected.lower().split())


def load_scenarios(path: Path = SCENARIO_DIR) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for file in sorted(path.glob("*.json")):
        scenarios.extend(json.loads(file.read_text(encoding="utf-8")))
    return scenarios


def _check_turn(expect: dict[str, Any], state: dict[str, Any], reply: str) -> list[str]:
    """Turn-level assertions; returns a list of failure descriptions (empty = ok)."""
    fails: list[str] = []
    if "asks_field" in expect:
        label = FIELD_LABELS.get(expect["asks_field"], expect["asks_field"])
        if label not in reply:
            fails.append(f"expected to ask '{expect['asks_field']}' but reply={reply!r}")
    if "not_reask" in expect:
        label = FIELD_LABELS.get(expect["not_reask"], expect["not_reask"])
        if label in reply:
            fails.append(f"should NOT re-ask '{expect['not_reask']}' but reply={reply!r}")
    if "reply_contains" in expect and expect["reply_contains"] not in reply:
        fails.append(f"reply missing {expect['reply_contains']!r}: {reply!r}")
    if "emergency" in expect and state["emergency"] is not expect["emergency"]:
        fails.append(f"emergency expected {expect['emergency']} got {state['emergency']}")
    if "done" in expect and state["done"] is not expect["done"]:
        fails.append(f"done expected {expect['done']} got {state['done']}")
    for fld, status in expect.get("slot_status", {}).items():
        actual = state["slots"].get(fld, {}).get("status")
        if actual != status:
            fails.append(f"slot '{fld}' status expected {status} got {actual}")
    return fails


def run_scenario(scenario: dict[str, Any], llm: Any | None = None) -> ScenarioResult:
    if llm is None:
        turn_map = {t["user"]: _full_nlu(t.get("nlu")) for t in scenario["turns"]}
        llm = ScriptedLLM(turn_map)
    engine = DialogueEngine(llm, VietnameseNormalizer())

    turn_failures: list[TurnFailure] = []
    last: Any = None
    for i, turn in enumerate(scenario["turns"]):
        last = engine.process(turn["user"])
        if "expect" in turn:
            for detail in _check_turn(turn["expect"], last.state, last.reply):
                turn_failures.append(TurnFailure(i, detail))
    final = engine.finalize()

    return ScenarioResult(
        id=scenario["id"],
        tier=scenario.get("tier", "?"),
        category_expected=scenario.get("category_expected", scenario.get("category")),
        category_predicted=final.category,
        fields_expected=scenario.get("final_expected", {}).get("fields", {}),
        fields_predicted=final.fields,
        turn_failures=turn_failures,
        done=bool(last.done) if last is not None else False,
    )


def run_all(
    scenarios: list[dict[str, Any]] | None = None,
    llm_factory: Callable[[], Any] | None = None,
) -> list[ScenarioResult]:
    scenarios = scenarios if scenarios is not None else load_scenarios()
    return [run_scenario(s, llm_factory() if llm_factory else None) for s in scenarios]

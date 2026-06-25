"""Contract freeze tests for Phase 1 (CTR-01, CTR-02).

These tests run on every PR to catch schema drift between tracks. Per D-05:
runtime pytest only; mypy static conformance deferred to Phase 3.
"""

import json

from callbot.dialogue.engine import TurnResult
from callbot.dialogue.fake_engine import FakeDialogueEngine
from callbot.models.schemas import FinalOutput, NormResult


class _StubNormalizer:
    """Echoes the raw value back, never fails — keeps tests offline."""

    def normalize_field(self, name: str, raw: str) -> NormResult:
        return NormResult(value=raw, parse_failed=False)


class _StubLLM:
    """Never called by FakeDialogueEngine (canned replies only)."""

    def complete(self, system, user, json_schema=None):
        return None


def test_fake_engine_process_returns_valid_turn_result():
    fe = FakeDialogueEngine(llm=_StubLLM(), normalizer=_StubNormalizer())
    result = fe.process("xin chào")

    # Returns a real TurnResult that round-trips through Pydantic v2 validation.
    TurnResult.model_validate(result.model_dump())

    assert isinstance(result.reply, str) and len(result.reply) > 0
    assert isinstance(result.done, bool)
    assert isinstance(result.state, dict)


def test_fake_engine_finalize_returns_valid_final_output_with_nulls():
    fe = FakeDialogueEngine(llm=_StubLLM(), normalizer=_StubNormalizer())
    # Simulate a partial call — only some slots get filled.
    fe.process("xin chào")
    fe.process("Nguyễn Văn Nam")

    fin = fe.finalize()

    # Valid FinalOutput per the frozen schema.
    FinalOutput.model_validate(fin.model_dump())
    assert isinstance(fin.fields, dict)

    # Unfilled fields are None (-> null in JSON), not absent from the dict.
    serialized = json.loads(fin.model_dump_json())
    assert any(v is None for v in fin.fields.values())
    assert any(v is None for v in serialized["fields"].values())

    assert fin.post_call.emergency in ("yes", "no")


def test_fake_engine_satisfies_engine_seam():
    # Duck-type seam check: the fake exposes the DialogueEngine interface.
    assert hasattr(FakeDialogueEngine, "process")
    assert hasattr(FakeDialogueEngine, "finalize")
    assert hasattr(FakeDialogueEngine, "reset")

    fe = FakeDialogueEngine(llm=_StubLLM(), normalizer=_StubNormalizer())
    assert callable(fe.process)
    assert callable(fe.finalize)
    assert callable(fe.reset)

    # Constructor matches DialogueEngine.__init__(self, llm, normalizer).
    varnames = fe.__init__.__code__.co_varnames
    assert "llm" in varnames
    assert "normalizer" in varnames

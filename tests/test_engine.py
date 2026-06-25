"""GATE 1 — DialogueEngine happy paths + core exceptions (TASK-A13).

The LLM is faked (scripted NLUResult per user utterance); the normalizer is the REAL
B10 VietnameseNormalizer. All phone/plate values are FAKE.
"""

from __future__ import annotations

import json

import pytest

from callbot.dialogue.categories import fields_for
from callbot.dialogue.engine import DialogueEngine
from callbot.llm.base import LLMResult
from callbot.normalization.vietnamese_numbers import VietnameseNormalizer

READBACK = {"phone", "owner_phone", "order_phone", "license_plate_vin"}

# Normalizer-safe raw inputs per field (verified to parse). No emergency keywords here.
VALUES = {
    "current_location": "duong Le Loi quan 1",
    "vehicle_condition": "den bao loi dong co",
    "vehicle_condition_details": "man hinh giai tri tu khoi dong",
    "phone": "0901234567",
    "owner_phone": "0912345678",
    "order_phone": "0987654321",
    "city_name": "Ha Noi",
    "full_name": "Tran Van Hung",
    "vehicle_model": "VF 8",
    "vehicle_line": "Klara S",
    "license_plate_vin": "30A-12345",
    "vehicle_type": "o to dien",
    "vehicle_usage_type": "ca nhan",
    "current_odo": "12000",
    "service_center": "VinFast Long Bien",
    "order_code_dealer": "ABC123",
    "customer_type": "ca nhan",
}


def nlu_payload(
    category=None,
    extracted=None,
    corrected=None,
    emergency=False,
    out_of_scope=False,
    correction=False,
    hangup=False,
) -> str:
    return json.dumps(
        {
            "category": category,
            "extracted_fields": extracted or {},
            "corrected_fields": corrected or {},
            "signals": {
                "emergency": emergency,
                "out_of_scope": out_of_scope,
                "correction": correction,
                "hangup": hangup,
            },
        }
    )


class FakeLLM:
    """Returns a scripted NLUResult JSON keyed by the user utterance."""

    def __init__(self, script: dict[str, str]) -> None:
        self.script = script

    def complete(self, system: str, user: str, json_schema=None) -> LLMResult:
        return LLMResult(text=self.script.get(user, nlu_payload()), latency_ms=0.0)


def _engine(script: dict[str, str]) -> DialogueEngine:
    return DialogueEngine(FakeLLM(script), VietnameseNormalizer())


def _drive(engine: DialogueEngine, order: list[str]):
    result = None
    for utterance in order:
        result = engine.process(utterance)
    return result


def _build_happy_path(category: str) -> tuple[dict[str, str], list[str]]:
    """Intro turn locks the category, then one turn per required field (+ a confirm
    turn after each readback field)."""
    script: dict[str, str] = {}
    order: list[str] = []
    intro = f"intro {category}"
    script[intro] = nlu_payload(category=category)
    order.append(intro)
    for spec in fields_for(category):
        if not spec.required:
            continue  # optional fields are never asked
        give = f"give {category} {spec.name}"
        script[give] = nlu_payload(extracted={spec.name: VALUES[spec.name]})
        order.append(give)
        if spec.name in READBACK:
            confirm = f"confirm {category} {spec.name}"
            script[confirm] = nlu_payload()  # empty utterance => confirmation
            order.append(confirm)
    return script, order


@pytest.mark.parametrize("category", ["G_1", "G_2", "G_3", "G_4", "G_5"])
def test_happy_path_each_category(category):
    script, order = _build_happy_path(category)
    engine = _engine(script)

    result = _drive(engine, order)
    final = engine.finalize()

    assert result.done is True
    assert final.category == category
    # finalize lists every field of the category (filled or null).
    assert set(final.fields) == {f.name for f in fields_for(category)}
    # Every required field must be collected (non-null).
    for spec in fields_for(category):
        if spec.required:
            assert final.fields[spec.name] is not None, f"{category}.{spec.name} missing"
    # G_5 current_odo is optional -> never asked -> null.
    if category == "G_5":
        assert final.fields["current_odo"] is None


def test_readback_field_confirmed_with_correct_value():
    script, order = _build_happy_path("G_3")
    engine = _engine(script)
    _drive(engine, order)

    final = engine.finalize()
    assert final.fields["order_phone"] == "0987654321"  # normalized, read back, confirmed


def test_missing_field_not_reasked():
    script = {
        "intro": nlu_payload(category="G_3"),
        "name": nlu_payload(extracted={"full_name": "Tran Van Hung"}),
    }
    engine = _engine(script)

    engine.process("intro")  # asks full_name
    r2 = engine.process("name")  # fills full_name -> should now ask order_phone

    assert "họ và tên" not in r2.reply  # not re-asking a filled field (#1)
    assert "số điện thoại" in r2.reply  # moved on to the next field


def test_correction_updates_value_without_reloop():
    script = {
        "intro": nlu_payload(category="G_3"),
        "name_a": nlu_payload(extracted={"full_name": "Tran Van A"}),
        "fix": nlu_payload(corrected={"full_name": "Tran Van B"}, correction=True),
    }
    engine = _engine(script)

    engine.process("intro")
    engine.process("name_a")
    r3 = engine.process("fix")

    snap_slots = r3.state["slots"]
    assert snap_slots["full_name"]["value"] == "Tran Van B"  # updated (#2)
    assert snap_slots["full_name"]["status"] == "corrected"


def test_emergency_skips_low_priority_and_readback():
    # G_1 emergency: priority>=90 (current_odo) skipped; readback fields confirmed inline.
    specs = [f for f in fields_for("G_1") if f.required and f.priority < 90]
    script = {"sos": nlu_payload(category="G_1", emergency=True)}
    order = ["sos"]
    for spec in specs:
        key = f"give {spec.name}"
        script[key] = nlu_payload(extracted={spec.name: VALUES[spec.name]})
        order.append(key)  # NO confirm turns — emergency defers readback

    engine = _engine(script)
    result = _drive(engine, order)
    final = engine.finalize()

    assert result.state["emergency"] is True
    assert final.post_call.emergency == "yes"
    assert result.done is True  # completed WITHOUT ever asking current_odo (skipped)
    assert final.fields["current_odo"] is None
    assert final.fields["phone"] == "0901234567"  # collected without a readback turn


def test_hybrid_emergency_keyword_backstop():
    # LLM says emergency=false, but the keyword backstop must still flip it on (FIX3).
    script = {"kw": nlu_payload(category="G_1", emergency=False)}
    # user_text itself carries the keyword (with diacritics)
    engine = _engine({"xe bốc khói ở nắp ca pô": script["kw"]})
    result = engine.process("xe bốc khói ở nắp ca pô")

    assert result.state["emergency"] is True


def test_hangup_midway_finalizes_partial():
    script = {
        "intro": nlu_payload(category="G_3"),
        "name": nlu_payload(extracted={"full_name": "Tran Van Hung"}),
        "bye": nlu_payload(hangup=True),
    }
    engine = _engine(script)

    engine.process("intro")
    engine.process("name")
    r3 = engine.process("bye")
    final = engine.finalize()

    assert r3.done is True
    assert final.fields["full_name"] == "Tran Van Hung"
    assert final.fields["order_phone"] is None  # not collected -> null (#8)
    assert final.fields["customer_type"] is None


def test_ambiguous_first_turn_asks_clarification():
    engine = _engine({"vague": nlu_payload(category=None)})

    result = engine.process("vague")

    assert result.done is False
    assert result.state["category"] is None
    assert "hỗ trợ" in result.reply  # clarify template (#3)


def test_garbled_value_triggers_repeat():
    script = {
        "intro": nlu_payload(category="G_4"),
        "name": nlu_payload(extracted={"full_name": "Tran Van Hung"}),
        "bad": nlu_payload(extracted={"phone": "abc"}),  # won't normalize
    }
    engine = _engine(script)
    engine.process("intro")
    engine.process("name")
    r3 = engine.process("bad")

    assert "nhắc lại" in r3.reply  # garbled repeat (#5)
    assert r3.state["slots"]["phone"]["status"] == "pending"


def test_two_engines_do_not_share_state():
    # No hidden global/self mutation across instances (pure nodes).
    e1 = _engine({"a": nlu_payload(category="G_3")})
    e2 = _engine({"a": nlu_payload(category="G_2")})

    e1.process("a")
    e2.process("a")

    assert e1.finalize().category == "G_3"
    assert e2.finalize().category == "G_2"


def test_reset_clears_state():
    engine = _engine({"intro": nlu_payload(category="G_3")})
    engine.process("intro")
    engine.reset()

    final = engine.finalize()
    assert final.category is None
    assert final.fields == {}


# --- R1: readback must be able to CATCH a wrong value (deny detection) ---
def _readback_script(extra: dict[str, str]) -> dict[str, str]:
    base = {
        "intro": nlu_payload(category="G_3"),
        "name": nlu_payload(extracted={"full_name": "Tran Van Hung"}),
        "phone": nlu_payload(extracted={"order_phone": "0987654321"}),
    }
    base.update(extra)
    return base


def test_readback_denial_does_not_confirm():
    engine = _engine(_readback_script({"không đúng": nlu_payload()}))  # denial, NLU empty
    engine.process("intro")
    engine.process("name")
    r3 = engine.process("phone")  # reads back order_phone
    assert r3.state["slots"]["order_phone"]["status"] == "pending"

    r4 = engine.process("không đúng")
    assert r4.state["slots"]["order_phone"]["status"] == "pending"  # NOT confirmed
    assert "đọc lại" in r4.reply  # asked to re-provide
    assert engine.finalize().fields["order_phone"] is None  # wrong value not recorded


def test_readback_correction_updates_and_rereads():
    extra = {
        "fix": nlu_payload(corrected={"order_phone": "0901234567"}, correction=True),
        "yes": nlu_payload(),
    }
    engine = _engine(_readback_script(extra))
    for u in ["intro", "name", "phone", "fix"]:
        last = engine.process(u)

    assert last.state["slots"]["order_phone"]["value"] == "0901234567"  # updated
    assert last.state["slots"]["order_phone"]["status"] == "pending"  # re-readback
    assert "0901234567" in last.reply
    engine.process("yes")
    assert engine.finalize().fields["order_phone"] == "0901234567"


def test_readback_affirmation_confirms():
    engine = _engine(_readback_script({"đúng rồi": nlu_payload()}))
    for u in ["intro", "name", "phone", "đúng rồi"]:
        engine.process(u)
    assert engine.finalize().fields["order_phone"] == "0987654321"


def test_readback_implicit_confirm_on_next_field():
    extra = {"code": nlu_payload(extracted={"order_code_dealer": "ABC123"})}
    engine = _engine(_readback_script(extra))
    for u in ["intro", "name", "phone", "code"]:
        engine.process(u)

    final = engine.finalize()
    assert final.fields["order_phone"] == "0987654321"  # implicitly confirmed
    assert final.fields["order_code_dealer"] == "ABC123"


def test_is_denial_keyword_detection():
    from callbot.dialogue.graph import _is_denial

    assert _is_denial("không đúng") is True
    assert _is_denial("sai rồi") is True
    assert _is_denial("không") is True  # bare standalone denial
    assert _is_denial("đúng rồi") is False
    assert _is_denial("không sao, đúng rồi ạ") is False  # embedded 'không' != denial


# --- R5: finalize() memoizes the post-call LLM call ---
def test_finalize_memoized_calls_post_call_llm_once():
    class CountingLLM:
        def __init__(self) -> None:
            self.summary_calls = 0

        def complete(self, system, user, json_schema=None) -> LLMResult:
            if "tổng kết" in system:  # post-call summarizer
                self.summary_calls += 1
                text = json.dumps({"short_summary": "x", "sentimental_analysis": "calm"})
                return LLMResult(text=text, latency_ms=0.0)
            return LLMResult(text=nlu_payload(category="G_3"), latency_ms=0.0)

    llm = CountingLLM()
    engine = DialogueEngine(llm, VietnameseNormalizer())
    engine.process("hi")
    engine.finalize()
    engine.finalize()
    engine.finalize()
    assert llm.summary_calls == 1  # memoized, not called 3x


def test_finalize_cache_invalidated_by_new_turn():
    class CountingLLM:
        def __init__(self) -> None:
            self.summary_calls = 0

        def complete(self, system, user, json_schema=None) -> LLMResult:
            if "tổng kết" in system:
                self.summary_calls += 1
                text = json.dumps({"short_summary": "x", "sentimental_analysis": "calm"})
                return LLMResult(text=text, latency_ms=0.0)
            return LLMResult(text=nlu_payload(category="G_3"), latency_ms=0.0)

    llm = CountingLLM()
    engine = DialogueEngine(llm, VietnameseNormalizer())
    engine.process("hi")
    engine.finalize()
    engine.process("more")  # new turn invalidates the memo
    engine.finalize()
    assert llm.summary_calls == 2


# --- Live smoke test (skipped without Ollama) ---
def _ollama_up() -> bool:
    try:
        import ollama

        ollama.Client().list()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _ollama_up(), reason="needs live Ollama + qwen3:8b")
def test_engine_runs_one_real_turn():
    from callbot.llm.ollama_client import OllamaClient

    engine = DialogueEngine(OllamaClient(), VietnameseNormalizer())
    result = engine.process("xe em bị tai nạn trên cao tốc")

    assert isinstance(result.reply, str) and result.reply
    assert result.state["emergency"] is True  # rescue scenario

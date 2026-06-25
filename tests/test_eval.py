"""Tests for the eval harness + metrics (TASK-A21). Scripted mode, no Ollama."""

from __future__ import annotations

from eval.harness import ScenarioResult, load_scenarios, run_all, run_scenario
from eval.metrics import DEFAULT_METRICS, routing_metric, slot_f1_metric


def _result(cat_exp, cat_pred, fexp=None, fpred=None, tfails=None) -> ScenarioResult:
    return ScenarioResult(
        id="x",
        tier="t",
        category_expected=cat_exp,
        category_predicted=cat_pred,
        fields_expected=fexp or {},
        fields_predicted=fpred or {},
        turn_failures=tfails or [],
        done=True,
    )


def test_load_scenarios_format():
    scenarios = load_scenarios()
    assert len(scenarios) >= 10  # >= brief minimum (2/category) + exceptions
    for s in scenarios:
        assert "id" in s and "turns" in s
        assert "category_expected" in s or "category" in s


def test_routing_metric_accuracy_and_confusion():
    results = [_result("G_1", "G_1"), _result("G_2", "G_3")]
    m = routing_metric(results)

    assert m["accuracy"] == 0.5
    assert (m["correct"], m["total"]) == (1, 2)
    idx = {label: i for i, label in enumerate(m["labels"])}
    assert m["confusion"][idx["G_1"]][idx["G_1"]] == 1
    assert m["confusion"][idx["G_2"]][idx["G_3"]] == 1  # G_2 misrouted as G_3


def test_slot_f1_metric_known_case():
    # full_name correct (tp); phone predicted wrong value (both fp and fn).
    r = _result(
        "G_3",
        "G_3",
        fexp={"full_name": "A", "phone": "1"},
        fpred={"full_name": "A", "phone": "2"},
    )
    m = slot_f1_metric([r])

    assert m["per_field"]["full_name"]["f1"] == 1.0
    phone = m["per_field"]["phone"]
    assert (phone["tp"], phone["fp"], phone["fn"]) == (0, 1, 1)
    assert abs(m["macro_f1"] - 0.5) < 1e-9  # mean(1.0, 0.0)


def test_slot_f1_value_match_after_normalization():
    # Case/space differences must still count as a match.
    r = _result("G_3", "G_3", fexp={"full_name": "tran van a"}, fpred={"full_name": "Tran  Van A"})
    assert slot_f1_metric([r])["per_field"]["full_name"]["f1"] == 1.0


def test_turn_level_catches_injected_bug():
    # The scenario claims the bot asks 'city_name' first, but G_3 asks full_name first.
    buggy = {
        "id": "buggy",
        "category_expected": "G_3",
        "turns": [
            {"user": "i", "nlu": {"category": "G_3"}, "expect": {"asks_field": "city_name"}},
        ],
        "final_expected": {"fields": {}},
    }
    res = run_scenario(buggy)

    assert res.turn_failures  # harness flagged the mid-conversation mismatch
    assert "city_name" in res.turn_failures[0].detail


def test_golden_routes_perfectly_and_high_slot_f1():
    results = run_all()
    assert routing_metric(results)["accuracy"] == 1.0
    assert slot_f1_metric(results)["macro_f1"] >= 0.99


def test_metrics_registry_is_pluggable():
    results = run_all()
    computed = [fn(results) for fn in DEFAULT_METRICS]  # A30 just appends to this list
    assert {m["name"] for m in computed} == {"routing_accuracy", "slot_filling_f1"}

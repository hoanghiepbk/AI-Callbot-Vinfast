"""Tests for the A30 metric suite: emergency safety, latency stats, judge gate, WER gate.

Deterministic + offline: the judge skip-path and WER pending-path make NO network/model
calls, so they run in CI.
"""

from __future__ import annotations

from eval.harness import ScenarioResult, run_all
from eval.judge import naturalness_judge
from eval.latency import _percentile, _summarize
from eval.metrics import emergency_metric
from eval.wer import measure_wer


def _emg(eid, expected, predicted, group=None, sentiment="calm") -> ScenarioResult:
    return ScenarioResult(
        id=eid,
        tier="t",
        category_expected="G_1",
        category_predicted="G_1",
        fields_expected={},
        fields_predicted={},
        emergency_expected=expected,
        emergency_predicted=predicted,
        emergency_group=group,
        sentiment_predicted=sentiment,
    )


def test_emergency_recall_precision_and_groups():
    results = [
        _emg("kw_hit", True, True, "keyword"),
        _emg("calm_hit", True, True, "calm"),
        _emg("calm_miss", True, False, "calm"),  # MISS -> recall < 1
        _emg("false_fire", False, True),  # FP -> precision < 1
        _emg("clean", False, False),  # TN
    ]
    m = emergency_metric(results)

    o = m["overall"]
    assert (o["tp"], o["fp"], o["fn"]) == (2, 1, 1)
    assert abs(o["recall"] - 2 / 3) < 1e-9  # 2 fired of 3 true
    assert abs(o["precision"] - 2 / 3) < 1e-9  # 2 correct of 3 fired
    assert m["by_group"]["keyword"]["recall"] == 1.0
    assert abs(m["by_group"]["calm"]["recall"] - 0.5) < 1e-9


def test_emergency_urgent_miss_counts_unfired_urgent():
    results = [
        _emg("urgent_but_calm_engine", False, False, sentiment="urgent"),  # urgent-miss
        _emg("urgent_and_fired", True, True, "keyword", sentiment="urgent"),  # not a miss
    ]
    m = emergency_metric(results)
    assert m["urgent_miss_count"] == 1
    assert m["urgent_miss_scenarios"] == ["urgent_but_calm_engine"]


def test_emergency_on_golden_scenarios():
    # Golden has 4 true emergencies (2 keyword + 2 calm) and 1 keyword false-positive.
    m = emergency_metric(run_all())
    assert m["overall"]["recall"] == 1.0  # engine + keyword backstop fire all true ones
    assert m["overall"]["fn"] == 0
    assert m["overall"]["fp"] >= 1  # the 'cao tốc' casual false-positive is exposed
    assert m["by_group"]["keyword"]["recall"] == 1.0
    assert m["by_group"]["calm"]["recall"] == 1.0


def test_latency_percentile_interpolates():
    samples = [10.0, 20.0, 30.0, 40.0]
    assert _percentile(samples, 50) == 25.0
    assert _percentile([5.0], 95) == 5.0  # single sample
    assert _percentile([], 50) == 0.0  # empty


def test_latency_summarize_shape():
    s = _summarize([10.0, 20.0, 30.0])
    assert s["n"] == 3
    assert s["mean"] == 20.0
    assert set(s) == {"p50", "p95", "mean", "n"}


def test_judge_skips_without_model(monkeypatch):
    monkeypatch.delenv("JUDGE_MODEL", raising=False)
    out = naturalness_judge(run_all())
    assert out["status"] == "skipped"
    assert "local" in out["note"]  # documents the bot stays local


def test_wer_pending_without_audio():
    out = measure_wer()
    # No committed audio set yet (B14) -> must return pending, never raise.
    assert out["status"] in {"pending", "ok"}
    if out["status"] == "pending":
        assert "pending" in out["reason"].lower() or "jiwer" in out["reason"].lower()

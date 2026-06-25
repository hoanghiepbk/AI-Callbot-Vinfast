"""Eval metrics (TASK-A21): deterministic routing + slot-filling F1.

Each metric is a pluggable function `(list[ScenarioResult]) -> dict`. A30 (Wave 3) adds
emergency recall/precision, latency and LLM-judge metrics by appending to DEFAULT_METRICS
— the harness and report iterate the list, so no signature changes are needed.
"""

from __future__ import annotations

from collections.abc import Sequence

from eval.harness import ScenarioResult, _value_match

_LABELS = ["G_1", "G_2", "G_3", "G_4", "G_5", "null"]


def _label(category: str | None) -> str:
    return category if category else "null"


def routing_metric(results: Sequence[ScenarioResult]) -> dict:
    """Routing accuracy + a 6x6 confusion matrix (rows=expected, cols=predicted)."""
    n = len(results)
    correct = sum(1 for r in results if r.category_predicted == r.category_expected)
    index = {label: i for i, label in enumerate(_LABELS)}
    confusion = [[0] * len(_LABELS) for _ in _LABELS]
    for r in results:
        confusion[index[_label(r.category_expected)]][index[_label(r.category_predicted)]] += 1
    return {
        "name": "routing_accuracy",
        "accuracy": correct / n if n else 0.0,
        "correct": correct,
        "total": n,
        "labels": _LABELS,
        "confusion": confusion,
    }


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def slot_f1_metric(results: Sequence[ScenarioResult]) -> dict:
    """Per-field and per-category slot-filling P/R/F1. 'Correct' = value matches after
    normalization (case/space-insensitive). A value mismatch counts as BOTH FP and FN."""
    per_field: dict[str, dict[str, int]] = {}
    per_cat: dict[str, dict[str, int]] = {}

    def bucket(store: dict[str, dict[str, int]], key: str) -> dict[str, int]:
        return store.setdefault(key, {"tp": 0, "fp": 0, "fn": 0})

    for r in results:
        cat = _label(r.category_expected)
        expected = {k: v for k, v in r.fields_expected.items() if v is not None}
        predicted = {k: v for k, v in r.fields_predicted.items() if v is not None}
        for name in set(expected) | set(predicted):
            exp, pred = expected.get(name), predicted.get(name)
            fb, cb = bucket(per_field, name), bucket(per_cat, cat)
            if exp is not None and pred is not None and _value_match(pred, exp):
                fb["tp"] += 1
                cb["tp"] += 1
                continue
            if pred is not None:  # predicted a value that is wrong or unexpected
                fb["fp"] += 1
                cb["fp"] += 1
            if exp is not None:  # expected a value that is missing or wrong
                fb["fn"] += 1
                cb["fn"] += 1

    field_scores = {name: _prf(**counts) for name, counts in sorted(per_field.items())}
    cat_scores = {cat: _prf(**counts) for cat, counts in sorted(per_cat.items())}
    macro_f1 = (
        sum(s["f1"] for s in field_scores.values()) / len(field_scores) if field_scores else 0.0
    )
    return {
        "name": "slot_filling_f1",
        "macro_f1": macro_f1,
        "per_field": field_scores,
        "per_category": cat_scores,
    }


# Pluggable registry — A30 appends emergency-recall / latency / judge metrics here.
DEFAULT_METRICS = [routing_metric, slot_f1_metric]

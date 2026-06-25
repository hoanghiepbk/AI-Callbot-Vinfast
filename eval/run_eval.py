"""Eval runner (TASK-A21): run golden scenarios, print a report, write results.json.

    python -m eval.run_eval            # scripted mode (deterministic, no Ollama)
    python -m eval.run_eval --ollama   # real LLM does extraction (needs Ollama running)

results.json is consumed by the report task (A32).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from eval.harness import ScenarioResult, _value_match, load_scenarios, run_all
from eval.metrics import DEFAULT_METRICS

_RESULTS_PATH = Path(__file__).resolve().parent / "results.json"


def _print_confusion(routing: dict[str, Any]) -> None:
    labels = routing["labels"]
    print("\nConfusion matrix (row=expected, col=predicted):")
    print("        " + " ".join(f"{c:>5}" for c in labels))
    for label, row in zip(labels, routing["confusion"]):
        print(f"  {label:>5} " + " ".join(f"{v:>5}" for v in row))


def _print_report(results: list[ScenarioResult], metrics: dict[str, dict[str, Any]]) -> None:
    routing = metrics["routing_accuracy"]
    slot = metrics["slot_filling_f1"]

    print(f"=== EVAL · {len(results)} scenarios ===")
    print(
        f"Routing accuracy : {100 * routing['accuracy']:.1f}%  "
        f"({routing['correct']}/{routing['total']})"
    )
    print(f"Slot-filling macro-F1: {slot['macro_f1']:.3f}")
    print("  per-category F1:")
    for cat, s in slot["per_category"].items():
        print(f"    {cat:>5}: F1={s['f1']:.3f}  P={s['precision']:.3f} R={s['recall']:.3f}")
    _print_confusion(routing)

    passed = [r for r in results if r.passed]
    print(f"\nScenarios passed: {len(passed)}/{len(results)}")
    failures = [r for r in results if not r.passed]
    if failures:
        print("\n--- FAILURES (honest) ---")
        for r in failures:
            reasons = []
            if r.category_predicted != r.category_expected:
                reasons.append(f"route {r.category_predicted}!={r.category_expected}")
            for tf in r.turn_failures:
                reasons.append(f"turn{tf.index}: {tf.detail}")
            for name, exp in r.fields_expected.items():
                got = r.fields_predicted.get(name)
                if not _value_match(got, exp):
                    reasons.append(f"field {name}: got {got!r} exp {exp!r}")
            print(f"  [{r.tier}] {r.id}: " + " | ".join(reasons))


def _write_results(results: list[ScenarioResult], metrics: dict[str, dict[str, Any]]) -> None:
    payload = {
        "metrics": metrics,
        "scenarios": [
            {
                **asdict(r),
                "passed": r.passed,
                "turn_failures": [asdict(t) for t in r.turn_failures],
            }
            for r in results
        ],
    }
    _RESULTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama", action="store_true", help="use real Ollama for extraction")
    args = parser.parse_args()

    llm_factory = None
    if args.ollama:
        from callbot.llm.ollama_client import OllamaClient

        llm_factory = OllamaClient

    scenarios = load_scenarios()
    if not scenarios:
        print("[BLOCKED] no scenarios found in scenarios/eval/")
        return 1

    results = run_all(scenarios, llm_factory=llm_factory)
    computed = [fn(results) for fn in DEFAULT_METRICS]  # each metric runs once (A30-safe)
    metrics = {m["name"]: m for m in computed}
    _print_report(results, metrics)
    _write_results(results, metrics)
    print(f"\nWrote {_RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

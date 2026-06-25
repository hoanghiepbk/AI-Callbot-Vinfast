"""Eval runner (TASK-A21 + A30): run golden scenarios, print a full metric report, write
results.json (+ a committed snapshot).

    python -m eval.run_eval            # scripted mode (deterministic, no Ollama)
    python -m eval.run_eval --ollama   # real LLM does extraction + real latency (needs Ollama)

Metric suite (A30): routing · slot-F1 · emergency recall/precision (keyword vs calm) +
urgent-miss · latency p50/p95 per stage (real mode) · LLM-judge naturalness (JUDGE_MODEL) ·
WER (if B14 audio present). results.json is consumed by the report task (A32); a trimmed,
deterministic results_snapshot.json is committed so the report always has numbers to cite.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from eval.harness import ScenarioResult, _value_match, load_scenarios, run_all
from eval.judge import naturalness_judge
from eval.latency import measure_latency
from eval.metrics import DEFAULT_METRICS
from eval.wer import measure_wer

_RESULTS_PATH = Path(__file__).resolve().parent / "results.json"
_SNAPSHOT_PATH = Path(__file__).resolve().parent / "results_snapshot.json"


def _print_confusion(routing: dict[str, Any]) -> None:
    labels = routing["labels"]
    print("\nConfusion matrix (row=expected, col=predicted):")
    print("        " + " ".join(f"{c:>5}" for c in labels))
    for label, row in zip(labels, routing["confusion"]):
        print(f"  {label:>5} " + " ".join(f"{v:>5}" for v in row))


def _print_emergency(emg: dict[str, Any]) -> None:
    o = emg["overall"]
    print("\nEmergency safety (recall = fired/true; precision = correct-fire/all-fired):")
    print(
        f"  overall : recall={o['recall']:.3f} precision={o['precision']:.3f}  "
        f"(tp={o['tp']} fp={o['fp']} fn={o['fn']})"
    )
    for group, s in emg["by_group"].items():
        total = s["tp"] + s["fn"]
        print(f"  {group:>7} : recall={s['recall']:.3f}  ({s['tp']}/{total} fired)")
    print(f"  urgent-miss: {emg['urgent_miss_count']} {emg['urgent_miss_scenarios']}")


def _print_latency(lat: dict[str, Any]) -> None:
    print(f"\nLatency (real pipeline, {lat['turns_measured']} turns) — ms p50 / p95:")
    for stage, s in lat["stages"].items():
        print(f"  {stage:>7}: p50={s['p50']:>8.1f}  p95={s['p95']:>8.1f}  mean={s['mean']:>8.1f}")
    for note in lat["notes"]:
        print(f"  note: {note}")


def _print_judge(judge: dict[str, Any]) -> None:
    if judge.get("status") != "ok":
        print(f"\nJudge naturalness: {judge.get('status')} — {judge.get('reason', '')}")
        print(f"  ({judge.get('note', '')})")
        return
    print(f"\nJudge naturalness: mean={judge['mean_score']}/5 over {judge['rated']} scenarios")
    print(f"  {judge['note']}")


def _print_wer(wer: dict[str, Any]) -> None:
    if wer["status"] != "ok":
        print(f"\nWER/CER: {wer['status']} — {wer['reason']}")
        return
    print(f"\nWER/CER ({wer['files']} files): WER={wer['wer']:.4f}  CER={wer['cer']:.4f}")


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
    _print_emergency(metrics["emergency_safety"])

    passed = [r for r in results if r.passed]
    print(f"\nScenarios passed: {len(passed)}/{len(results)}")
    _print_failures(results)


def _print_failures(results: list[ScenarioResult]) -> None:
    """Honest failure analysis: which scenarios failed and the root cause."""
    failures = [r for r in results if not r.passed]
    if not failures:
        return
    print("\n--- FAILURE ANALYSIS (honest) ---")
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
        if r.emergency_expected != r.emergency_predicted:
            reasons.append(f"emergency exp {r.emergency_expected} got {r.emergency_predicted}")
        print(f"  [{r.tier}] {r.id}: " + " | ".join(reasons))


def _serialize_results(results: list[ScenarioResult]) -> list[dict[str, Any]]:
    return [
        {**asdict(r), "passed": r.passed, "turn_failures": [asdict(t) for t in r.turn_failures]}
        for r in results
    ]


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

    # Latency needs a live pipeline run (real LLM) — real mode only.
    latency: dict[str, Any] = {"name": "latency", "status": "skipped (use --ollama)"}
    if args.ollama:
        latency = measure_latency(scenarios, llm_factory=llm_factory)
        _print_latency(latency)

    judge = naturalness_judge(results)  # self-gates on JUDGE_MODEL (skips without network)
    _print_judge(judge)

    wer = measure_wer()  # pending until B14 audio exists
    _print_wer(wer)

    payload = {
        "mode": "ollama" if args.ollama else "scripted",
        "metrics": metrics,
        "latency": latency,
        "judge": judge,
        "wer": wer,
        "scenarios": _serialize_results(results),
    }
    _RESULTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Committed snapshot: deterministic scripted run only, so the report (A32) always has
    # numbers under version control even though results.json is gitignored.
    if not args.ollama:
        snapshot = {
            "mode": "scripted",
            "metrics": metrics,
            "judge": {k: judge[k] for k in ("name", "status") if k in judge},
            "wer": {k: wer[k] for k in ("name", "status") if k in wer},
            "scenarios": [{"id": r.id, "tier": r.tier, "passed": r.passed} for r in results],
        }
        _SNAPSHOT_PATH.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nWrote {_RESULTS_PATH} + {_SNAPSHOT_PATH}")
    else:
        print(f"\nWrote {_RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

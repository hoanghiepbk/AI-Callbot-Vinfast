"""Spike (re-measure): STRICT emergency recall — empty/invalid output counts as MISS.

Reuses the exact SYSTEM + few-shot from measure_nlu.py so numbers are comparable.
Splits emergency cases into keyword-clear vs calm, runs the signature calm case 5x,
and tests whether a single retry-on-empty rescues recall.

    OLLAMA_MODEL=qwen3:8b python scripts/measure_emergency.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import ollama
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for measure_nlu
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from measure_nlu import FEWSHOT, HOST, MODEL, SYSTEM  # noqa: E402

from callbot.models.schemas import NLUResult  # noqa: E402

RUNS = 3
CALM_RUNS = 5

# Emergency cases taken verbatim from the original 16-case set (emergency == True).
KEYWORD_CLEAR = [
    "xe vừa tông vào dải phân cách trên quốc lộ một",
    "xe bốc khói ở nắp ca pô em sợ quá",
]
CALM = [
    "xe chết máy giữa đường tối quá không thấy gì",
    "anh ơi xe em đỗ giữa cao tốc không nổ được",
]
ALL_EMERGENCY = KEYWORD_CLEAR + CALM
CALM_SIGNATURE = "anh ơi xe em đỗ giữa cao tốc không nổ được"

_client = ollama.Client(host=HOST, timeout=90)  # bound runaway thinking-mode generations
_schema = NLUResult.model_json_schema()


def _call(text: str) -> str:
    # A timeout / transport error means the model failed to answer in time => MISS.
    try:
        resp = _client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                *FEWSHOT,
                {"role": "user", "content": text},
            ],
            format=_schema,
            options={"temperature": 0},
            keep_alive="10m",
        )
    except Exception:  # noqa: BLE001 - spike: any failure = no usable answer
        return ""
    return str(resp["message"]["content"])


def _classify(raw: str) -> str:
    """Return 'hit' (emergency=true), 'empty', 'invalid', or 'miss' (valid but false)."""
    if not raw.strip():
        return "empty"
    try:
        data = json.loads(raw)
        nlu = NLUResult.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return "invalid"
    return "hit" if nlu.signals.emergency else "miss"


def _call_with_retry(text: str) -> str:
    raw = _call(text)
    if _classify(raw) in {"empty", "invalid"}:
        raw = _call(text)  # one retry-on-empty (models A10 retry)
    return raw


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    try:
        _client.list()
    except Exception as exc:  # noqa: BLE001
        print(f"[BLOCKED] Ollama not reachable at {HOST}: {exc}")
        return 1

    # --- 1+2. strict recall per run, by group (empty/invalid/miss all = MISS) ---
    print(f"=== STRICT emergency recall · model={MODEL} · {RUNS} runs · empty=MISS ===")
    per_run: list[float] = []
    group_hits = {"keyword": 0, "calm": 0}
    group_total = {"keyword": len(KEYWORD_CLEAR) * RUNS, "calm": len(CALM) * RUNS}
    for run in range(RUNS):
        hits = 0
        for text in ALL_EMERGENCY:
            verdict = _classify(_call(text))
            if verdict == "hit":
                hits += 1
                group_hits["keyword" if text in KEYWORD_CLEAR else "calm"] += 1
        n = len(ALL_EMERGENCY)
        per_run.append(hits / n)
        print(f"  run {run + 1}: recall {hits}/{n} = {100 * hits / n:.0f}%")
    print(f"  AVERAGE recall: {100 * sum(per_run) / len(per_run):.1f}%")
    print(
        f"  group keyword-clear: {group_hits['keyword']}/{group_total['keyword']} = "
        f"{100 * group_hits['keyword'] / group_total['keyword']:.0f}%"
    )
    print(
        f"  group calm-voice   : {group_hits['calm']}/{group_total['calm']} = "
        f"{100 * group_hits['calm'] / group_total['calm']:.0f}%"
    )

    # --- 3. calm signature, 5 runs ---
    print(f"\n=== calm signature x{CALM_RUNS}: {CALM_SIGNATURE!r} ===")
    tally = {"hit": 0, "empty": 0, "invalid": 0, "miss": 0}
    for _ in range(CALM_RUNS):
        tally[_classify(_call(CALM_SIGNATURE))] += 1
    print(
        f"  hit(emergency=true): {tally['hit']}/{CALM_RUNS} · empty: {tally['empty']}/{CALM_RUNS} "
        f"· invalid: {tally['invalid']}/{CALM_RUNS} · miss-flag: {tally['miss']}/{CALM_RUNS}"
    )

    # --- 4. retry-on-empty: recall before vs after ---
    print(f"\n=== retry-on-empty · {RUNS} runs over {len(ALL_EMERGENCY)} emergency cases ===")
    retry_hits = 0
    for _ in range(RUNS):
        for text in ALL_EMERGENCY:
            if _classify(_call_with_retry(text)) == "hit":
                retry_hits += 1
    total = len(ALL_EMERGENCY) * RUNS
    before = 100 * sum(per_run) / len(per_run)
    after = 100 * retry_hits / total
    print(
        f"  recall before: {before:.1f}%  ->  after 1 retry: {after:.1f}%  ({retry_hits}/{total})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

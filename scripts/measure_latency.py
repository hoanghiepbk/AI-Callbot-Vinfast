"""Throwaway spike (M1): measure per-stage latency.

NOT product code. Today it measures the LLM stage only (one NLU-style turn), since
ASR/TTS impls land with B11/B20. Run after Ollama is up:

    OLLAMA_MODEL=qwen3:8b python scripts/measure_latency.py

Prints LLM latency p50/p95 over N turns (model kept warm via keep_alive). When ASR/TTS
exist, extend with mic->ASR and LLM->TTS timers and sum an E2E total per turn.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import ollama

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from callbot.models.schemas import NLUResult  # noqa: E402

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
N = 10

PROMPT = "khách nói: xe em chết máy giữa cao tốc không nổ được. Trả JSON NLUResult."


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main() -> int:
    client = ollama.Client(host=HOST)
    schema = NLUResult.model_json_schema()
    try:
        client.list()
    except Exception as exc:  # noqa: BLE001
        print(f"[BLOCKED] Ollama not reachable at {HOST}: {exc}")
        return 1

    # Warm-up: load the model resident (keep_alive) so we don't time the cold load.
    client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": "ping"}],
        keep_alive="10m",
    )

    llm_ms: list[float] = []
    for _ in range(N):
        t0 = time.perf_counter()
        client.chat(
            model=MODEL,
            messages=[{"role": "user", "content": PROMPT}],
            format=schema,
            options={"temperature": 0},
            keep_alive="10m",
        )
        llm_ms.append((time.perf_counter() - t0) * 1000)

    print(f"\n=== M1 LATENCY (LLM stage only) · model={MODEL} · N={N} ===")
    print(f"  LLM/turn  p50: {_percentile(llm_ms, 0.50):8.0f} ms")
    print(f"  LLM/turn  p95: {_percentile(llm_ms, 0.95):8.0f} ms")
    print(f"  LLM/turn  min: {min(llm_ms):8.0f} ms   max: {max(llm_ms):8.0f} ms")
    print("\n  ASR (mic->text) and TTS (text->audio) stages: pending B11 / B20.")
    print("  E2E total/turn = ASR + LLM + TTS — compute once those land.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

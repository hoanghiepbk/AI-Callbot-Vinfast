"""Real-mode latency measurement (A30) through the actual CallbotPipeline.

Latency is NOT a pure function of ScenarioResult — it needs a live pipeline run with the
real LLM — so it is not in DEFAULT_METRICS. run_eval calls measure_latency() only under
`--ollama`. Each scenario turn goes through CallbotPipeline.turn(text=...), which records
per-stage latency via the _LatencyLLMProxy (now accumulating all LLM calls within a turn).

HONEST scope notes (reported alongside the numbers):
- text mode has no audio, so ASR latency is 0 — true E2E-with-ASR needs the B14 audio set.
- TTS latency is 0 when no TTS engine is configured (TTS_ENGINE=none / missing binary).
- llm latency comes from the proxy; we never fall back to engine-time (that would mislabel
  engine overhead as LLM time).
"""

from __future__ import annotations

from typing import Any, Callable

from callbot.pipeline import CallbotPipeline

_STAGES = ("asr", "llm", "tts", "engine", "total")


def _percentile(samples: list[float], pct: float) -> float:
    """Linear-interpolation percentile (pct in 0..100). Pure stdlib for unit-testing."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def _summarize(samples: list[float]) -> dict:
    return {
        "p50": round(_percentile(samples, 50), 1),
        "p95": round(_percentile(samples, 95), 1),
        "mean": round(sum(samples) / len(samples), 1) if samples else 0.0,
        "n": len(samples),
    }


def measure_latency(
    scenarios: list[dict[str, Any]],
    *,
    llm_factory: Callable[[], Any] | None = None,
) -> dict:
    """Run every scenario turn through the pipeline (text mode) and aggregate stage latency."""
    if llm_factory is None:
        from callbot.llm.ollama_client import OllamaClient

        llm_factory = OllamaClient

    pipeline = CallbotPipeline.from_dependencies(llm=llm_factory(), include_asr=False)
    tts_name = type(pipeline.tts).__name__ if pipeline.tts is not None else None

    buckets: dict[str, list[float]] = {stage: [] for stage in _STAGES}
    turns_measured = 0
    for scenario in scenarios:
        pipeline.reset()
        for turn in scenario["turns"]:
            result = pipeline.turn(text=turn["user"], play_audio=False)
            buckets["asr"].append(result.asr_latency_ms)
            buckets["llm"].append(result.llm_latency_ms)
            buckets["tts"].append(result.tts_latency_ms)
            buckets["engine"].append(result.engine_latency_ms)
            buckets["total"].append(result.total_latency_ms)
            turns_measured += 1

    notes = [
        "text mode: ASR latency is 0 (no audio) — full ASR E2E needs B14 audio.",
        f"TTS engine: {tts_name or 'none configured (tts latency = 0)'}.",
    ]
    return {
        "name": "latency",
        "status": "ok",
        "turns_measured": turns_measured,
        "stages": {stage: _summarize(buckets[stage]) for stage in _STAGES},
        "notes": notes,
    }

"""Per-turn latency timers (asr/llm/tts ms).

The pipeline already measures each stage and carries the numbers on its turn result; this module
just renders them as one compact line for logs/CLI so a turn's end-to-end latency breakdown is
visible at a glance (brief: "measure and report end-to-end latency per turn").
"""

from __future__ import annotations

from typing import Protocol


class HasLatencies(Protocol):
    asr_latency_ms: float
    llm_latency_ms: float
    tts_latency_ms: float
    engine_latency_ms: float
    total_latency_ms: float


def format_latency(result: HasLatencies) -> str:
    """One-line breakdown: 'asr=.. llm=.. tts=.. engine=.. total=.. ms'."""
    return (
        f"asr={result.asr_latency_ms:.0f} "
        f"llm={result.llm_latency_ms:.0f} "
        f"tts={result.tts_latency_ms:.0f} "
        f"engine={result.engine_latency_ms:.0f} "
        f"total={result.total_latency_ms:.0f} ms"
    )

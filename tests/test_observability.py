"""Logging setup + per-turn latency formatting (observability helpers)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from callbot.utils.latency import format_latency
from callbot.utils.logging import setup_logging


@dataclass
class _Latencies:
    asr_latency_ms: float
    llm_latency_ms: float
    tts_latency_ms: float
    engine_latency_ms: float
    total_latency_ms: float


def test_format_latency_renders_each_stage() -> None:
    line = format_latency(_Latencies(12.4, 800.6, 50.0, 805.0, 870.2))
    assert line == "asr=12 llm=801 tts=50 engine=805 total=870 ms"


def test_setup_logging_is_idempotent(monkeypatch) -> None:
    # Force a fresh state so the test does not depend on import order.
    monkeypatch.setattr("callbot.utils.logging._configured", False)
    calls: list[dict] = []
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: calls.append(kw))

    setup_logging("DEBUG")
    setup_logging("DEBUG")  # second call must be a no-op

    assert len(calls) == 1
    assert calls[0]["level"] == "DEBUG"

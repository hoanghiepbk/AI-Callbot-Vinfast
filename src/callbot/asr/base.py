# FROZEN CONTRACT — changes require both tracks to agree (WORKFLOW §5).
"""ASR interface (Protocol) and result types."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ASRResult(BaseModel):
    text: str
    confidence: float | None = None
    latency_ms: float


@runtime_checkable
class ASR(Protocol):
    def transcribe(self, audio, sample_rate: int = 16000) -> ASRResult: ...

    @classmethod
    def from_file(cls, path: str) -> ASRResult: ...  # for WER eval on .wav

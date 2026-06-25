# FROZEN CONTRACT — changes require both tracks to agree (WORKFLOW §5).
"""TTS interface (Protocol) and result types."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class TTSResult(BaseModel):
    audio: bytes
    latency_ms: float


@runtime_checkable
class TTS(Protocol):
    def synthesize(self, text: str) -> TTSResult: ...

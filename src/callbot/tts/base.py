"""TTS interface (Protocol) and result types."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class TTSResult(BaseModel):
    audio: bytes
    latency_ms: float


class TTS(Protocol):
    def synthesize(self, text: str) -> TTSResult: ...

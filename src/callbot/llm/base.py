"""LLM interface (Protocol) and result types."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class LLMResult(BaseModel):
    text: str
    latency_ms: float


class LLM(Protocol):
    # json_schema set => force structured output (Ollama format mode)
    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult: ...

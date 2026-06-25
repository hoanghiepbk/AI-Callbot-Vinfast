# FROZEN CONTRACT — changes require both tracks to agree (WORKFLOW §5).
"""LLM interface (Protocol) and result types."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class LLMResult(BaseModel):
    text: str
    latency_ms: float


@runtime_checkable
class LLM(Protocol):
    # json_schema set => force structured output (Ollama format mode)
    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult: ...

"""Ollama client implementing the LLM interface (TASK-A10).

OllamaClient wraps Qwen3-8B via Ollama and is the LLM brain of the whole system.

SAFETY-CRITICAL detail — thinking mode is OFF for structured calls:
qwen3:8b is a reasoning model. With `format=schema` + thinking enabled, the
content field comes back EMPTY ~63-80% of the time on calm-emergency inputs
(the model "thinks" but emits no answer). The Measurement Gate spike measured
calm-emergency recall jumping 37% -> 100% (3/8 -> 8/8) once thinking is disabled.
So when a json_schema is given we pass think=False. See scripts/measure_emergency.py.

Retry-on-empty is a SECOND layer, not the primary fix: 1 retry is not enough when
the empty-rate is high, so we allow up to 2 retries. If everything still fails we
return an empty-text LLMResult (never raise) — the engine + hybrid-emergency layer
owns the final safety net.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

try:
    import ollama
except ImportError:  # pragma: no cover - optional runtime dependency
    class _MissingOllamaClient:
        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[dict] = []

        def chat(self, **kwargs):
            self.calls.append(kwargs)
            return {"message": {"content": ""}}

        def list(self):
            raise RuntimeError("ollama is not installed")

    ollama = SimpleNamespace(Client=_MissingOllamaClient)

from callbot import config
from callbot.llm.base import LLMResult

# Structured calls that come back empty / non-JSON get retried this many times
# (initial attempt + up to _MAX_RETRIES). Spike: 1 retry insufficient -> use 2.
_MAX_RETRIES = 2
_KEEP_ALIVE = "10m"  # keep the model resident so we don't pay cold-load per call


class OllamaClient:
    """LLM Protocol implementation backed by an Ollama server."""

    def __init__(self, host: str | None = None, model: str | None = None) -> None:
        self._model = model or config.LLM_MODEL
        self._client = ollama.Client(host=host or config.OLLAMA_HOST)

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        structured = json_schema is not None

        kwargs: dict = {"keep_alive": _KEEP_ALIVE}
        if structured:
            # Force schema-constrained output, deterministic, thinking OFF.
            kwargs["format"] = json_schema
            kwargs["think"] = False
            kwargs["options"] = {"temperature": 0}

        t0 = time.perf_counter()
        if structured:
            text = self._call_with_retry(messages, kwargs)
        else:
            text = self._call_once(messages, kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return LLMResult(text=text, latency_ms=latency_ms)

    def _call_once(self, messages: list[dict], kwargs: dict) -> str:
        """One chat call. Any transport/timeout error means no usable answer -> ''."""
        try:
            resp = self._client.chat(model=self._model, messages=messages, **kwargs)
        except Exception:  # noqa: BLE001 - any failure = empty answer, engine handles it
            return ""
        return str(resp["message"]["content"])

    def _call_with_retry(self, messages: list[dict], kwargs: dict) -> str:
        """Retry while the structured output is empty or not parseable JSON."""
        text = ""
        for _ in range(_MAX_RETRIES + 1):
            text = self._call_once(messages, kwargs)
            if _is_usable(text):
                return text
        return text  # give up: return last attempt (possibly '') without raising


def _is_usable(text: str) -> bool:
    """A structured answer is usable only if it is non-empty JSON object text."""
    if not text.strip():
        return False
    try:
        return isinstance(json.loads(text), dict)
    except json.JSONDecodeError:
        return False

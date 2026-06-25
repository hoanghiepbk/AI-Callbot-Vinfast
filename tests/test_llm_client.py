"""Unit tests for OllamaClient (TASK-A10) — Ollama is mocked, no live server."""

from __future__ import annotations

import json

import pytest

from callbot.llm.ollama_client import OllamaClient
from callbot.models.schemas import NLUResult

_VALID_NLU = {
    "category": "G_1",
    "extracted_fields": {"current_location": "cao tốc Hà Nội Hải Phòng"},
    "corrected_fields": {},
    "signals": {
        "emergency": True,
        "out_of_scope": False,
        "correction": False,
        "hangup": False,
    },
}


def _resp(content: str) -> dict:
    return {"message": {"content": content}}


@pytest.fixture
def fake_chat(monkeypatch):
    """Replace ollama.Client with a stub whose .chat we control; return that stub."""

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[dict] = []
            self.responses: list[dict] = []

        def chat(self, **kwargs):
            self.calls.append(kwargs)
            return self.responses.pop(0)

    stub = _FakeClient()
    monkeypatch.setattr("callbot.llm.ollama_client.ollama.Client", lambda *a, **k: stub)
    return stub


def test_structured_returns_schema_valid_json(fake_chat):
    fake_chat.responses = [_resp(json.dumps(_VALID_NLU))]
    client = OllamaClient()

    result = client.complete("sys", "user", json_schema=NLUResult.model_json_schema())

    nlu = NLUResult.model_validate(json.loads(result.text))  # parses + validates
    assert nlu.category == "G_1"
    assert nlu.signals.emergency is True
    assert result.latency_ms >= 0


def test_think_disabled_and_format_set_for_structured(fake_chat):
    fake_chat.responses = [_resp(json.dumps(_VALID_NLU))]
    schema = NLUResult.model_json_schema()
    client = OllamaClient()

    client.complete("sys", "user", json_schema=schema)

    sent = fake_chat.calls[0]
    assert sent["think"] is False  # SAFETY-CRITICAL: thinking off for structured
    assert sent["format"] == schema
    assert sent["options"]["temperature"] == 0


def test_prose_call_leaves_thinking_default(fake_chat):
    fake_chat.responses = [_resp("một câu trả lời tự do")]
    client = OllamaClient()

    result = client.complete("sys", "user")  # no json_schema

    sent = fake_chat.calls[0]
    assert "think" not in sent  # don't globally disable thinking for prose
    assert "format" not in sent
    assert result.text == "một câu trả lời tự do"


def test_retry_on_empty_then_success(fake_chat):
    fake_chat.responses = [_resp(""), _resp(json.dumps(_VALID_NLU))]
    client = OllamaClient()

    result = client.complete("sys", "user", json_schema=NLUResult.model_json_schema())

    assert len(fake_chat.calls) == 2  # retried once past the empty answer
    assert json.loads(result.text)["category"] == "G_1"


def test_gives_up_after_max_retries_without_raising(fake_chat):
    fake_chat.responses = [_resp(""), _resp(""), _resp("")]  # initial + 2 retries
    client = OllamaClient()

    result = client.complete("sys", "user", json_schema=NLUResult.model_json_schema())

    assert len(fake_chat.calls) == 3  # capped at 1 + _MAX_RETRIES
    assert result.text == ""  # empty, but no exception — engine handles the floor


def test_transport_error_returns_empty(fake_chat, monkeypatch):
    def _boom(**kwargs):
        raise ConnectionError("ollama down")

    monkeypatch.setattr(fake_chat, "chat", _boom)
    client = OllamaClient()

    result = client.complete("sys", "user", json_schema=NLUResult.model_json_schema())

    assert result.text == ""  # failure swallowed, no crash

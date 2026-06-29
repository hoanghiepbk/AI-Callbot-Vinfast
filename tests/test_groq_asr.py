"""GroqASR cloud backend + create_asr factory (no network — httpx.post is faked)."""

from __future__ import annotations

import io
import wave

import httpx
import numpy as np
import pytest

from callbot.asr import create_asr
from callbot.asr.groq_asr import GroqASR, _to_wav_bytes


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def test_to_wav_bytes_is_valid_16k_mono_pcm() -> None:
    audio = np.zeros(16000, dtype=np.float32)

    data = _to_wav_bytes(audio, 16000)

    assert data[:4] == b"RIFF"
    with wave.open(io.BytesIO(data), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000


def test_transcribe_posts_and_parses_text(monkeypatch) -> None:
    captured: dict = {}

    def _fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        captured["has_file"] = "file" in kwargs.get("files", {})
        return _FakeResponse({"text": "  xe em bị chết máy  "})

    monkeypatch.setattr(httpx, "post", _fake_post)

    asr = GroqASR(api_key="test-key")
    result = asr.transcribe(np.zeros(16000, dtype=np.float32), sample_rate=16000)

    assert result.text == "xe em bị chết máy"  # trimmed
    assert result.latency_ms >= 0
    assert captured["url"].endswith("/audio/transcriptions")
    assert captured["data"]["model"] == "whisper-large-v3"
    assert captured["data"]["language"] == "vi"
    assert captured["has_file"]


def test_missing_api_key_raises_clear_error() -> None:
    asr = GroqASR(api_key="")

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        asr.transcribe(np.zeros(1600, dtype=np.float32))


def test_create_asr_selects_groq_without_importing_faster_whisper() -> None:
    asr = create_asr("groq")

    assert isinstance(asr, GroqASR)

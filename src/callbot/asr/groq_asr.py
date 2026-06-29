"""Groq cloud STT — optional fast Vietnamese ASR via whisper-large-v3 (OpenAI-compatible API).

NON-CANONICAL, dev/demo convenience — the same role `edge_tts.py` plays for Piper. The submitted
bot is 100% local (`FasterWhisperASR` + PhoWhisper); this is an opt-in backend (`ASR_ENGINE=groq`)
that removes the local model download and CPU decode latency for quick laptop testing of the live
conversation. It needs `GROQ_API_KEY` (free tier) and internet, so it breaks the offline /
reproducible guarantee and is never the default. WER numbers stay measured on local PhoWhisper.
"""

from __future__ import annotations

import io
import time
import wave
from pathlib import Path

import numpy as np

from callbot import config
from callbot.asr.base import ASRResult

_TRANSCRIBE_PATH = "/audio/transcriptions"


def _to_wav_bytes(audio: np.ndarray | list[float], sample_rate: int) -> bytes:
    """Encode a mono float32 [-1, 1] buffer as 16-bit PCM WAV bytes for upload."""
    samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm16.tobytes())
    return buffer.getvalue()


class GroqASR:
    """ASR adapter backed by Groq's OpenAI-compatible audio transcription endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        language: str = "vi",
    ) -> None:
        self.api_key = api_key if api_key is not None else config.GROQ_API_KEY
        self.model = model or config.GROQ_MODEL
        self.base_url = (base_url or config.GROQ_BASE_URL).rstrip("/")
        self.language = language

    def _post(self, wav_bytes: bytes, filename: str) -> ASRResult:
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set — required for ASR_ENGINE=groq. "
                "Get a free key at https://console.groq.com and put it in .env."
            )
        import httpx

        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}{_TRANSCRIBE_PATH}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": (filename, wav_bytes, "audio/wav")},
            data={"model": self.model, "language": self.language, "response_format": "json"},
            timeout=60.0,
        )
        response.raise_for_status()
        text = (response.json().get("text") or "").strip()
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ASRResult(text=text, latency_ms=latency_ms)

    def transcribe(self, audio: np.ndarray | list[float], sample_rate: int = 16000) -> ASRResult:
        return self._post(_to_wav_bytes(audio, sample_rate), "audio.wav")

    @classmethod
    def from_file(cls, path: str) -> ASRResult:
        instance = cls()
        return instance._post(Path(path).read_bytes(), Path(path).name)

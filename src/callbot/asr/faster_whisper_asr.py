"""PhoWhisper / faster-whisper ASR implementation."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from callbot.asr.base import ASRResult


class FasterWhisperASR:
    """ASR adapter backed by faster-whisper/CTranslate2.

    Heavy model loading is lazy so importing the module does not download or
    initialize model weights. Use a PhoWhisper CT2 model path/name by default,
    with generic faster-whisper model names as a fallback via ASR_MODEL.
    """

    def __init__(
        self,
        model_name: str | None = None,
        *,
        device: str | None = None,
        compute_type: str | None = None,
        language: str = "vi",
    ) -> None:
        self.model_name = model_name or os.getenv("ASR_MODEL", "phowhisper-medium")
        self.device = device or os.getenv("ASR_DEVICE", "cpu")
        self.compute_type = compute_type or os.getenv("ASR_COMPUTE_TYPE", "int8")
        self.language = language
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - depends on optional runtime install
                raise RuntimeError("faster-whisper is required for ASR") from exc

            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(self, audio: np.ndarray | list[float], sample_rate: int = 16000) -> ASRResult:
        started = time.perf_counter()
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if sample_rate != 16000:
            raise ValueError("FasterWhisperASR expects 16 kHz mono audio")

        segments, info = self.model.transcribe(samples, language=self.language, vad_filter=False)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        latency_ms = (time.perf_counter() - started) * 1000
        confidence = getattr(info, "language_probability", None)
        return ASRResult(text=text, confidence=confidence, latency_ms=latency_ms)

    @classmethod
    def from_file(cls, path: str) -> ASRResult:
        started = time.perf_counter()
        instance = cls()
        segments, info = instance.model.transcribe(str(Path(path)), language=instance.language)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        latency_ms = (time.perf_counter() - started) * 1000
        confidence = getattr(info, "language_probability", None)
        return ASRResult(text=text, confidence=confidence, latency_ms=latency_ms)

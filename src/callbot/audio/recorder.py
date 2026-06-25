"""Microphone capture (sounddevice, 16kHz mono)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RecorderConfig:
    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "float32"


class MicrophoneRecorder:
    """Small sounddevice wrapper that returns mono float32 numpy buffers."""

    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RecorderConfig()

    def record_seconds(self, seconds: float) -> np.ndarray:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("sounddevice is required for microphone recording") from exc

        frames = int(self.config.sample_rate * seconds)
        audio = sd.rec(
            frames,
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
        )
        sd.wait()
        return np.asarray(audio, dtype=np.float32).reshape(-1)

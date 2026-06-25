"""Voice-activity detection (silero-vad) for turn segmentation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from callbot.models.schemas import READBACK_REQUIRED


@dataclass(frozen=True)
class VADConfig:
    sample_rate: int = 16000
    threshold: float = 0.01
    frame_ms: int = 30
    silence_ms: int = 700
    numeric_field_silence_ms: int = 1200
    min_speech_ms: int = 120


class EnergyVAD:
    """Dependency-light VAD used as the deterministic fallback for turn cutting."""

    def __init__(self, config: VADConfig | None = None) -> None:
        self.config = config or VADConfig()

    def trim_utterance(self, audio: np.ndarray, *, field_name: str | None = None) -> np.ndarray:
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return samples

        frame_size = max(1, int(self.config.sample_rate * self.config.frame_ms / 1000))
        silence_ms = (
            self.config.numeric_field_silence_ms
            if field_name in READBACK_REQUIRED
            else self.config.silence_ms
        )
        max_silent_frames = max(1, int(silence_ms / self.config.frame_ms))
        min_speech_frames = max(1, int(self.config.min_speech_ms / self.config.frame_ms))

        start: int | None = None
        end = samples.size
        speech_frames = 0
        silent_frames = 0

        for offset in range(0, samples.size, frame_size):
            frame = samples[offset : offset + frame_size]
            is_speech = float(np.sqrt(np.mean(frame * frame))) >= self.config.threshold
            if is_speech:
                if start is None:
                    start = offset
                speech_frames += 1
                silent_frames = 0
                end = min(samples.size, offset + frame_size)
            elif start is not None:
                silent_frames += 1
                if speech_frames >= min_speech_frames and silent_frames >= max_silent_frames:
                    break

        if start is None:
            return np.array([], dtype=np.float32)
        return samples[start:end]


class SileroVAD(EnergyVAD):
    """Placeholder-compatible VAD interface with EnergyVAD fallback.

    The project depends on silero-vad, but the exact runtime helper API has
    changed across releases. EnergyVAD keeps Phase 1 deterministic; a later
    Phase 2 swap can replace `trim_utterance` internals without changing the
    public interface.
    """

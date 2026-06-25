"""Pluggable edge-tts stub.

The project keeps this module as a future swap point, but the reproducible
submission path is Piper/local TTS. The stub raises a clear error if selected.
"""

from __future__ import annotations

from dataclasses import dataclass

from callbot.tts.base import TTSResult


@dataclass
class EdgeTTS:
    def synthesize(self, text: str) -> TTSResult:
        raise RuntimeError("edge-tts is not wired in this phase")

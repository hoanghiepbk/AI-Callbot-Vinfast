"""Pluggable viXTTS stub.

Kept as a future extension point so the TTS factory can stay reversible.
"""

from __future__ import annotations

from dataclasses import dataclass

from callbot.tts.base import TTSResult


@dataclass
class ViXTTS:
    def synthesize(self, text: str) -> TTSResult:
        raise RuntimeError("vixtts is not wired in this phase")

"""ASR package."""

from __future__ import annotations

from callbot import config
from callbot.asr.base import ASR, ASRResult


def create_asr(engine: str | None = None) -> ASR:
    """Create the configured ASR backend.

    "faster_whisper" (default) = local PhoWhisper/Whisper (canonical, offline). "groq" = cloud
    whisper-large-v3 (opt-in dev/demo). Imports are lazy so selecting one never requires the
    other's heavy/optional deps (e.g. faster-whisper need not be installed to use Groq).
    """
    selected = (engine or config.ASR_ENGINE or "faster_whisper").strip().lower()
    if selected in {"groq", "cloud"}:
        from callbot.asr.groq_asr import GroqASR

        return GroqASR()
    if selected in {"", "faster_whisper", "faster-whisper", "local", "phowhisper", "whisper"}:
        from callbot.asr.faster_whisper_asr import FasterWhisperASR

        return FasterWhisperASR()
    raise ValueError(f"Unsupported ASR_ENGINE={selected!r}")


__all__ = ["ASR", "ASRResult", "create_asr"]

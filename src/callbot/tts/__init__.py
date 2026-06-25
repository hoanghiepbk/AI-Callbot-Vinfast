"""TTS package."""

from __future__ import annotations

from callbot import config
from callbot.tts.base import TTS, TTSResult
from callbot.tts.edge_tts import EdgeTTS
from callbot.tts.piper_tts import PiperTTS
from callbot.tts.vixtts import ViXTTS


def create_tts(engine: str | None = None) -> TTS | None:
    """Create the configured TTS engine.

    `none`/`off` returns `None` so the pipeline can run text-only.
    """

    selected = (engine or config.TTS_ENGINE or "piper").strip().lower()
    if selected in {"", "none", "off"}:
        return None
    if selected == "piper":
        return PiperTTS()
    if selected in {"edge", "edge-tts"}:
        return EdgeTTS()
    if selected in {"vix", "vixtts", "vietnamese-tts"}:
        return ViXTTS()
    raise ValueError(f"Unsupported TTS_ENGINE={selected!r}")


__all__ = [
    "EdgeTTS",
    "PiperTTS",
    "TTS",
    "TTSResult",
    "ViXTTS",
    "create_tts",
]

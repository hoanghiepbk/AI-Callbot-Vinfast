"""Voice-mode filler backchannel (pipeline output layer). Offline — no audio/Ollama."""

from __future__ import annotations

from callbot.pipeline import CallbotPipeline
from callbot.tts.base import TTSResult


class _FakeTTS:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text: str) -> TTSResult:
        self.calls.append(text)
        return TTSResult(audio=b"", latency_ms=0.0)  # empty -> no playback thread spawned


def _pipeline(enabled: bool, tts: object | None = None) -> CallbotPipeline:
    # engine is unused by the filler decision, so a stub is fine.
    return CallbotPipeline(engine=object(), tts=tts, filler_enabled=enabled)  # type: ignore[arg-type]


def test_filler_fires_on_voice_turn_when_enabled():
    p = _pipeline(True, _FakeTTS())
    assert p._wants_filler(audio=[0.1, 0.2], effective_play_audio=True) is True


def test_no_filler_when_toggled_off():
    p = _pipeline(False, _FakeTTS())
    assert p._wants_filler(audio=[0.1, 0.2], effective_play_audio=True) is False


def test_no_filler_on_text_fast_turn():
    # Text turn (no audio) skips ASR — already fast, so no backchannel.
    p = _pipeline(True, _FakeTTS())
    assert p._wants_filler(audio=None, effective_play_audio=True) is False


def test_no_filler_without_tts_or_playback():
    assert _pipeline(True, None)._wants_filler(audio=[0.1], effective_play_audio=True) is False
    p = _pipeline(True, _FakeTTS())
    assert p._wants_filler(audio=[0.1], effective_play_audio=False) is False


def test_filler_rotates_variants():
    tts = _FakeTTS()
    p = _pipeline(True, tts)
    assert p._emit_filler() == "Dạ vâng ạ."
    assert p._emit_filler() == "Dạ em nghe ạ."
    assert p._emit_filler() == "Dạ anh/chị chờ em chút ạ."
    assert tts.calls == ["Dạ vâng ạ.", "Dạ em nghe ạ.", "Dạ anh/chị chờ em chút ạ."]

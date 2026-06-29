"""Half-duplex turn-taking for the browser voice-call session (VoiceCallSession).

Drives the session with synthetic mic chunks (no microphone, no Gradio) to exercise the
endpoint -> answer -> mute-while-speaking loop deterministically.
"""

from __future__ import annotations

import io
import wave

import numpy as np

from callbot.asr.base import ASRResult
from callbot.dialogue.fake_engine import FakeDialogueEngine
from callbot.llm.base import LLMResult
from callbot.models.schemas import NormResult
from callbot.pipeline import CallbotPipeline
from callbot.tts.base import TTSResult
from callbot.voice_call import VoiceCallSession

_SR = 16000
_FRAME = _SR * 30 // 1000  # 30 ms frame


def _speech(n_frames: int) -> np.ndarray:
    return np.full(n_frames * _FRAME, 0.1, dtype=np.float32)  # RMS 0.1 >> threshold 0.01


def _silence(n_frames: int) -> np.ndarray:
    return np.zeros(n_frames * _FRAME, dtype=np.float32)


def _utterance() -> np.ndarray:
    # 6 ambient frames (adaptive floor calibration) + 5 speech (confirms onset) + 30 silent
    # (clears the 700 ms window). The bot mutes the mic after speaking, so a real turn likewise
    # opens with background before the caller talks.
    return np.concatenate([_silence(6), _speech(5), _silence(30)])


class _StubNormalizer:
    def normalize_field(self, name: str, raw: str) -> NormResult:
        return NormResult(value=raw, parse_failed=False)


class _StubLLM:
    def complete(self, system: str, user: str, json_schema=None) -> LLMResult:
        return LLMResult(
            text='{"category":"G_3","extracted_fields":{},"corrected_fields":{},'
            '"signals":{"emergency":false,"out_of_scope":false,"correction":false,'
            '"hangup":false}}',
            latency_ms=5.0,
        )


class _StubASR:
    def transcribe(self, audio, sample_rate: int = 16000) -> ASRResult:
        return ASRResult(text="em hoi don hang", confidence=0.9, latency_ms=10.0)


class _StubTTS:
    def synthesize(self, text: str) -> TTSResult:
        samples = np.zeros(_SR // 10, dtype=np.int16)  # 0.1 s of audio
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(_SR)
            wav.writeframes(samples.tobytes())
        return TTSResult(audio=buffer.getvalue(), latency_ms=3.0)


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _pipeline() -> CallbotPipeline:
    engine = FakeDialogueEngine(llm=_StubLLM(), normalizer=_StubNormalizer())
    return CallbotPipeline(engine=engine, asr=_StubASR(), tts=_StubTTS())


def test_silence_chunk_does_not_produce_a_turn() -> None:
    session = VoiceCallSession(_pipeline())
    assert session.feed(_silence(10), _SR) is None


def test_utterance_then_pause_runs_a_turn() -> None:
    session = VoiceCallSession(_pipeline())

    result = session.feed(_utterance(), _SR)

    assert result is not None
    assert result.user_text == "em hoi don hang"  # the utterance was transcribed + answered


def test_mic_is_muted_while_bot_speaks() -> None:
    clock = _Clock()
    session = VoiceCallSession(_pipeline(), now=clock)

    # First utterance -> a turn; ~0.1 s bot audio mutes the mic until ~0.4 s.
    assert session.feed(_utterance(), _SR) is not None
    # Still inside the playback window -> mic ignored (half-duplex, no self-transcription).
    clock.t = 0.2
    assert session.feed(_utterance(), _SR) is None
    # After playback + margin -> listening again, a new utterance runs a turn.
    clock.t = 1.0
    assert session.feed(_utterance(), _SR) is not None


def test_caller_talking_immediately_is_still_heard() -> None:
    # Regression: an earlier fixed calibration window mistook the caller's first words for the
    # noise floor, then never detected speech. With no leading silence (caller talks the instant
    # the mic opens), the utterance must still endpoint and run a turn.
    session = VoiceCallSession(_pipeline())

    result = session.feed(np.concatenate([_speech(5), _silence(30)]), _SR)

    assert result is not None
    assert result.user_text == "em hoi don hang"


def test_long_utterance_without_a_pause_still_answers() -> None:
    # Constant speech with no trailing silence (or a noisy room the VAD can't endpoint): the
    # safety cap must still force a turn so the caller is never left waiting on a silent bot.
    session = VoiceCallSession(_pipeline())

    # 6 ambient frames to calibrate, then > _MAX_UTTERANCE_S (15 s) of unbroken speech.
    long = np.concatenate([_silence(6), _speech(700)])  # 700 frames * 30 ms = 21 s
    result = session.feed(long, _SR)

    assert result is not None
    assert result.user_text == "em hoi don hang"


def test_greet_speaks_first_without_a_user_turn() -> None:
    session = VoiceCallSession(_pipeline())

    greeting = session.greet()

    assert greeting.user_text == ""
    assert greeting.reply_text  # carries the opening line
    assert greeting.reply_audio  # and is spoken

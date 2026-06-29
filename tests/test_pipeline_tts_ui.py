"""Tests for B20-B22 runtime wiring."""

from __future__ import annotations

import io
import wave

import numpy as np

from callbot.asr.base import ASRResult
from callbot.audio.playback import decode_wav_bytes
from callbot.dialogue.fake_engine import FakeDialogueEngine
from callbot.gradio_app import create_demo
from callbot.llm.base import LLMResult
from callbot.models.schemas import NormResult
from callbot.pipeline import CallbotPipeline
from callbot.tts import PiperTTS, create_tts
from callbot.tts.base import TTSResult


class _StubNormalizer:
    def normalize_field(self, name: str, raw: str) -> NormResult:
        return NormResult(value=raw, parse_failed=False)


class _StubLLM:
    def complete(self, system: str, user: str, json_schema=None) -> LLMResult:
        return LLMResult(
            text='{"category":"G_3","extracted_fields":{},"corrected_fields":{},"signals":{"emergency":false,"out_of_scope":false,"correction":false,"hangup":false}}',
            latency_ms=7.5,
        )


class _StubASR:
    def transcribe(self, audio, sample_rate: int = 16000) -> ASRResult:
        return ASRResult(text="xin chao", confidence=0.9, latency_ms=12.0)


class _StrictASR:
    """Mirrors FasterWhisperASR's contract: rejects non-16k audio, records what it received."""

    def __init__(self) -> None:
        self.got_sr: int | None = None
        self.got_dtype = None

    def transcribe(self, audio, sample_rate: int = 16000) -> ASRResult:
        if sample_rate != 16000:
            raise ValueError("FasterWhisperASR expects 16 kHz mono audio")
        self.got_sr = sample_rate
        self.got_dtype = np.asarray(audio).dtype
        return ASRResult(text="ok", confidence=0.9, latency_ms=1.0)


class _StubTTS:
    def synthesize(self, text: str) -> TTSResult:
        samples = np.zeros(22050 // 10, dtype=np.float32)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes((samples * 32767).astype(np.int16).tobytes())
        return TTSResult(audio=buffer.getvalue(), latency_ms=3.0)


def _engine() -> FakeDialogueEngine:
    return FakeDialogueEngine(llm=_StubLLM(), normalizer=_StubNormalizer())


def test_piper_tts_returns_valid_wav_bytes() -> None:
    # No voice installed in CI -> synthesize returns a valid silent WAV (never crashes,
    # never a beep). With a real voice in models/piper/ it returns Vietnamese speech.
    tts = PiperTTS()

    result = tts.synthesize("Xin chao anh/chị")

    assert result.latency_ms >= 0
    assert result.audio[:4] == b"RIFF"
    sample_rate, samples = decode_wav_bytes(result.audio)
    assert sample_rate > 0
    assert samples.size > 0


def test_pipeline_text_turn_and_finalize() -> None:
    pipeline = CallbotPipeline(engine=_engine(), asr=None, tts=_StubTTS())

    turn = pipeline.turn(text="xin chao", play_audio=False)

    assert turn.user_text == "xin chao"
    assert turn.reply_text
    assert turn.asr_latency_ms == 0
    assert turn.tts_latency_ms == 3.0
    assert turn.total_latency_ms >= 0
    assert turn.reply_audio is not None
    assert turn.reply_audio_sample_rate == 22050

    final = pipeline.finalize()
    assert final.post_call.emergency in {"yes", "no"}


def test_pipeline_reset_clears_conversation_state() -> None:
    # What the gradio "Cuộc gọi mới" button triggers: state must not bleed across calls.
    pipeline = CallbotPipeline(engine=_engine(), asr=None, tts=None)

    pipeline.turn(text="xin chao", play_audio=False)
    pipeline.reset()
    turn = pipeline.turn(text="cau hoi moi", play_audio=False)

    # Fresh call: the turn counter restarts at 1 instead of continuing to 2.
    assert turn.state["turn_index"] == 1


def test_pipeline_audio_turn_uses_asr() -> None:
    pipeline = CallbotPipeline(engine=_engine(), asr=_StubASR(), tts=_StubTTS())
    audio = np.zeros(16000, dtype=np.float32)

    turn = pipeline.turn(audio=audio, sample_rate=16000, play_audio=False)

    assert turn.user_text == "xin chao"
    assert turn.asr_latency_ms == 12.0
    assert turn.llm_latency_ms >= 0
    assert turn.reply_audio is not None


def test_prepare_audio_for_asr_resamples_and_normalizes() -> None:
    from callbot.pipeline import _prepare_audio_for_asr

    sr = 48000
    mic = (np.sin(np.linspace(0, 400, sr)) * 16000).astype(np.int16)  # 1s int16 @ 48 kHz

    out = _prepare_audio_for_asr(mic, sr)

    assert out.dtype == np.float32
    assert out.ndim == 1
    assert abs(len(out) - 16000) <= 4  # downsampled 48k -> ~16k samples
    assert float(np.max(np.abs(out))) <= 1.0 + 1e-3  # int16 normalized into [-1, 1]


def test_mic_48k_int16_path_does_not_crash() -> None:
    # The reported demo bug: gradio hands a (48000, int16) tuple; ASR needs 16 kHz float32.
    asr = _StrictASR()
    pipeline = CallbotPipeline(engine=_engine(), asr=asr, tts=None)
    mic = np.zeros(48000, dtype=np.int16)

    turn = pipeline.turn(audio=(48000, mic), play_audio=False)  # gradio numpy-mic tuple

    assert turn.user_text == "ok"
    assert asr.got_sr == 16000  # pipeline resampled before ASR (no ValueError)
    assert asr.got_dtype == np.float32


def test_warmup_pipeline_warms_asr_and_resets_state() -> None:
    from callbot.main import _warmup_pipeline

    asr = _StrictASR()
    pipeline = CallbotPipeline(engine=_engine(), asr=asr, tts=_StubTTS())
    _warmup_pipeline(pipeline)

    assert asr.got_sr == 16000  # ASR was pre-loaded (warmed) at 16 kHz
    # the warm-up turn was discarded -> the next real turn starts the conversation at index 1
    turn = pipeline.turn(text="xin chao", play_audio=False)
    assert turn.state["turn_index"] == 1


def test_edge_tts_synth_is_silence_safe_without_deps() -> None:
    # No edge-tts/internet in CI -> graceful silent WAV, never crashes (like Piper).
    from callbot.tts.edge_tts import EdgeTTS

    result = EdgeTTS().synthesize("Xin chào")
    assert result.audio[:4] == b"RIFF"


def test_tts_factory_and_gradio_factory_are_safe_without_optional_deps() -> None:
    from callbot.tts.edge_tts import EdgeTTS

    assert create_tts("none") is None
    assert isinstance(create_tts("piper"), PiperTTS)
    assert isinstance(create_tts("edge"), EdgeTTS)

    demo = create_demo(pipeline=CallbotPipeline(engine=_engine(), asr=None, tts=_StubTTS()))
    assert (demo.available and demo.blocks is not None) or (
        not demo.available and demo.blocks is None
    )

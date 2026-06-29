"""One-turn pipeline: audio -> ASR -> engine -> TTS, with latency timers."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np
from pydantic import BaseModel

from callbot import config
from callbot.asr.base import ASR
from callbot.audio.playback import play_wav_bytes
from callbot.dialogue import response as tmpl
from callbot.dialogue.engine import DialogueEngine, TurnResult
from callbot.llm.base import LLM
from callbot.models.schemas import FinalOutput
from callbot.normalization.base import Normalizer
from callbot.normalization.vietnamese_numbers import VietnameseNormalizer
from callbot.tts import TTS, create_tts

logger = logging.getLogger(__name__)
_warned_no_soxr = False


def _safe_play(audio: bytes) -> None:
    """Play audio, swallowing any playback error — a filler must never break the turn."""
    try:
        play_wav_bytes(audio)
    except Exception:  # noqa: BLE001 - best-effort backchannel playback
        pass


class _LatencyLLMProxy:
    """Proxy that preserves the LLM protocol and records LLM latency for the turn.

    A single turn may issue more than one LLM call (today nlu=1, but post-call or a
    future re-prompt could add a second). So we ACCUMULATE every call's latency within
    a turn instead of keeping only the last — `start_turn()` zeroes the accumulator at
    the top of each turn and `last_latency_ms` then holds the turn's total LLM time.
    """

    def __init__(self, llm: LLM) -> None:
        self._llm = llm
        self.last_latency_ms = 0.0  # total LLM time within the current turn

    def start_turn(self) -> None:
        """Reset the per-turn accumulator (call at the top of each pipeline turn)."""
        self.last_latency_ms = 0.0

    def complete(self, system: str, user: str, json_schema: dict | None = None):
        result = self._llm.complete(system, user, json_schema)
        self.last_latency_ms += result.latency_ms  # accumulate within the turn
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


def _split_audio_input(
    audio: Any,
    sample_rate: int,
) -> tuple[Any, int]:
    """Accept Gradio-style `(sample_rate, samples)` or raw samples."""

    if isinstance(audio, tuple) and len(audio) == 2:
        first, second = audio
        if isinstance(first, int):
            return second, first
        if isinstance(second, int):
            return first, second
    return audio, sample_rate


def _resample_to_16k(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Resample to 16 kHz for ASR. Prefers soxr (anti-aliased, speech-grade); falls back to
    linear interpolation with a one-time warning when soxr is absent (e.g. the lean CI env)."""
    try:
        import soxr

        return np.asarray(soxr.resample(samples, sample_rate, 16000), dtype=np.float32)
    except ImportError:
        global _warned_no_soxr
        if not _warned_no_soxr:
            logger.warning(
                "soxr not installed; falling back to linear resample (lower quality). "
                'Install with: pip install -e ".[asr]"'
            )
            _warned_no_soxr = True
        n_out = max(1, round(len(samples) * 16000 / sample_rate))
        x_new = np.linspace(0, len(samples) - 1, n_out)
        return np.interp(x_new, np.arange(len(samples)), samples).astype(np.float32)


def _prepare_audio_for_asr(samples: Any, sample_rate: int) -> np.ndarray:
    """Normalize arbitrary mic/file audio to what FasterWhisperASR expects: float32 mono in
    [-1, 1] at 16 kHz. Gradio's Audio(type="numpy") returns int16 at the device's native rate
    (commonly 48 kHz), so we rescale the integer PCM and resample down to 16 kHz."""
    arr = np.asarray(samples)
    if arr.dtype.kind in ("i", "u"):  # int16/int32 PCM (gradio mic) -> float32 [-1, 1]
        arr = arr.astype(np.float32) / float(np.iinfo(arr.dtype).max)
    else:
        arr = arr.astype(np.float32)
    if arr.ndim > 1:  # stereo / multi-channel -> mono
        arr = arr.mean(axis=1)
    if sample_rate != 16000:
        arr = _resample_to_16k(arr, sample_rate)
    return arr


class PipelineTurnResult(BaseModel):
    user_text: str
    reply_text: str
    done: bool
    state: dict[str, Any]
    final_output: FinalOutput | None = None
    reply_audio: bytes | None = None
    reply_audio_sample_rate: int | None = None
    asr_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    tts_latency_ms: float = 0.0
    engine_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    filler_text: str | None = None  # backchannel played this turn (voice mode), if any


class CallbotPipeline:
    """Reusable runtime that wires ASR -> DialogueEngine -> TTS."""

    def __init__(
        self,
        *,
        engine: DialogueEngine,
        asr: ASR | None = None,
        tts: TTS | None = None,
        llm_proxy: _LatencyLLMProxy | None = None,
        default_sample_rate: int = 16000,
        auto_play: bool = False,
        filler_enabled: bool | None = None,
    ) -> None:
        self.engine = engine
        self.asr = asr
        self.tts = tts
        self._llm_proxy = llm_proxy
        self.default_sample_rate = default_sample_rate
        self.auto_play = auto_play
        self._filler_enabled = config.VOICE_FILLER if filler_enabled is None else filler_enabled
        self._filler_index = 0
        self._filler_cache: dict[str, bytes] = {}  # fixed filler set -> synthesize each once

    @classmethod
    def from_dependencies(
        cls,
        *,
        asr: ASR | None = None,
        llm: LLM | None = None,
        normalizer: Normalizer | None = None,
        tts: TTS | None = None,
        include_asr: bool = True,
        default_sample_rate: int = 16000,
        auto_play: bool = False,
    ) -> "CallbotPipeline":
        if llm is None:
            from callbot.llm.ollama_client import OllamaClient

            llm = OllamaClient()
        normalizer = normalizer or VietnameseNormalizer()
        proxy = _LatencyLLMProxy(llm)
        engine = DialogueEngine(proxy, normalizer)
        if include_asr and asr is None:
            from callbot.asr.faster_whisper_asr import FasterWhisperASR

            asr = FasterWhisperASR()
        return cls(
            engine=engine,
            asr=asr if include_asr else None,
            tts=tts if tts is not None else create_tts(),
            llm_proxy=proxy,
            default_sample_rate=default_sample_rate,
            auto_play=auto_play,
        )

    @classmethod
    def from_env(
        cls,
        *,
        include_asr: bool = True,
        auto_play: bool = False,
        default_sample_rate: int = 16000,
    ) -> "CallbotPipeline":
        return cls.from_dependencies(
            include_asr=include_asr,
            auto_play=auto_play,
            default_sample_rate=default_sample_rate,
        )

    def turn(
        self,
        audio: Any | None = None,
        *,
        text: str | None = None,
        sample_rate: int | None = None,
        play_audio: bool | None = None,
    ) -> PipelineTurnResult:
        """Process one caller turn from audio or text."""

        started = time.perf_counter()
        sr = sample_rate or self.default_sample_rate
        user_text = text
        asr_latency_ms = 0.0
        effective_play_audio = self.auto_play if play_audio is None else play_audio

        # Backchannel: a voice turn is about to pay ASR+LLM latency. Play a fixed filler NOW
        # (async, deterministic, no LLM) so the caller perceives an instant reply.
        filler_text: str | None = None
        if self._wants_filler(audio, effective_play_audio):
            filler_text = self._emit_filler()

        if self._llm_proxy is not None:
            self._llm_proxy.start_turn()  # reset per-turn LLM accumulator

        if user_text is None:
            if audio is None:
                raise ValueError("turn() requires either audio or text")
            if self.asr is None:
                raise RuntimeError("ASR is not configured")
            audio_data, sr = _split_audio_input(audio, sr)
            # Gradio/mic audio is int16 at the device rate (e.g. 48 kHz); ASR needs float32
            # mono @ 16 kHz, so normalize + resample here (the seam both UI and voice share).
            audio_16k = _prepare_audio_for_asr(audio_data, sr)
            asr_result = self.asr.transcribe(audio_16k, sample_rate=16000)
            user_text = asr_result.text
            asr_latency_ms = asr_result.latency_ms
            if not (user_text or "").strip():
                # ASR filtered out non-speech (silence/background noise) — skip the engine
                # entirely so a stray noise turn cannot trip the stuck-escalation. The caller
                # (voice loop) sees empty user_text and simply keeps listening.
                return PipelineTurnResult(
                    user_text="",
                    reply="",
                    done=False,
                    state={},
                    asr_latency_ms=asr_latency_ms,
                    total_latency_ms=(time.perf_counter() - started) * 1000.0,
                )

        process_started = time.perf_counter()
        turn_result: TurnResult = self.engine.process(user_text or "")
        engine_latency_ms = (time.perf_counter() - process_started) * 1000.0

        llm_latency_ms = (
            self._llm_proxy.last_latency_ms if self._llm_proxy is not None else engine_latency_ms
        )

        reply_audio: bytes | None = None
        reply_audio_sample_rate: int | None = None
        tts_latency_ms = 0.0
        if self.tts is not None:
            tts_result = self.tts.synthesize(turn_result.reply)
            reply_audio = tts_result.audio
            reply_audio_sample_rate = _detect_wav_sample_rate(reply_audio)
            tts_latency_ms = tts_result.latency_ms
            if effective_play_audio and reply_audio:
                play_wav_bytes(reply_audio)

        final_output = self.engine.finalize() if turn_result.done else None
        total_latency_ms = (time.perf_counter() - started) * 1000.0
        return PipelineTurnResult(
            user_text=user_text or "",
            reply_text=turn_result.reply,
            done=turn_result.done,
            state=turn_result.state,
            final_output=final_output,
            reply_audio=reply_audio,
            reply_audio_sample_rate=reply_audio_sample_rate,
            asr_latency_ms=asr_latency_ms,
            llm_latency_ms=llm_latency_ms,
            tts_latency_ms=tts_latency_ms,
            engine_latency_ms=engine_latency_ms,
            total_latency_ms=total_latency_ms,
            filler_text=filler_text,
        )

    def _wants_filler(self, audio: Any | None, effective_play_audio: bool) -> bool:
        """Filler only for voice turns (audio input → real ASR+LLM wait), when enabled and we
        are actually playing audio out. Text turns skip the slow path, so no filler."""
        return bool(
            self._filler_enabled
            and effective_play_audio
            and audio is not None
            and self.tts is not None
        )

    def _emit_filler(self) -> str:
        """Play the next rotating filler in the background (non-blocking).

        The filler set is fixed (a 3-variant rotation), so each unique clip is synthesized
        once and cached — later turns reuse the bytes instead of paying TTS again, which
        matters for cloud TTS where re-synthesizing would add latency ahead of ASR.
        """
        text = tmpl.filler(self._filler_index)
        self._filler_index += 1
        assert self.tts is not None  # guarded by _wants_filler
        audio = self._filler_cache.get(text)
        if audio is None:
            audio = self.tts.synthesize(text).audio
            self._filler_cache[text] = audio
        if audio:
            threading.Thread(target=_safe_play, args=(audio,), daemon=True).start()
        return text

    def finalize(self) -> FinalOutput:
        return self.engine.finalize()

    def reset(self) -> None:
        self.engine.reset()


def _detect_wav_sample_rate(audio: bytes | None) -> int | None:
    if not audio:
        return None
    try:
        import io
        import wave

        with wave.open(io.BytesIO(audio), "rb") as wav:
            return wav.getframerate()
    except Exception:  # noqa: BLE001
        return None

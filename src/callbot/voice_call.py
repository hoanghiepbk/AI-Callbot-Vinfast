"""Server-side state for the browser voice-call ('Gọi điện') mode.

Drives a hands-free, half-duplex phone-call loop on top of the existing pipeline: streamed
mic chunks are fed in, an energy-VAD endpoints each utterance on a trailing pause, the pipeline
answers, and the bot's audio plays back while the mic is muted so the bot never transcribes its
own voice. UI-agnostic, so the turn-taking is unit-testable without Gradio.
"""

from __future__ import annotations

import io
import time
import wave
from typing import Any, Callable

import numpy as np

from callbot.audio.stream import VadEndpointer
from callbot.audio.vad import VADConfig
from callbot.pipeline import CallbotPipeline, PipelineTurnResult, _prepare_audio_for_asr

# Bot speaks first, like a real call being answered.
GREETING = "Dạ VinFast xin nghe, em có thể hỗ trợ gì cho mình ạ?"

# Extra quiet after the bot's audio before the mic is live again, so the tail of playback (or
# its echo through speakers) is not captured as the next utterance.
_MUTE_MARGIN_S = 0.3

# Safety cap: if the energy-VAD never sees a trailing pause (e.g. constant background noise), the
# turn would accumulate forever and the bot would never answer. Force the turn after this long.
_MAX_UTTERANCE_S = 15.0


def _wav_info(audio: bytes | None) -> tuple[float, int | None]:
    """Return (duration_seconds, sample_rate) of a WAV blob; (0.0, None) if empty/invalid."""
    if not audio:
        return 0.0, None
    try:
        with wave.open(io.BytesIO(audio)) as wav:
            rate = wav.getframerate()
            return wav.getnframes() / float(rate or 1), rate
    except (wave.Error, EOFError):
        return 0.0, None


class VoiceCallSession:
    """Half-duplex phone-call turn-taking over a pushed mic stream.

    Feed streamed mic chunks via :meth:`feed`; when an utterance endpoints, the pipeline
    answers and the result is returned for playback. While the bot's audio plays, incoming mic
    chunks are dropped (half-duplex) so the bot does not transcribe itself. One session holds
    one call's state; :meth:`reset` starts a fresh call.
    """

    def __init__(
        self, pipeline: CallbotPipeline, *, now: Callable[[], float] = time.perf_counter
    ) -> None:
        self.pipeline = pipeline
        self._now = now
        self._vad_config = VADConfig()
        self._endpointer = VadEndpointer(self._vad_config, adaptive=True)
        self._leftover = np.empty(0, dtype=np.float32)
        self._muted_until = 0.0
        self._max_utt_frames = max(1, int(_MAX_UTTERANCE_S * 1000 / self._vad_config.frame_ms))
        self._utt_frames = 0

    def greet(self) -> PipelineTurnResult:
        """Bot's opening line, spoken first. No user turn is run."""
        audio = self._synthesize(GREETING)
        self._mute_for(audio)
        _, sr = _wav_info(audio)
        return PipelineTurnResult(
            user_text="",
            reply_text=GREETING,
            done=False,
            state={},
            reply_audio=audio,
            reply_audio_sample_rate=sr,
        )

    def feed(self, samples: Any, sample_rate: int) -> PipelineTurnResult | None:
        """Process one streamed mic chunk; return a turn result when an utterance ends."""
        if self._now() < self._muted_until:
            return None  # bot is speaking — half-duplex, ignore the mic
        chunk = _prepare_audio_for_asr(samples, sample_rate)  # mono float32 @ 16 kHz
        if chunk.size == 0:
            return None
        self._leftover = np.concatenate([self._leftover, chunk]) if self._leftover.size else chunk

        utterance: np.ndarray | None = None
        frame_size = self._endpointer.frame_size
        while self._leftover.size >= frame_size:
            frame = self._leftover[:frame_size]
            self._leftover = self._leftover[frame_size:]
            utterance = self._endpointer.push_frame(frame)
            if utterance is None and self._endpointer.started:
                self._utt_frames += 1
                if self._utt_frames >= self._max_utt_frames:
                    utterance = self._endpointer.flush()  # VAD missed the pause — force the turn
            if utterance is not None:
                break
        if utterance is None:
            return None
        self._utt_frames = 0

        result = self.pipeline.turn(audio=utterance, sample_rate=16000, play_audio=False)
        if not result.user_text.strip():
            return None  # ASR filtered noise/silence — keep listening, no turn
        self._mute_for(result.reply_audio)
        # Arm the longer silence window when the next field is a read-back number, so a
        # mid-number pause does not cut the caller off; also drop any audio buffered mid-turn.
        next_field = result.state.get("current_field") or result.state.get("pending_field")
        self._endpointer = VadEndpointer(self._vad_config, field_name=next_field, adaptive=True)
        self._leftover = np.empty(0, dtype=np.float32)
        self._utt_frames = 0
        return result

    def reset(self) -> None:
        """Start a fresh call: wipe the pipeline conversation + endpointing state."""
        self.pipeline.reset()
        self._endpointer = VadEndpointer(self._vad_config, adaptive=True)
        self._leftover = np.empty(0, dtype=np.float32)
        self._muted_until = 0.0
        self._utt_frames = 0

    def _synthesize(self, text: str) -> bytes | None:
        if self.pipeline.tts is None:
            return None
        try:
            return self.pipeline.tts.synthesize(text).audio
        except Exception:  # noqa: BLE001 - greeting audio is best-effort
            return None

    def _mute_for(self, audio: bytes | None) -> None:
        duration, _ = _wav_info(audio)
        self._muted_until = self._now() + duration + _MUTE_MARGIN_S

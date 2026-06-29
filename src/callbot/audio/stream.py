"""Continuous mic capture with VAD endpointing for real-time turn-taking.

The fixed-window recorder (`MicrophoneRecorder.record_seconds`) forces the caller
to fit each turn into a rigid N-second clip — a walkie-talkie, not a phone call.
This module opens a *continuous* input stream and uses energy-based VAD to detect
when the caller starts and stops speaking, so a turn ends naturally on a trailing
pause. The dialogue loop just calls `listen_utterance()` once per turn.

Half-duplex by design: the stream is only open while we are listening. While the
bot is speaking (TTS playback), no stream is open, so the bot never transcribes
its own voice. Barge-in (interrupting the bot) is intentionally out of scope.
"""

from __future__ import annotations

import queue
import time
from collections import deque

import numpy as np

from callbot import config
from callbot.audio.recorder import RecorderConfig
from callbot.audio.vad import VADConfig
from callbot.models.schemas import READBACK_REQUIRED

# Audio kept BEFORE a confirmed speech onset so a soft word-initial consonant (h/ph/x/s) is
# not clipped when collection starts. ~150 ms covers a typical onset.
_PREROLL_MS = 150

# Adaptive endpointing (browser voice-call only). A browser mic with AGC has a noise floor that can
# sit ABOVE the fixed 0.01 threshold, so every frame reads as speech and the turn never ends -> the
# bot never answers. In adaptive mode the ambient floor is estimated as the quietest frame in a
# rolling window and speech must clear it by _NOISE_SPEECH_FACTOR, capped at _NOISE_RMS_MAX so even
# a noisy mic can't lift the bar above normal speech. There is no blocking calibration window, so a
# caller who starts talking the instant the mic opens is still heard (a fixed calibration window
# mistook those first words for the noise floor and then never detected any speech).
_NOISE_WINDOW_MS = 1500
_NOISE_SPEECH_FACTOR = 2.2
_NOISE_RMS_MAX = 0.04


class VadEndpointer:
    """Frame-by-frame energy-VAD endpointing state machine.

    Shared by the CLI pull-loop (`StreamingMicrophone`, reading frames off a sounddevice
    stream) and the browser push-stream (the Gradio voice-call tab, feeding frames decoded
    from streamed mic chunks). Feed mono float32 frames of ``frame_size`` samples via
    :meth:`push_frame`; it returns the captured utterance the moment speech is followed by a
    trailing pause, else ``None``, and auto-resets so the same instance handles the next turn.

    A candidate onset must reach ``min_speech_frames`` CONSECUTIVE speech frames to confirm (so
    a transient click never arms a capture), and a ``_PREROLL_MS`` ring buffer is prepended so a
    soft word-initial consonant is not clipped. ``field_name`` arms the longer numeric-field
    silence window for read-back fields (phone/plate/VIN). ``adaptive`` calibrates the speech
    threshold to the ambient noise floor (used by the browser voice-call, where a fixed threshold
    is too low for an AGC mic and the turn would never end).
    """

    def __init__(
        self,
        vad_config: VADConfig | None = None,
        *,
        field_name: str | None = None,
        adaptive: bool = False,
    ) -> None:
        cfg = vad_config or VADConfig()
        self.frame_size = max(1, int(cfg.sample_rate * cfg.frame_ms / 1000))
        self.threshold = cfg.threshold
        # Keep the cfg-derived silence windows so rearm() can switch between them per turn.
        self._frame_ms = cfg.frame_ms
        self._default_silence_ms = cfg.silence_ms
        self._numeric_silence_ms = cfg.numeric_field_silence_ms
        silence_ms = (
            cfg.numeric_field_silence_ms if field_name in READBACK_REQUIRED else cfg.silence_ms
        )
        self.max_silent_frames = max(1, int(silence_ms / cfg.frame_ms))
        self.min_speech_frames = max(1, int(cfg.min_speech_ms / cfg.frame_ms))
        self.preroll_frames = max(1, int(_PREROLL_MS / cfg.frame_ms))
        self.adaptive = adaptive
        self.noise_window = max(1, int(_NOISE_WINDOW_MS / cfg.frame_ms))
        self.reset()

    def reset(self) -> None:
        """Full reset for a NEW call — also forgets the ambient-noise estimate."""
        self._reset_utterance()
        self._recent_rms: deque[float] = deque(maxlen=self.noise_window)

    def _reset_utterance(self) -> None:
        """Reset only the per-utterance capture state; the rolling noise estimate is KEPT so
        adaptive calibration carries across consecutive turns (see :meth:`rearm`)."""
        self.started = False
        self._preroll: deque[np.ndarray] = deque(maxlen=self.preroll_frames)
        self._candidate: list[np.ndarray] = []
        self._collected: list[np.ndarray] = []
        self._pending_speech = 0
        self._silent_frames = 0

    def rearm(self, field_name: str | None = None) -> None:
        """Ready the endpointer for the next turn of the SAME call: switch the silence window
        to ``field_name``'s (longer for read-back numbers) and clear capture state, but PRESERVE
        the ambient-noise calibration so an AGC mic does not re-converge from scratch each turn."""
        numeric = field_name in READBACK_REQUIRED
        silence_ms = self._numeric_silence_ms if numeric else self._default_silence_ms
        self.max_silent_frames = max(1, int(silence_ms / self._frame_ms))
        self._reset_utterance()

    def _speech_floor(self) -> float:
        """Energy a frame must clear to count as speech: the fixed threshold, or the rolling
        ambient-noise floor (quietest recent frame) scaled up, whichever is higher."""
        if not self.adaptive or not self._recent_rms:
            return self.threshold
        noise = min(min(self._recent_rms), _NOISE_RMS_MAX)
        return max(self.threshold, noise * _NOISE_SPEECH_FACTOR)

    def push_frame(self, frame: np.ndarray) -> np.ndarray | None:
        """Process one ``frame_size`` frame; return the utterance when it ends, else None."""
        rms = float(np.sqrt(np.mean(frame * frame)))
        if self.adaptive:
            self._recent_rms.append(rms)  # rolling ambient-floor estimate (quietest recent frame)
        is_speech = rms >= self._speech_floor()

        if not self.started:
            if is_speech:
                self._candidate.append(frame)
                self._pending_speech += 1
                if self._pending_speech >= self.min_speech_frames:
                    # Confirmed onset: prepend the pre-roll so the quiet lead-in of the first
                    # word is not clipped.
                    self.started = True
                    self._collected = list(self._preroll) + self._candidate
                    self._silent_frames = 0
            else:
                # Candidate run broke before confirming -> a transient, not speech. Drop it and
                # keep waiting (no false capture, no hang).
                self._candidate.clear()
                self._pending_speech = 0
                self._preroll.append(frame)
            return None

        self._collected.append(frame)
        if is_speech:
            self._silent_frames = 0
        else:
            self._silent_frames += 1
            if self._silent_frames >= self.max_silent_frames:
                return self._flush()
        return None

    def flush(self) -> np.ndarray | None:
        """Force-return any collected speech (e.g. on a wall-clock cap), then reset."""
        return self._flush() if self.started and self._collected else None

    def _flush(self) -> np.ndarray:
        utterance = np.concatenate(self._collected)
        self._reset_utterance()  # keep the noise estimate for the next utterance of this call
        return utterance


class StreamingMicrophone:
    """Continuous mic + energy VAD endpointing.

    `listen_utterance()` blocks until one full utterance (speech followed by a
    trailing silence) is captured, then returns the mono float32 buffer. Reuses
    `VADConfig` thresholds so endpointing matches the batch VAD used elsewhere,
    including the longer silence window for read-back numeric fields.
    """

    def __init__(
        self,
        recorder_config: RecorderConfig | None = None,
        vad_config: VADConfig | None = None,
        gain: float | None = None,
    ) -> None:
        self.recorder_config = recorder_config or RecorderConfig()
        self.vad_config = vad_config or VADConfig()
        self.gain = config.MIC_GAIN if gain is None else gain

    def listen_utterance(
        self,
        *,
        field_name: str | None = None,
        max_wait_seconds: float = 20.0,
        max_utterance_seconds: float = 20.0,
    ) -> np.ndarray | None:
        """Capture one utterance.

        Returns the float32 buffer for the utterance, or ``None`` if no speech
        started within ``max_wait_seconds`` (pure silence — caller can loop).

        ``field_name`` arms the longer numeric-field silence window when the bot
        is waiting on a phone/plate/VIN, so a mid-number pause does not cut the
        caller off (mirrors `EnergyVAD` / READBACK_REQUIRED).
        """
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("sounddevice is required for microphone capture") from exc

        endpointer = VadEndpointer(self.vad_config, field_name=field_name)
        frame_size = endpointer.frame_size

        frames: "queue.Queue[np.ndarray]" = queue.Queue()

        def _callback(indata, _frames, _time_info, _status) -> None:  # noqa: ANN001
            frames.put(np.asarray(indata, dtype=np.float32).reshape(-1).copy())

        leftover = np.empty(0, dtype=np.float32)
        wall_start = time.perf_counter()

        with sd.InputStream(
            samplerate=self.recorder_config.sample_rate,
            channels=self.recorder_config.channels,
            dtype=self.recorder_config.dtype,
            blocksize=frame_size,
            callback=_callback,
        ):
            while True:
                try:
                    block = frames.get(timeout=0.1)
                    leftover = np.concatenate([leftover, block]) if leftover.size else block
                except queue.Empty:
                    pass

                while leftover.size >= frame_size:
                    frame = leftover[:frame_size]
                    leftover = leftover[frame_size:]
                    if self.gain != 1.0:
                        # Boost quiet mics so speech clears the VAD threshold and ASR gets a
                        # healthy level; clip to keep the buffer in valid [-1, 1] float range.
                        frame = np.clip(frame * self.gain, -1.0, 1.0)
                    utterance = endpointer.push_frame(frame)
                    if utterance is not None:
                        return utterance

                elapsed = time.perf_counter() - wall_start
                if not endpointer.started and elapsed >= max_wait_seconds:
                    return None
                # Wall-clock safety cap: never hang on a runaway turn or a dead mic.
                if endpointer.started and elapsed >= max_utterance_seconds:
                    return endpointer.flush()

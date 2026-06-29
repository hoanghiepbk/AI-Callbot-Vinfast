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

        sr = self.recorder_config.sample_rate
        frame_ms = self.vad_config.frame_ms
        frame_size = max(1, int(sr * frame_ms / 1000))
        threshold = self.vad_config.threshold
        silence_ms = (
            self.vad_config.numeric_field_silence_ms
            if field_name in READBACK_REQUIRED
            else self.vad_config.silence_ms
        )
        max_silent_frames = max(1, int(silence_ms / frame_ms))
        min_speech_frames = max(1, int(self.vad_config.min_speech_ms / frame_ms))
        preroll_frames = max(1, int(_PREROLL_MS / frame_ms))

        frames: "queue.Queue[np.ndarray]" = queue.Queue()

        def _callback(indata, _frames, _time_info, _status) -> None:  # noqa: ANN001
            frames.put(np.asarray(indata, dtype=np.float32).reshape(-1).copy())

        collected: list[np.ndarray] = []
        leftover = np.empty(0, dtype=np.float32)
        # Pre-onset state: a candidate run must reach min_speech_frames CONSECUTIVE speech
        # frames to confirm a real onset — a transient (click/keystroke) never does, so it can
        # no longer arm a capture that then hangs until the wall-clock cap.
        preroll: "deque[np.ndarray]" = deque(maxlen=preroll_frames)
        candidate: list[np.ndarray] = []
        pending_speech = 0
        started = False
        silent_frames = 0
        wall_start = time.perf_counter()

        with sd.InputStream(
            samplerate=sr,
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
                    is_speech = float(np.sqrt(np.mean(frame * frame))) >= threshold

                    if not started:
                        if is_speech:
                            candidate.append(frame)
                            pending_speech += 1
                            if pending_speech >= min_speech_frames:
                                # Confirmed onset: prepend the pre-roll so the quiet lead-in of
                                # the first word is not clipped.
                                started = True
                                collected = list(preroll) + candidate
                                silent_frames = 0
                        else:
                            # Candidate run broke before confirming -> a transient, not speech.
                            # Drop it and keep waiting (no false capture, no 20s hang).
                            candidate.clear()
                            pending_speech = 0
                            preroll.append(frame)
                        continue

                    collected.append(frame)
                    if is_speech:
                        silent_frames = 0
                    else:
                        silent_frames += 1
                        if silent_frames >= max_silent_frames:
                            return np.concatenate(collected)

                elapsed = time.perf_counter() - wall_start
                if not started and elapsed >= max_wait_seconds:
                    return None
                # Wall-clock safety cap: never hang on a runaway turn or a dead mic.
                if started and elapsed >= max_utterance_seconds:
                    return np.concatenate(collected)

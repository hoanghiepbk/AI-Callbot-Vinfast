"""Endpointing logic for the real-time voice loop (StreamingMicrophone).

The mic stream needs hardware, so we inject a fake `sounddevice` module whose
InputStream replays pre-baked frames into the VAD callback. This exercises the
speech/silence state machine deterministically, without a microphone.
"""

from __future__ import annotations

import sys
import types

import numpy as np

from callbot.audio.stream import StreamingMicrophone, VadEndpointer

_SR = 16000
_FRAME = _SR * 30 // 1000  # 30 ms frame = 480 samples


def _speech(n_frames: int) -> np.ndarray:
    # RMS 0.1 >> default VAD threshold 0.01 → counts as speech.
    return np.full(n_frames * _FRAME, 0.1, dtype=np.float32)


def _silence(n_frames: int) -> np.ndarray:
    return np.zeros(n_frames * _FRAME, dtype=np.float32)


def _level(n_frames: int, rms: float) -> np.ndarray:
    return np.full(n_frames * _FRAME, rms, dtype=np.float32)


def _feed_endpointer(endpointer: VadEndpointer, audio: np.ndarray) -> np.ndarray | None:
    """Push an audio buffer through an endpointer frame-by-frame; return the captured utterance."""
    captured = None
    for offset in range(0, audio.size, _FRAME):
        frame = audio[offset : offset + _FRAME]
        if frame.size == _FRAME:
            result = endpointer.push_frame(frame)
            if result is not None:
                captured = result
    return captured


def _install_fake_sd(monkeypatch, audio: np.ndarray) -> None:
    module = types.ModuleType("sounddevice")

    class _FakeInputStream:
        def __init__(self, *, callback, **_kwargs):
            self._callback = callback

        def __enter__(self):
            self._callback(audio.reshape(-1, 1), audio.size, None, None)
            return self

        def __exit__(self, *_exc):
            return False

    module.InputStream = _FakeInputStream  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sounddevice", module)


def test_endpoints_on_trailing_silence(monkeypatch):
    # 5 speech frames (>min_speech) then 30 silent frames (>700ms window).
    audio = np.concatenate([_speech(5), _silence(30)])
    _install_fake_sd(monkeypatch, audio)

    utterance = StreamingMicrophone(gain=1.0).listen_utterance(max_wait_seconds=2.0)

    assert utterance is not None
    # Captured buffer starts at speech and ends once the silence window is hit.
    assert utterance.size >= 5 * _FRAME


def test_pure_silence_returns_none(monkeypatch):
    _install_fake_sd(monkeypatch, _silence(3))

    utterance = StreamingMicrophone(gain=1.0).listen_utterance(max_wait_seconds=0.3)

    assert utterance is None


def test_transient_noise_does_not_arm_capture(monkeypatch):
    # A 2-frame click (< min_speech = 4 frames) then silence must NOT start a capture.
    # Regression: a single loud frame armed `started`, which then never endpointed and hung
    # until the 20s wall-clock cap. The candidate must be discarded -> treated as silence.
    audio = np.concatenate([_speech(2), _silence(20)])
    _install_fake_sd(monkeypatch, audio)

    utterance = StreamingMicrophone(gain=1.0).listen_utterance(max_wait_seconds=0.3)

    assert utterance is None


def test_preroll_keeps_quiet_onset(monkeypatch):
    # 3 sub-threshold frames (a soft word onset), then speech. The capture must prepend the
    # pre-roll so it begins BEFORE the first above-threshold frame, not clip the onset.
    quiet = np.full(3 * _FRAME, 0.002, dtype=np.float32)  # RMS 0.002 < threshold 0.01
    audio = np.concatenate([quiet, _speech(5), _silence(30)])
    _install_fake_sd(monkeypatch, audio)

    utterance = StreamingMicrophone(gain=1.0).listen_utterance(max_wait_seconds=2.0)

    assert utterance is not None
    # The buffer opens with the quiet lead-in (pre-roll), not with speech-level energy.
    assert float(np.max(np.abs(utterance[:_FRAME]))) < 0.01


def test_fixed_threshold_hangs_on_a_noisy_floor():
    # A mic whose ambient floor (RMS 0.04) sits ABOVE the fixed 0.01 threshold: every frame reads
    # as speech, so the trailing 'pause' never registers and the turn never ends. This is the
    # browser bug the adaptive mode fixes — documented here as the contrast case.
    audio = np.concatenate([_level(6, 0.04), _level(8, 0.2), _level(30, 0.04)])

    assert _feed_endpointer(VadEndpointer(adaptive=False), audio) is None


def test_adaptive_endpoints_above_the_noise_floor():
    # Same noisy mic: adaptive calibration lifts the speech bar above the 0.04 ambient floor, so
    # real speech (0.2) is captured and the return to ambient ends the turn — the bot can answer.
    audio = np.concatenate([_level(6, 0.04), _level(8, 0.2), _level(30, 0.04)])

    utterance = _feed_endpointer(VadEndpointer(adaptive=True), audio)

    assert utterance is not None
    assert utterance.size >= 8 * _FRAME


def _ambient(endpointer: VadEndpointer, n: int, rms: float = 0.03) -> None:
    for _ in range(n):
        endpointer.push_frame(np.full(endpointer.frame_size, rms, dtype=np.float32))


def test_rearm_preserves_noise_calibration_but_resets_capture():
    # The browser AGC mic calibrates an ambient-noise floor over a few frames. rearm() (used
    # between turns) must KEEP that calibration so the floor does not re-converge each turn,
    # while clearing the per-utterance capture state.
    endpointer = VadEndpointer(adaptive=True)
    _ambient(endpointer, 6)
    assert endpointer._recent_rms  # calibration accumulated
    floor_before = endpointer._speech_floor()

    endpointer.rearm("phone")

    assert endpointer.started is False  # capture state cleared
    assert endpointer._recent_rms  # but the noise estimate is kept
    assert endpointer._speech_floor() == floor_before  # same calibration carried forward


def test_rearm_switches_silence_window_per_field():
    endpointer = VadEndpointer(adaptive=True)
    default_frames = endpointer.max_silent_frames

    endpointer.rearm("phone")  # a read-back numeric field -> longer silence window
    assert endpointer.max_silent_frames > default_frames

    endpointer.rearm("full_name")  # ordinary field -> back to the default window
    assert endpointer.max_silent_frames == default_frames


def test_reset_clears_noise_calibration():
    # A NEW call (reset) must forget the previous call's ambient estimate.
    endpointer = VadEndpointer(adaptive=True)
    _ambient(endpointer, 4)
    assert endpointer._recent_rms

    endpointer.reset()

    assert not endpointer._recent_rms


def test_readback_field_uses_longer_silence_window(monkeypatch):
    # 5 speech frames + a 900ms pause (30 frames). The default 700ms window would
    # endpoint here and cut the buffer short; the numeric read-back window (1200ms)
    # must NOT — so the read-back capture keeps the whole (longer) buffer.
    audio = np.concatenate([_speech(5), _silence(30)])

    _install_fake_sd(monkeypatch, audio)
    default_capture = StreamingMicrophone(gain=1.0).listen_utterance(max_wait_seconds=2.0)

    _install_fake_sd(monkeypatch, audio)
    readback_capture = StreamingMicrophone(gain=1.0).listen_utterance(
        field_name="phone", max_wait_seconds=2.0, max_utterance_seconds=0.4
    )

    assert default_capture is not None and readback_capture is not None
    # Read-back field tolerates the mid-number pause → captures more than the default cut.
    assert readback_capture.size > default_capture.size

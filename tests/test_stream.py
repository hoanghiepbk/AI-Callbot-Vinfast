"""Endpointing logic for the real-time voice loop (StreamingMicrophone).

The mic stream needs hardware, so we inject a fake `sounddevice` module whose
InputStream replays pre-baked frames into the VAD callback. This exercises the
speech/silence state machine deterministically, without a microphone.
"""

from __future__ import annotations

import sys
import types

import numpy as np

from callbot.audio.stream import StreamingMicrophone

_SR = 16000
_FRAME = _SR * 30 // 1000  # 30 ms frame = 480 samples


def _speech(n_frames: int) -> np.ndarray:
    # RMS 0.1 >> default VAD threshold 0.01 → counts as speech.
    return np.full(n_frames * _FRAME, 0.1, dtype=np.float32)


def _silence(n_frames: int) -> np.ndarray:
    return np.zeros(n_frames * _FRAME, dtype=np.float32)


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

    utterance = StreamingMicrophone().listen_utterance(max_wait_seconds=2.0)

    assert utterance is not None
    # Captured buffer starts at speech and ends once the silence window is hit.
    assert utterance.size >= 5 * _FRAME


def test_pure_silence_returns_none(monkeypatch):
    _install_fake_sd(monkeypatch, _silence(3))

    utterance = StreamingMicrophone().listen_utterance(max_wait_seconds=0.3)

    assert utterance is None


def test_readback_field_uses_longer_silence_window(monkeypatch):
    # 5 speech frames + a 900ms pause (30 frames). The default 700ms window would
    # endpoint here and cut the buffer short; the numeric read-back window (1200ms)
    # must NOT — so the read-back capture keeps the whole (longer) buffer.
    audio = np.concatenate([_speech(5), _silence(30)])

    _install_fake_sd(monkeypatch, audio)
    default_capture = StreamingMicrophone().listen_utterance(max_wait_seconds=2.0)

    _install_fake_sd(monkeypatch, audio)
    readback_capture = StreamingMicrophone().listen_utterance(
        field_name="phone", max_wait_seconds=2.0, max_utterance_seconds=0.4
    )

    assert default_capture is not None and readback_capture is not None
    # Read-back field tolerates the mid-number pause → captures more than the default cut.
    assert readback_capture.size > default_capture.size

"""TTS audio playback."""

from __future__ import annotations

import io
import wave

import numpy as np


def decode_wav_bytes(audio: bytes) -> tuple[int, np.ndarray]:
    """Decode WAV bytes into a `(sample_rate, float32_samples)` tuple."""
    with wave.open(io.BytesIO(audio), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError("only 16-bit PCM WAV playback is supported")
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        raw = wav.readframes(wav.getnframes())

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels)
    return sample_rate, samples


def play_wav_bytes(audio: bytes) -> None:
    """Play 16-bit PCM WAV bytes through sounddevice."""

    try:
        import sounddevice as sd
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("sounddevice is required for audio playback") from exc

    sample_rate, samples = decode_wav_bytes(audio)
    sd.play(samples, sample_rate)
    sd.wait()

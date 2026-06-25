"""Piper local TTS implementation."""

from __future__ import annotations

import io
import math
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from callbot import config
from callbot.tts.base import TTSResult


def _wav_bytes_from_pcm(samples: np.ndarray, sample_rate: int) -> bytes:
    clipped = np.asarray(samples, dtype=np.float32)
    if clipped.ndim != 1:
        clipped = clipped.reshape(-1)
    clipped = np.clip(clipped, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def _tone_fallback(text: str, sample_rate: int) -> bytes:
    """Deterministic offline fallback used when no Piper binary/voice is present."""

    plain = text.strip() or " "
    segments: list[np.ndarray] = []
    # Short vowel-like bursts with tiny gaps make the fallback sound less like a beep.
    base = 155.0
    for idx, chunk in enumerate(plain.split() or [plain]):
        duration = min(0.35 + 0.03 * len(chunk), 0.8)
        n = max(1, int(sample_rate * duration))
        t = np.linspace(0.0, duration, n, endpoint=False)
        freq = base + (sum(ord(ch) for ch in chunk) % 140)
        carrier = 0.55 * np.sin(2 * math.pi * freq * t)
        carrier += 0.25 * np.sin(2 * math.pi * (freq * 2.01) * t)
        envelope = np.sin(np.linspace(0.0, math.pi, n))
        segments.append((carrier * envelope).astype(np.float32))
        if idx < len(plain.split()) - 1:
            segments.append(np.zeros(int(sample_rate * 0.08), dtype=np.float32))
    if not segments:
        segments = [np.zeros(int(sample_rate * 0.2), dtype=np.float32)]
    return _wav_bytes_from_pcm(np.concatenate(segments), sample_rate)


@dataclass
class PiperTTS:
    """Piper adapter with a best-effort local binary path and a safe fallback.

    The primary path is a local `piper` executable plus a voice `.onnx` file.
    If the binary or voice is missing, the adapter still returns a valid WAV so
    the CLI/demo does not crash on a clean machine.
    """

    voice_path: str | None = None
    executable: str | None = None
    speaker: str | None = None
    sample_rate: int = config.PIPER_SAMPLE_RATE
    fallback_mode: str = "tone"

    def __post_init__(self) -> None:
        if self.voice_path is None and config.PIPER_VOICE:
            self.voice_path = config.PIPER_VOICE
        if self.executable is None:
            self.executable = config.PIPER_BINARY
        if self.speaker is None and config.PIPER_SPEAKER:
            self.speaker = config.PIPER_SPEAKER

    def synthesize(self, text: str) -> TTSResult:
        started = time.perf_counter()
        audio = self._synthesize_best_effort(text)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return TTSResult(audio=audio, latency_ms=latency_ms)

    def _synthesize_best_effort(self, text: str) -> bytes:
        try:
            return self._synthesize_with_piper(text)
        except Exception:
            if self.fallback_mode == "silence":
                return self._silence(text)
            return _tone_fallback(text, self.sample_rate)

    def _synthesize_with_piper(self, text: str) -> bytes:
        executable = self._resolve_executable()
        voice = self._resolve_voice()
        if executable is None or voice is None:
            raise RuntimeError("piper executable and voice model are required")

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "tts.wav"
            cmd = [
                executable,
                "--model",
                str(voice),
                "--output_file",
                str(output),
            ]
            if self.speaker:
                cmd.extend(["--speaker", str(self.speaker)])
            if self.sample_rate:
                cmd.extend(["--sample_rate", str(int(self.sample_rate))])
            subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                check=True,
            )
            if not output.is_file():
                raise RuntimeError("piper did not produce an output file")
            return output.read_bytes()

    def _resolve_executable(self) -> str | None:
        candidate = (self.executable or "").strip()
        if candidate and Path(candidate).is_file():
            return candidate
        if candidate:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return shutil.which("piper")

    def _resolve_voice(self) -> Path | None:
        if not self.voice_path:
            return None
        voice = Path(self.voice_path).expanduser()
        if voice.is_file():
            return voice
        return None

    def _silence(self, text: str) -> bytes:
        length_sec = max(0.2, min(1.5, 0.03 * max(1, len(text))))
        samples = np.zeros(int(self.sample_rate * length_sec), dtype=np.float32)
        return _wav_bytes_from_pcm(samples, self.sample_rate)

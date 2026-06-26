"""Edge-TTS — Microsoft neural Vietnamese voice (default vi-VN-HoaiMyNeural, young female).

A cloud TTS with much more natural prosody than local Piper, used for the live demo
(DEC-05: documented swap; the reproducible submission default stays Piper/local). Needs
internet. Numbers are expanded digit-by-digit (shared with Piper) so phone/plate/VIN read
correctly. On any failure (no package / offline) it returns silence + a warning, never crashes.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from dataclasses import dataclass, field

import numpy as np

from callbot import config
from callbot.tts.base import TTSResult
from callbot.tts.piper_tts import _silence_wav, tts_preprocess

logger = logging.getLogger(__name__)

_DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
_HINT = 'edge-tts unavailable (offline or not installed: pip install -e ".[tts]")'


def _mp3_to_wav(mp3: bytes) -> bytes:
    """Decode edge-tts MP3 bytes to 16-bit PCM mono WAV (the pipeline's audio format)."""
    import av

    container = av.open(io.BytesIO(mp3))
    rate = container.streams.audio[0].rate
    chunks: list[np.ndarray] = []
    for frame in container.decode(audio=0):
        arr = frame.to_ndarray()
        if arr.ndim > 1:  # planar / multi-channel -> mono
            arr = arr.mean(axis=0)
        chunks.append(arr.reshape(-1))
    data = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    if data.dtype.kind == "f":
        pcm = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16)
    else:
        pcm = data.astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(rate))
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


@dataclass
class EdgeTTS:
    """Microsoft Edge neural TTS adapter. Real speech when online; silence + warning otherwise."""

    voice: str = ""
    _warned: bool = field(default=False, init=False, repr=False)

    def synthesize(self, text: str) -> TTSResult:
        started = time.perf_counter()
        audio = self._synthesize_speech(tts_preprocess(text))
        return TTSResult(audio=audio, latency_ms=(time.perf_counter() - started) * 1000.0)

    def _synthesize_speech(self, text: str) -> bytes:
        try:
            mp3 = self._fetch_mp3(text)
            if mp3:
                return _mp3_to_wav(mp3)
        except Exception as exc:  # noqa: BLE001 - cloud/network best-effort, never crash a turn
            if not self._warned:
                logger.warning("EdgeTTS: %s (%s)", _HINT, type(exc).__name__)
                self._warned = True
        return _silence_wav()

    def _fetch_mp3(self, text: str) -> bytes:
        import edge_tts

        voice = self.voice or config.EDGE_VOICE or _DEFAULT_VOICE

        async def _run() -> bytes:
            communicate = edge_tts.Communicate(text, voice)
            buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buffer.write(chunk["data"])
            return buffer.getvalue()

        return asyncio.run(_run())

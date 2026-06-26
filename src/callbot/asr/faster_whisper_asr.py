"""PhoWhisper / faster-whisper ASR implementation."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from callbot.asr.base import ASRResult

# "phowhisper-medium" is a friendly label, NOT a loadable faster-whisper name — PhoWhisper
# ships as a HuggingFace transformers checkpoint and must be converted to CTranslate2 first
# (scripts/setup_asr.py). The local CT2 export lives here once built.
_PLACEHOLDER = "phowhisper-medium"
_LOCAL_CT2 = Path(__file__).resolve().parents[3] / "models" / "phowhisper-medium-ct2"
_SETUP_HINT = (
    "PhoWhisper is not converted to CTranslate2 yet. Run `python scripts/setup_asr.py` to "
    "build models/phowhisper-medium-ct2, or set ASR_MODEL to a faster-whisper model name "
    "(e.g. 'medium') or a CT2 path."
)


def _resolve_model(explicit: str | None) -> str:
    """Pick the ASR model: explicit arg > real ASR_MODEL > local CT2 export > placeholder."""
    if explicit:
        return explicit
    env = os.getenv("ASR_MODEL")
    if env and env != _PLACEHOLDER:
        return env  # user pointed ASR_MODEL at a real model / CT2 path
    if _LOCAL_CT2.is_dir():
        return str(_LOCAL_CT2)  # the converted PhoWhisper from setup_asr.py
    return _PLACEHOLDER  # not converted -> load raises with the setup hint below


def _ensure_cuda_dlls() -> None:
    """Put the CUDA 12 runtime DLLs on PATH so ctranslate2 can load on GPU (Windows).

    The `nvidia-*-cu12` wheels (pip install -e ".[gpu]") ship cublas/cudnn/cudart under
    site-packages/nvidia/*/bin. ctranslate2 loads them via the OS loader, which searches PATH,
    so we prepend those dirs in-process — no system CUDA toolkit install needed.
    """
    import glob
    import sys

    if sys.platform != "win32":
        return  # Linux wheels expose the libs differently; nothing to do here
    try:
        import site

        bases = site.getsitepackages()
    except Exception:  # noqa: BLE001 - site layout varies; skip silently
        return
    dirs = [d for base in bases for d in glob.glob(os.path.join(base, "nvidia", "*", "bin"))]
    current = os.environ.get("PATH", "")
    missing = [d for d in dirs if d not in current]
    if missing:
        os.environ["PATH"] = os.pathsep.join(missing) + os.pathsep + current


class FasterWhisperASR:
    """ASR adapter backed by faster-whisper/CTranslate2.

    Heavy model loading is lazy so importing the module does not download or
    initialize model weights. Defaults to the local PhoWhisper-medium CT2 export
    (built by scripts/setup_asr.py); ASR_MODEL can override with any faster-whisper
    model name or CT2 path.
    """

    def __init__(
        self,
        model_name: str | None = None,
        *,
        device: str | None = None,
        compute_type: str | None = None,
        language: str = "vi",
    ) -> None:
        self.model_name = _resolve_model(model_name)
        self.device = device or os.getenv("ASR_DEVICE", "cpu")
        self.compute_type = compute_type or os.getenv("ASR_COMPUTE_TYPE", "int8")
        self.language = language
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - depends on optional runtime install
                raise RuntimeError("faster-whisper is required for ASR") from exc

            if self.model_name == _PLACEHOLDER:
                raise RuntimeError(_SETUP_HINT)
            if self.device == "cuda":
                _ensure_cuda_dlls()  # make the bundled CUDA runtime loadable (Windows)
            try:
                self._model = WhisperModel(
                    self.model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            except ValueError as exc:  # invalid model name/path -> point at the setup script
                raise RuntimeError(f"{exc}. {_SETUP_HINT}") from exc
        return self._model

    def transcribe(self, audio: np.ndarray | list[float], sample_rate: int = 16000) -> ASRResult:
        started = time.perf_counter()
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if sample_rate != 16000:
            raise ValueError("FasterWhisperASR expects 16 kHz mono audio")

        segments, info = self.model.transcribe(samples, language=self.language, vad_filter=False)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        latency_ms = (time.perf_counter() - started) * 1000
        confidence = getattr(info, "language_probability", None)
        return ASRResult(text=text, confidence=confidence, latency_ms=latency_ms)

    @classmethod
    def from_file(cls, path: str) -> ASRResult:
        started = time.perf_counter()
        instance = cls()
        segments, info = instance.model.transcribe(str(Path(path)), language=instance.language)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        latency_ms = (time.perf_counter() - started) * 1000
        confidence = getattr(info, "language_probability", None)
        return ASRResult(text=text, confidence=confidence, latency_ms=latency_ms)

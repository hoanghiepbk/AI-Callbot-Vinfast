"""WER / CER measurement (A30, folds in B14) — conditional on an audio set.

Reads scenarios/audio/manifest.json: a list of {"audio": "<file>.wav", "text": "<gold>"}.
For each entry it transcribes the wav with FasterWhisperASR.from_file (B11) and compares
against the gold transcript (both normalized) using jiwer.

If the manifest is missing/empty, OR jiwer is not installed, it returns a 'pending' result
and NEVER blocks A30 — B14 audio is not ready yet. We do NOT synthesize TTS audio to fake a
WER number (that would measure the TTS+ASR loop, not real ASR — decided out of scope).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_AUDIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "audio"
_MANIFEST = _AUDIO_DIR / "manifest.json"


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace (applied to both sides).

    Python 3 ``\\w`` is Unicode-aware, so Vietnamese accented letters are kept as word
    characters; only punctuation is dropped.
    """
    stripped = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(stripped.split())


def _pending(reason: str) -> dict:
    return {"name": "wer", "status": "pending", "reason": reason}


def measure_wer() -> dict:
    if not _MANIFEST.is_file():
        return _pending("WER pending B14 audio: scenarios/audio/manifest.json not found")
    try:
        entries = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _pending(f"manifest.json is not valid JSON: {exc}")
    if not entries:
        return _pending("WER pending B14 audio: manifest.json is empty")

    try:
        import jiwer
    except ImportError:
        return _pending("jiwer not installed (add to run WER on the audio set)")

    from callbot.asr.faster_whisper_asr import FasterWhisperASR

    refs: list[str] = []
    hyps: list[str] = []
    per_file: list[dict] = []
    for entry in entries:
        wav = _AUDIO_DIR / entry["audio"]
        if not wav.is_file():
            per_file.append({"audio": entry["audio"], "error": "wav not found"})
            continue
        gold = _normalize(entry["text"])
        hyp = _normalize(FasterWhisperASR.from_file(str(wav)).text)
        refs.append(gold)
        hyps.append(hyp)
        per_file.append(
            {
                "audio": entry["audio"],
                "wer": round(jiwer.wer(gold, hyp), 4),
                "cer": round(jiwer.cer(gold, hyp), 4),
            }
        )

    if not refs:
        return _pending("manifest listed files but none were found on disk")
    return {
        "name": "wer",
        "status": "ok",
        "files": len(refs),
        "wer": round(jiwer.wer(refs, hyps), 4),
        "cer": round(jiwer.cer(refs, hyps), 4),
        "per_file": per_file,
    }

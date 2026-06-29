"""Environment/config loading from .env.

Stdlib-only loader (no python-dotenv dependency): reads KEY=value lines from a
`.env` at the project root into os.environ, without overriding vars already set
in the real environment. Only the keys A10 needs are exposed as constants.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root = two levels up from src/callbot/config.py.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _load_env_file(path: Path) -> None:
    """Populate os.environ from a .env file. Real environment vars take precedence."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key, value = key.strip(), value.strip()
        if key:
            os.environ.setdefault(key, value)


_load_env_file(_ENV_PATH)

# Use 127.0.0.1 (IPv4) not "localhost": after httpx's 5s keep-alive expiry the pooled
# connection drops, and reconnecting to "localhost" tries IPv6 ::1 first (ollama listens on
# IPv4 only) which stalls ~2s before falling back — adding ~2s to any call made >5s after the
# previous one (i.e. every real demo turn). 127.0.0.1 skips that and keeps turns at ~0.7s.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper").strip().lower() or "piper"
PIPER_BINARY = os.environ.get("PIPER_BINARY", "piper").strip() or "piper"
PIPER_VOICE = os.environ.get("PIPER_VOICE", "").strip()
PIPER_SPEAKER = os.environ.get("PIPER_SPEAKER", "").strip()
# Edge-TTS voice (used when TTS_ENGINE=edge). Default = young female Vietnamese neural voice.
EDGE_VOICE = os.environ.get("EDGE_VOICE", "vi-VN-HoaiMyNeural").strip() or "vi-VN-HoaiMyNeural"
try:
    PIPER_SAMPLE_RATE = int(os.environ.get("PIPER_SAMPLE_RATE", "22050"))
except ValueError:
    PIPER_SAMPLE_RATE = 22050

try:
    PIPER_LENGTH_SCALE = float(os.environ.get("PIPER_LENGTH_SCALE", "1.5"))
except ValueError:
    PIPER_LENGTH_SCALE = 1.5

# Voice-mode backchannel: play a fixed "dạ vâng ạ" filler the instant audio arrives, masking
# ASR+LLM latency so the caller perceives an instant reply. Opt-in (off by default).
VOICE_FILLER = os.environ.get("VOICE_FILLER", "0").strip().lower() in {"1", "true", "yes", "on"}

# Mic input gain for the real-time voice loop. Quiet built-in laptop mics can sit below the
# VAD speech threshold, so the bot never detects a turn; boosting the signal in software fixes
# detection AND gives ASR a healthier level. 1.0 = no change. Raise (e.g. 8–12) for quiet mics.
try:
    MIC_GAIN = float(os.environ.get("MIC_GAIN", "1.0"))
except ValueError:
    MIC_GAIN = 1.0

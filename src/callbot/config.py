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

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
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
    PIPER_LENGTH_SCALE = float(os.environ.get("PIPER_LENGTH_SCALE", "1.3"))
except ValueError:
    PIPER_LENGTH_SCALE = 1.3

# Voice-mode backchannel: play a fixed "dạ vâng ạ" filler the instant audio arrives, masking
# ASR+LLM latency so the caller perceives an instant reply. Opt-in (off by default).
VOICE_FILLER = os.environ.get("VOICE_FILLER", "0").strip().lower() in {"1", "true", "yes", "on"}

"""Download a Vietnamese FEMALE Piper voice into models/piper/ so the bot speaks real speech.

Voice: vi_VN-vais1000-medium from rhasspy/piper-voices — a single female Northern-Vietnamese
speaker (VAIS-1000 corpus), medium quality, 22.05 kHz. Verified female by pitch (F0 ~237 Hz).

    pip install -e ".[tts]"      # piper-tts (onnxruntime-based)
    python scripts/setup_tts.py  # downloads the .onnx + .onnx.json into models/piper/

PiperTTS auto-detects models/piper/vi_VN-vais1000-medium.onnx. The voice binary is git-ignored.
Re-run with --force to re-download.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_REPO = "rhasspy/piper-voices"
_VOICE = "vi_VN-vais1000-medium"
_BASE = "vi/vi_VN/vais1000/medium"
_DEST = Path(__file__).resolve().parent.parent / "models" / "piper"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the Vietnamese female Piper voice.")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()

    _DEST.mkdir(parents=True, exist_ok=True)
    onnx = _DEST / f"{_VOICE}.onnx"
    if onnx.is_file() and not args.force:
        print(f"[setup_tts] already present: {onnx} (use --force to re-download)")
        return 0

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            '[setup_tts] huggingface_hub missing. Install with:\n    pip install -e ".[tts]"',
            file=sys.stderr,
        )
        return 1

    print(f"[setup_tts] downloading {_VOICE} (female, vi_VN) -> {_DEST} …")
    for filename in (f"{_VOICE}.onnx", f"{_VOICE}.onnx.json"):
        cached = hf_hub_download(_REPO, f"{_BASE}/{filename}")
        shutil.copy(cached, _DEST / filename)
    print(f"[setup_tts] done. PiperTTS will now speak with {_VOICE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

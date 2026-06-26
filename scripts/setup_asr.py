"""Convert PhoWhisper-medium to CTranslate2 so faster-whisper can load it (voice demo).

PhoWhisper (vinai/PhoWhisper-medium) is the best Vietnamese Whisper checkpoint, but it ships
as a HuggingFace transformers model — faster-whisper needs the CTranslate2 format. This script
builds `models/phowhisper-medium-ct2/` (int8) once; FasterWhisperASR then auto-detects it.

    pip install -e ".[asr]"      # transformers + ctranslate2
    python scripts/setup_asr.py  # one-time conversion (set HF_TOKEN if the model is gated)

Re-run with --force to rebuild.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SOURCE_MODEL = "vinai/PhoWhisper-medium"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "models" / "phowhisper-medium-ct2"


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert PhoWhisper-medium to CTranslate2.")
    parser.add_argument("--force", action="store_true", help="rebuild even if output exists")
    parser.add_argument("--quantization", default="int8", help="CT2 quantization (default int8)")
    args = parser.parse_args()

    if _OUTPUT_DIR.is_dir() and not args.force:
        print(f"[setup_asr] already converted: {_OUTPUT_DIR} (use --force to rebuild)")
        return 0

    try:
        from ctranslate2.converters import TransformersConverter
    except ImportError:
        print(
            "[setup_asr] missing converter deps. Install with:\n"
            '    pip install -e ".[asr]"   (transformers + ctranslate2)',
            file=sys.stderr,
        )
        return 1

    print(f"[setup_asr] converting {_SOURCE_MODEL} -> {_OUTPUT_DIR} ({args.quantization}) …")
    converter = TransformersConverter(
        _SOURCE_MODEL,
        copy_files=["tokenizer.json", "preprocessor_config.json"],
    )
    converter.convert(str(_OUTPUT_DIR), quantization=args.quantization, force=args.force)
    print(f"[setup_asr] done. FasterWhisperASR will now auto-detect {_OUTPUT_DIR.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""WER/CER runner (B14): transcribe the audio set and write eval/wer_results.json.

    # raw .wav live in a private, git-ignored folder; the manifest + results are committed.
    set ASR_MODEL=<faster-whisper / CT2 model>   # e.g. a PhoWhisper-medium CT2 export
    python -m eval.run_wer

Reproducibility: anyone with their own recordings placed to match scenarios/audio/manifest.json
(audio paths relative to the repo root) can re-run this and regenerate wer_results.json. We do
NOT commit raw audio (size + real voices are private); the reference transcripts (manifest),
the per-clip results, and this script are committed so the numbers stay verifiable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from eval.wer import measure_wer

_RESULTS_PATH = Path(__file__).resolve().parent / "wer_results.json"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    result = measure_wer()
    if result["status"] != "ok":
        print(f"[WER] {result['status']}: {result['reason']}")
        return 1
    # Document methodology in the committed artifact so the numbers are interpretable.
    default_label = "vinai/PhoWhisper-medium (CTranslate2 int8)"
    result["asr_model"] = os.environ.get("ASR_MODEL_LABEL", default_label)
    result["normalization"] = "lowercase + strip punctuation + collapse whitespace (both sides)"
    print(f"=== WER/CER · {result['files']} clips ===")
    print(f"macro WER = {result['wer']:.4f}   macro CER = {result['cer']:.4f}\n")
    for row in result["per_file"]:
        if "error" in row:
            print(f"  {row['audio']:24} {row['error']}")
            continue
        print(f"  {row['audio']:22} [{row['category']}] WER={row['wer']:.3f} CER={row['cer']:.3f}")
    _RESULTS_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {_RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

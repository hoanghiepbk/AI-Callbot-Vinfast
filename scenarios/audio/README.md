# Audio WER set (B14)

Speech-to-text accuracy (WER/CER) for the ASR stage, measured on real Vietnamese
recordings.

## What is committed vs not

- **NOT committed:** the raw `*.wav` recordings — they contain real voices (privacy) and
  are heavy. They are git-ignored (`audio/*.wav`).
- **Committed (so the numbers stay verifiable):**
  - `scenarios/audio/manifest.json` — each clip → `reference_text` (ground-truth transcript)
    + `category` + `note`. Audio paths are relative to the repo root (e.g. `audio/voice1.wav`).
  - `eval/wer_results.json` — per-clip WER/CER + the ASR output + macro totals + model used.
  - `eval/run_wer.py` + `eval/wer.py` — the scripts that produce the results.
  - `audio/*.reference.txt` — the original per-clip reference transcripts.

## Reproduce

1. Place recordings so each `audio` path in `manifest.json` exists (your own `*.wav`).
2. Point `ASR_MODEL` at a faster-whisper / CTranslate2 model. The committed numbers use
   **vinai/PhoWhisper-medium** exported to CTranslate2 (int8). Convert it once:

   ```bash
   ct2-transformers-converter --model vinai/PhoWhisper-medium \
     --output_dir phowhisper-medium-ct2 \
     --copy_files tokenizer.json preprocessor_config.json --quantization int8
   export ASR_MODEL=$PWD/phowhisper-medium-ct2
   ```

3. Run:

   ```bash
   pip install jiwer
   python -m eval.run_wer
   ```

Both reference and hypothesis are normalized (lowercase, strip punctuation, collapse
whitespace) before scoring. We do **not** synthesize TTS audio to fake WER — that would
measure the TTS+ASR loop, not real ASR.

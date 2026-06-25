# Architecture

## Pipeline Overview

The runtime path is intentionally split into two tracks:

1. Audio input: microphone capture produces 16 kHz mono float32 audio.
2. VAD: the turn segmenter cuts an utterance after silence, with a longer silence window for phone, plate, and VIN fields.
3. ASR: `FasterWhisperASR` transcribes Vietnamese audio and reports `asr_latency_ms`.
4. Dialogue engine: text enters `DialogueEngine.process(text)` so dialogue evaluation can run without audio noise.
5. Normalization: extracted field values are normalized per field after extraction, not globally.
6. Output: the engine returns the next response and eventually the final JSON.

The audio side depends only on the frozen interfaces in `asr/base.py`, `tts/base.py`, and `normalization/base.py`. That lets the dialogue track use fake ASR/TTS in tests while the voice track evolves independently.

## ASR

Primary ASR is a faster-whisper/CTranslate2 adapter configured for Vietnamese:

- default model: `ASR_MODEL=phowhisper-medium`
- fallback: any faster-whisper model name such as `small` or `medium`
- default device: `ASR_DEVICE=cpu`
- default compute type: `ASR_COMPUTE_TYPE=int8`

The adapter lazy-loads model weights on first transcription. `transcribe(audio, sample_rate=16000)` handles live mic buffers, while `from_file(path)` supports WER evaluation on recorded WAV fixtures.

## VAD And Mic Capture

`MicrophoneRecorder` records 16 kHz mono float32 buffers via `sounddevice`.

`EnergyVAD` is the deterministic Phase 1 turn-cutter. It is intentionally simple and import-safe. `SileroVAD` currently keeps the same public interface so Phase 2 can replace the internals with the package-backed Silero model without changing pipeline code.

Numeric identity fields use a longer silence timeout because Vietnamese callers often pause while reading long phones, plates, or VINs. This avoids turning `"30F"` and `"1234"` into two failed turns.

## Normalization

`VietnameseNormalizer.normalize_field(name, raw)` returns `NormResult(value, parse_failed)`.

The normalizer is per-field:

- phone fields: spoken digits and mixed numeric chunks become exactly 10 digits
- `license_plate_vin`: spoken plates become canonical forms like `30A-567.89`; 17-character VINs are compacted and uppercased
- `current_odo`: spoken distance such as `nam van cay` becomes `50000`
- free-text fields: whitespace is cleaned but semantic text is preserved

Strict parse failures are the dialogue signal for garbled input handling. The normalizer does not decide what to ask next; it only reports whether a field value is parseable under the frozen schema contract.

## Pipeline Ownership

`pipeline.py` is owned by Track B because it wires audio, ASR, dialogue, and optional TTS. The dialogue engine remains interface-agnostic: it receives text and returns structured state. That boundary keeps text-mode tests deterministic and lets audio quality be evaluated separately with WER.

## Trade-Offs

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| ASR runtime | faster-whisper CT2 | cloud ASR | reproducible offline demo and WER control |
| Turn cutting | deterministic VAD interface | dialogue-aware audio heuristics inside engine | keeps engine independent from audio |
| Normalization | per-field parser | global text replacement | avoids corrupting names such as `anh Nam` into numbers |
| TTS primary | Piper local later | edge-tts primary | offline reproducibility matters more than voice quality |
| RAG | not used for Phase 1 | vector retrieval | static policy and state management are higher scoring and less risky |


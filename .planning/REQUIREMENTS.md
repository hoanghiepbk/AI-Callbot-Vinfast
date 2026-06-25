# Requirements — VinFast Callbot Track B

Derived from TASKGRAPH.md (23 task cards). Each requirement ID maps to one TASKGRAPH task.
Status reflects implementation state as of 2026-06-25.

---

## Wave 0 — Contract Freeze (COMPLETE — both tracks)

- **REQ-001** [TASK-001] Repo scaffold and tooling: directory tree, venv, requirements.txt skeleton, .env.example, .gitignore blocking .venv/.env/*.onnx/audio*.wav, all __init__.py, all base.py/module stubs with docstrings. ✓
- **REQ-002** [TASK-002] Pydantic v2 schemas (data contract): SlotStatus, Slot, IntentSignals, NLUResult, PostCall, FinalOutput + dialogue/values.py (D9) + READBACK_REQUIRED constant (D10). Field names exactly per brief. Validators for phone/VIN/plate returning parse_failed. ✓
- **REQ-003** [TASK-003] Interface base classes: asr/base.py (ASR, ASRResult), llm/base.py (LLM, LLMResult), tts/base.py (TTS, TTSResult), normalization/base.py (Normalizer, NormResult), dialogue/engine.py (DialogueEngine signature + TurnResult). FROZEN after merge. ✓

---

## Wave 1 — Track A (Dialogue Core) — COMPLETE (on main, remote branches a/*)

- **REQ-A10** [TASK-A10] LLM client + prompts: llm/ollama_client.py implementing LLM protocol (Ollama, json_schema → format mode, latency_ms, 1 retry on invalid JSON). llm/prompts.py with versioned NLU/response/post-call prompts. Config from .env only. ✓
- **REQ-A11** [TASK-A11] Category config + next-field policy: dialogue/categories.py with G_1..G_5 field lists (name, priority, required). pick_next_missing(category, state, emergency) pure deterministic function. ✓
- **REQ-A12** [TASK-A12] NLU layer: dialogue/intent.py (category classification, ambiguity detection) + dialogue/extraction.py (entity extraction + signals → NLUResult). extracted_fields = only fields provided this turn. corrected_fields separate. category=None when ambiguous. ✓
- **REQ-A13** [TASK-A13] LangGraph engine (happy path): dialogue/state.py (CallState), dialogue/graph.py (5-node StateGraph), dialogue/nodes.py (pure node functions), dialogue/engine.py (process/finalize/reset). Happy path + missing-field (#1) + hangup finalize (#8). Template-first response (2-3 variants). Normalization per-field post-extraction (D2). ✓
- **REQ-A14** [TASK-A14] Post-call track: dialogue/post_call.py runs once on call end, feeds full transcript to 1 LLM call → PostCall(short_summary, sentimental_analysis, emergency). ✓

---

## Wave 1 — Track B (Senses Stack) — COMPLETE

- **REQ-B10** [TASK-B10] Vietnamese normalization + tests: normalization/vietnamese_numbers.py implementing Normalizer protocol. normalize_field(name, raw) → NormResult(value, parse_failed). Per-field typed normalization: spoken digits → phone (10 digits), license plate (canonical), VIN (17 chars), odo (integer km), free-text (whitespace cleaned). tests/test_normalization.py with 17 passing cases. ✓
- **REQ-B11** [TASK-B11] ASR wrapper + file mode: asr/faster_whisper_asr.py implementing ASR protocol. Supports mic buffer transcription (language="vi", compute_type="int8") and from_file() for WER eval. Default PhoWhisper-CT2; generic faster-whisper fallback. Measures latency_ms. ✓
- **REQ-B12** [TASK-B12] Mic capture + VAD: audio/recorder.py (sounddevice, 16 kHz mono float32) + audio/vad.py (turn segmentation, Phase 1 EnergyVAD / Phase 2 silero-vad). Extended silence timeout for READBACK_REQUIRED fields to avoid false garbled triggers mid-number. ✓
- **REQ-B13** [TASK-B13] Conversation corpus: scenarios/g1..g5.json + exceptions.json with realistic Vietnamese caller utterances (colloquial, agitated, abbreviated, spoken numbers). Turn-by-turn format. ≥2 scenarios/category (≥10 total) + ≥3 exception scenarios. ✓
- **REQ-B14** [TASK-B14] WER audio fixtures: ≥5 real Vietnamese audio clips (diverse speakers, spoken phone numbers / plate numbers) with reference transcripts at scenarios/audio/*.wav + *.reference.txt. ✓

---

## Wave 2 — Exception Handling & Voice I/O (PENDING)

*Coordinate with Hiệp to confirm A20/A21 status before starting B21.*

- **REQ-A20** [TASK-A20] 8 exception handlers: dialogue/exceptions.py implementing all 8 exception strategies, integrated into engine.process(). All deterministic and flag-driven from NLU output. Covers: #1 missing (no re-ask), #2 correction (update no repeat), #3 ambiguous (exactly 1 clarification), #4 out-of-scope (redirect/human), #5 garbled (parse_failed → readback + confirm), #6 emergency (hybrid detect → hotline + skip low-priority fields), #7 stuck ≥2 turns (offer human), #8 hangup (partial JSON null). [TRACK A — status: check with Hiệp]
- **REQ-A21** [TASK-A21] Eval harness + slot F1 + exception tests: eval/run_eval.py (text-mode scenario feed), eval/metrics.py (slot precision/recall/F1, routing accuracy). tests/test_exception_handling.py (≥3 exception cases), test_dialogue_state.py, test_field_extraction.py, test_final_output_schema.py. [TRACK A — status: check with Hiệp]
- **REQ-B20** [TASK-B20] TTS Piper: tts/piper_tts.py implementing TTS protocol with Piper local ONNX (vais1000 medium voice). audio/playback.py for audio output. Measures latency_ms. Swap-able via .env TTS_ENGINE=piper. edge_tts.py and vixtts.py as stub-pluggable alternatives.
- **REQ-B21** [TASK-B21] Pipeline integration + CLI: pipeline.py turn() function (audio→ASR→engine.process→TTS, logging asr/llm/tts latency_ms per turn). main.py CLI with --voice (mic loop) and --text (keyboard/stdin). Measurement Gate: log template-only latency AND E2E latency before any optimization. Silence-timeout/disconnect/Ctrl-C → engine.finalize() → partial JSON (#8, D4). Depends on REQ-A13 merged to main. Also: swap EnergyVAD → silero-vad here.
- **REQ-B22** [TASK-B22] Gradio UI: Gradio web UI with mic input, transcript display, live JSON panel (state/final output), TTS playback. Wraps pipeline.turn() without adding new logic. Required for signature demo video recording.

---

## Wave 3 — Evaluation, Demo & Report (NOT STARTED)

- **REQ-A30** [TASK-A30] Full metric suite: routing confusion matrix 5×5, emergency recall on adversarial set (including calm-voice emergency cases), sentiment accuracy, WER via jiwer on scenarios/audio/, LLM-as-judge naturalness (dev-time only, documented), latency E2E + breakdown ASR/LLM/TTS p50/p95 per component. [TRACK A]
- **REQ-A31** [TASK-A31] Ablation study: with/without state-machine, with/without recall tuning, Qwen3 vs Vietnamese-tuned variant, laptop medium vs GPU large WER. Delta table produced per run. [TRACK A]
- **REQ-A32** [TASK-A32] Evaluation Report (Deliverable #4): docs/EVALUATION_REPORT.md covering all metrics + failure analysis (what failed + WHY + remediation direction) + latency + ablation + honest limitations + LLM-as-judge disclosure. [TRACK A]
- **REQ-B30** [TASK-B30] Signature demo + video: record signature demo call (~90 sec) via Gradio showing emergency-priority + correction + garbled-confirm + no-re-ask + normalization + JSON emergency=yes. Plus calm-voice emergency case proving recall-tuned detection. May use edge_tts for recording quality; submitted version uses Piper local (documented).
- **REQ-S30** [TASK-S30] Architecture Doc finalized (Deliverable #1): docs/ARCHITECTURE.md complete with pipeline, model choices, conversation flow, 8 exception strategies, decisions + trade-offs including rejected alternatives. A writes dialogue/exception/eval sections; B writes ASR/TTS/normalization/pipeline sections. [PAIR]
- **REQ-S31** [TASK-S31] Reproducibility: requirements.txt pinned == (including langgraph, langchain-core). scripts/setup.ps1 and setup.sh pull Ollama models + ASR/TTS weights + document minimum hardware. .env.example complete. README runnable. Repo scanned for secret leaks. pip install -r on clean machine must succeed. [PAIR]
- **REQ-S32** [TASK-S32] Gate 3 verification: cross-check all requirements against REQ matrix in BLUEPRINT.md §5. Walk through all 5 categories + ≥3 exceptions. Verify Report generated. [PAIR]

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-001 | Phase 01 | Complete ✓ |
| REQ-002 | Phase 01 | Complete ✓ |
| REQ-003 | Phase 01 | Complete ✓ |
| REQ-A10 | Phase 01 | Complete ✓ |
| REQ-A11 | Phase 01 | Complete ✓ |
| REQ-A12 | Phase 01 | Complete ✓ |
| REQ-A13 | Phase 01 | Complete ✓ |
| REQ-A14 | Phase 01 | Complete ✓ |
| REQ-B10 | Phase 01 | Complete ✓ |
| REQ-B11 | Phase 01 | Complete ✓ |
| REQ-B12 | Phase 01 | Complete ✓ |
| REQ-B13 | Phase 01 | Complete ✓ |
| REQ-B14 | Phase 01 | Complete ✓ |
| REQ-A20 | Phase 02 | Pending (Track A) |
| REQ-A21 | Phase 02 | Pending (Track A) |
| REQ-B20 | Phase 02 | Pending |
| REQ-B21 | Phase 02 | Pending |
| REQ-B22 | Phase 02 | Pending |
| REQ-A30 | Phase 03 | Not started |
| REQ-A31 | Phase 03 | Not started |
| REQ-A32 | Phase 03 | Not started |
| REQ-B30 | Phase 03 | Not started |
| REQ-S30 | Phase 03 | Partial (B-side sections done) |
| REQ-S31 | Phase 03 | Not started |
| REQ-S32 | Phase 03 | Not started |

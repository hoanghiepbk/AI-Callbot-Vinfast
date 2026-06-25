# requirements.md — Functional Requirements Intel
# Synthesized from: PLAN.md (PRD, precedence 2), BLUEPRINT.md (ADR, locked, precedence 0),
#                   TASKGRAPH.md (SPEC, precedence 3)
# Generated: 2026-06-25

---

## Wave 0 — Contract Freeze (Phase 0) — STATUS: COMPLETE

### REQ-scaffold
source: PLAN.md (Phase 0), TASKGRAPH.md (TASK-001)
id: REQ-scaffold
description: Repo scaffold and tooling. Directory tree per TECHSTACK.md §7, venv, requirements.txt
  skeleton, .env.example, .gitignore (blocks .venv/, __pycache__/, .env, *.onnx,
  scenarios/audio/*.wav), all __init__.py, all base.py/module stubs with docstrings.
acceptance:
  - Given empty repo, when scaffold is applied, directory tree matches BLUEPRINT.md §4.
  - python -c "import callbot" succeeds.
  - git status does not show .venv or .env.
scope: all files, both tracks
task: TASK-001 [PAIR]
status: COMPLETE (per PHASE_0_1_B_UPDATE.md)

### REQ-schemas
source: BLUEPRINT.md (§2), TASKGRAPH.md (TASK-002)
id: REQ-schemas
description: Implement models/schemas.py with frozen Pydantic v2 data contract: SlotStatus, Slot,
  IntentSignals, NLUResult, PostCall, FinalOutput. Also dialogue/values.py (D9) and constant
  READBACK_REQUIRED (D10). Field names EXACTLY per brief (see DEC-23 in decisions.md).
acceptance:
  - FinalOutput with missing fields serializes null (not absent) for each unset field.
  - Phone "0885234567" passes validator; "abc" fails.
  - Plate/VIN wrong format returns parse_failed=True.
  - FinalOutput structure is {category, fields, post_call}.
scope: models/schemas.py, dialogue/values.py
task: TASK-002 [PAIR]
status: COMPLETE (per PHASE_0_1_B_UPDATE.md — frozen schema plate/phone validation in place)

### REQ-interfaces
source: BLUEPRINT.md (§3), TASKGRAPH.md (TASK-003)
id: REQ-interfaces
description: Define all Protocol/ABC base classes: asr/base.py (ASR, ASRResult), llm/base.py
  (LLM, LLMResult), tts/base.py (TTS, TTSResult), normalization/base.py (Normalizer, NormResult),
  dialogue/engine.py (DialogueEngine signature + TurnResult — no logic yet).
acceptance:
  - mypy/import check passes on all base files.
  - Signatures match BLUEPRINT.md §3.
  - A fake impl can be created in tests using these protocols.
scope: asr/base.py, llm/base.py, tts/base.py, normalization/base.py, dialogue/engine.py
task: TASK-003 [PAIR]
status: COMPLETE (per PHASE_0_1_B_UPDATE.md)

---

## Wave 1 — Track A (Dialogue Core) — STATUS: IN PROGRESS / UNKNOWN (Track A status not in B-side docs)

### REQ-llm-client
source: TASKGRAPH.md (TASK-A10), BLUEPRINT.md (§1A Part 3)
id: REQ-llm-client
description: llm/ollama_client.py implements LLM protocol. Calls Ollama, supports json_schema
  parameter -> format mode, measures latency_ms, retries once on invalid JSON, raises clearly on
  second failure. llm/prompts.py contains versioned prompts for NLU, response, post-call.
acceptance:
  - Given "xe toi chet may tren cao toc", when complete(nlu_schema), returns JSON parseable to
    NLUResult with signals.emergency=True.
  - Given invalid JSON on first attempt, retries; on second failure raises clearly.
  - Model and host come from .env only (OLLAMA_HOST, LLM_MODEL).
scope: llm/ollama_client.py, llm/prompts.py
task: TASK-A10 [A]
track: A

### REQ-categories
source: TASKGRAPH.md (TASK-A11), BLUEPRINT.md (§2)
id: REQ-categories
description: dialogue/categories.py maps each category G_1..G_5 to a list of fields
  (name, priority, required). Implements pick_next_missing(category, state, emergency) as a
  deterministic pure function.
acceptance:
  - Given G_1 with current_location confirmed, next field = vehicle_condition (next priority).
  - Given emergency=True, fields with priority>=90 (e.g., current_odo) are skipped.
  - Given all required fields confirmed, returns None.
scope: dialogue/categories.py
task: TASK-A11 [A]
track: A

### REQ-nlu
source: TASKGRAPH.md (TASK-A12), BLUEPRINT.md (§1)
id: REQ-nlu
description: dialogue/intent.py (category classification, ambiguity detection) and
  dialogue/extraction.py (entity extraction + signals -> NLUResult). extracted_fields contains
  only fields provided THIS turn. corrected_fields is separate (exception #2). category=None
  when ambiguous (exception #3).
acceptance:
  - Given "a khong phai, so em la 0912...", signals.correction=True and corrected_fields has phone.
  - Given "toi can hoi chut", category=None.
scope: dialogue/intent.py, dialogue/extraction.py
task: TASK-A12 [A]
track: A

### REQ-langgraph-engine
source: TASKGRAPH.md (TASK-A13), BLUEPRINT.md (§1, §1A)
id: REQ-langgraph-engine
description: dialogue/state.py (CallState as LangGraph state schema), dialogue/graph.py
  (StateGraph with 5 nodes), dialogue/nodes.py (nlu/route/slot_update/next_field/respond pure fns),
  dialogue/engine.py (DialogueEngine wrapping graph; process/finalize/reset). Happy path + missing
  field (#1) + hangup finalize (#8). Template-first response (2-3 variants). Normalization called
  per-field after extraction (D2). Measurement Gate: measure template-only vs LLM-turn latency.
acceptance:
  - G_3 happy path 4 turns: finalize() returns correct FinalOutput; no re-ask of confirmed fields.
  - finalize() mid-call: unconfirmed fields = null.
  - Measurement Gate: latency for template-only turn and LLM turn both logged.
  - LangGraph 4 hard rules respected (see DEC-02 in decisions.md).
scope: dialogue/state.py, dialogue/graph.py, dialogue/nodes.py, dialogue/engine.py, dialogue/response.py
task: TASK-A13 [A]
track: A

### REQ-post-call
source: TASKGRAPH.md (TASK-A14), BLUEPRINT.md (§1 post-call track)
id: REQ-post-call
description: dialogue/post_call.py: runs once on call end (done or hangup). Feeds full transcript
  to 1 LLM call -> PostCall(short_summary, sentimental_analysis, emergency).
acceptance:
  - Given accident transcript, emergency="yes", sentimental_analysis in {urgent, frustrated,...},
    summary 1-2 sentences.
  - Runs exactly once per call, not in the turn loop.
scope: dialogue/post_call.py
task: TASK-A14 [A]
track: A

---

## Wave 1 — Track B (Voice/Sensor) — STATUS: COMPLETE

### REQ-normalization
source: TASKGRAPH.md (TASK-B10), BLUEPRINT.md (D2, D3, §5 REQ-13)
id: REQ-normalization
description: normalization/vietnamese_numbers.py implements Normalizer protocol. normalize_field
  (name, raw) -> NormResult(value, parse_failed). Per-field typed normalization: spoken digits to
  phone (10 digits), license plate (canonical form), VIN (17 chars uppercased), odo (integer km),
  free-text (whitespace cleaned). tests/test_normalization.py with >=15 cases.
  Short-pause tolerance: "30F" + pause + "1234" treated as one plate input.
acceptance:
  - "khong chin mot hai ba bon nam sau bay tam" -> "0912345678"
  - "ba muoi a cham nam sau bay cham tam chin" -> canonical plate form
  - "khong chin mot" (incomplete) -> parse_failed=True
  - Tolerate numeric field pauses: two-part plate after re-join -> parse PASS
  - >=15 test cases pass
scope: normalization/vietnamese_numbers.py, tests/test_normalization.py
task: TASK-B10 [B]
track: B
status: COMPLETE (17 pytest tests passing per PHASE_0_1_B_UPDATE.md)

### REQ-asr-wrapper
source: TASKGRAPH.md (TASK-B11), BLUEPRINT.md (D1, §3 ASR)
id: REQ-asr-wrapper
description: asr/faster_whisper_asr.py implements ASR protocol. Supports live mic buffer
  transcription (language="vi", compute_type="int8") and from_file() for WER eval. Default model
  PhoWhisper-medium CT2; fallback generic faster-whisper. Measures latency_ms. Model lazy-loads
  on first transcription.
acceptance:
  - Given .wav Vietnamese file, from_file() returns reasonable transcript + latency_ms.
  - Given mic buffer, transcribe() returns ASRResult.
scope: asr/faster_whisper_asr.py
task: TASK-B11 [B]
track: B
status: COMPLETE (per PHASE_0_1_B_UPDATE.md)

### REQ-mic-vad
source: TASKGRAPH.md (TASK-B12), BLUEPRINT.md (§3 audio)
id: REQ-mic-vad
description: audio/recorder.py (sounddevice, 16kHz mono float32) and audio/vad.py (turn
  segmentation). Phase 1: EnergyVAD (deterministic, import-safe). Phase 2: SileroVAD behind
  same interface. Extended silence timeout for READBACK_REQUIRED fields to avoid false garbled
  triggers mid-number.
acceptance:
  - Given one spoken sentence then silence, VAD cuts exactly 1 utterance, returns numpy buffer.
  - For phone/plate/VIN fields, short pauses mid-number do NOT trigger VAD cutoff.
scope: audio/recorder.py, audio/vad.py
task: TASK-B12 [B]
track: B
status: COMPLETE (per PHASE_0_1_B_UPDATE.md)

### REQ-corpus
source: TASKGRAPH.md (TASK-B13), PLAN.md (Phase 1), BLUEPRINT.md (§5 REQ-14)
id: REQ-corpus
description: scenarios/g1..g5.json + exceptions.json with realistic Vietnamese caller utterances
  (colloquial, agitated, abbreviated, spoken numbers). Turn-by-turn format: user input + expected
  {category, fields, signals}. >=2 scenarios/category (>=10 total) + >=3 exception scenarios.
  B writes user input; A defines expected output.
acceptance:
  - All JSON files parse cleanly.
  - >=10 scenario files + >=3 exception scenarios.
  - Field names in expected match schemas.py exactly.
  - Vietnamese is realistic, not "textbook".
scope: scenarios/*.json
task: TASK-B13 [B] (A reviews expected output)
track: B / shared (A reviews)
status: COMPLETE (per PHASE_0_1_B_UPDATE.md — G_1 through G_5 + exception cases)

### REQ-wer-audio
source: TASKGRAPH.md (TASK-B14), BLUEPRINT.md (D5)
id: REQ-wer-audio
description: Collect >=5 real Vietnamese audio clips (diverse speakers, spoken phone numbers /
  plate numbers) with reference transcripts. Store as scenarios/audio/*.wav + *.reference.txt.
  Must be usable by jiwer WER evaluation (TASK-A30).
acceptance:
  - >=5 wav+reference pairs available.
  - Audio contains spoken numbers/plates as domain-real content.
scope: scenarios/audio/
task: TASK-B14 [B]
track: B
status: COMPLETE (per PHASE_0_1_B_UPDATE.md — audio fixture support in place)

---

## Wave 2 — Exception Handling & Voice I/O

### REQ-exceptions
source: TASKGRAPH.md (TASK-A20), BLUEPRINT.md (§9), PLAN.md (Phase 2)
id: REQ-exceptions
description: Implement all 8 exception handlers in dialogue/exceptions.py and integrate into
  engine.process(). All handlers are deterministic and flag-driven (not LLM-memory). See DEC-24
  in decisions.md for full specification of each exception.
acceptance (per TASKGRAPH.md TASK-A20):
  - #2 correction: update field, no re-ask of confirmed fields
  - #3 ambiguous: exactly 1 clarification question before routing
  - #4 out-of-scope: apologize + offer human
  - #5 garbled: parse_failed -> readback + confirm before storing
  - Readback (D10): phone/plate/VIN always readback even when parse OK
  - #6 emergency: detect immediately -> hotline + skip low-priority fields
  - #7 stuck: 2 turns no progress -> offer human
scope: dialogue/exceptions.py, dialogue/nodes.py, dialogue/engine.py
task: TASK-A20 [A]
track: A
status: PENDING

### REQ-eval-harness
source: TASKGRAPH.md (TASK-A21), PLAN.md (Phase 2)
id: REQ-eval-harness
description: eval/run_eval.py feeds scenario corpus through engine in text mode. eval/metrics.py
  computes slot precision/recall/F1 and routing accuracy. tests/test_exception_handling.py (>=3
  exception cases), test_dialogue_state.py, test_field_extraction.py, test_final_output_schema.py.
acceptance:
  - Given corpus, run_eval.py outputs slot F1 + routing accuracy per category.
  - pytest >=3 exception tests pass.
scope: eval/run_eval.py, eval/metrics.py, tests/test_exception_handling.py (and others)
task: TASK-A21 [A]
track: A
status: PENDING

### REQ-tts-piper
source: TASKGRAPH.md (TASK-B20), BLUEPRINT.md, TECHSTACK.md (§4)
id: REQ-tts-piper
description: tts/piper_tts.py implements TTS protocol with Piper local ONNX (Vietnamese voice,
  vais1000 medium recommended). audio/playback.py plays audio output. Measures latency_ms.
  Swap-able via .env TTS_ENGINE=piper. edge_tts.py and vixtts.py as stub-pluggable alternatives.
acceptance:
  - Given Vietnamese sentence, synthesize() returns TTSResult with audio bytes + latency_ms.
  - Audio is playable.
  - Local only; no network calls.
scope: tts/piper_tts.py, audio/playback.py
task: TASK-B20 [B]
track: B
status: PENDING

### REQ-pipeline-cli
source: TASKGRAPH.md (TASK-B21), BLUEPRINT.md (D4, §5 REQ-12, REQ-17)
id: REQ-pipeline-cli
description: pipeline.py implements turn(): audio -> ASR -> engine.process -> TTS, logging
  asr_latency_ms, llm_latency_ms, tts_latency_ms per turn. main.py CLI with --voice (mic loop)
  and --text (keyboard/stdin for dev/eval). Measurement Gate: log both template-only latency and
  E2E latency BEFORE any optimization. Silence-timeout/disconnect/Ctrl-C -> engine.finalize()
  -> partial JSON (#8, D4).
acceptance:
  - Given live mic, 1 turn runs ASR -> engine -> reply end-to-end with latency breakdown printed.
  - Given --text flag, keyboard input works.
  - Given Ctrl-C or silence-timeout, engine.finalize() called -> partial JSON with nulls.
  - Measurement Gate data logged.
scope: pipeline.py (B owns, A reviews), main.py
task: TASK-B21 [B]
track: B (owner), A (reviewer)
dependency: TASK-A13 must be merged to main before B writes pipeline.py
status: PENDING

### REQ-gradio-ui
source: TASKGRAPH.md (TASK-B22), PLAN.md (Phase 2)
id: REQ-gradio-ui
description: Gradio web UI with mic input, transcript display, live JSON panel (state/final output),
  TTS playback button. Wraps pipeline.turn() without adding new logic. Used for signature demo video.
acceptance:
  - Given browser, spoken input produces visible transcript + live JSON state panel update.
scope: Gradio UI file (main.py or separate gradio_app.py)
task: TASK-B22 [B]
track: B
status: PENDING

---

## Wave 3 — Evaluation, Demo & Report

### REQ-metrics-full
source: TASKGRAPH.md (TASK-A30), PLAN.md (Phase 3), BLUEPRINT.md (§5 REQ-14 through REQ-17)
id: REQ-metrics-full
description: Full metric suite: confusion matrix 5x5, emergency recall (adversarial set including
  "calm voice" emergencies), sentiment accuracy, WER via jiwer on scenarios/audio/, LLM-as-judge
  naturalness (dev-time only, documented), latency E2E + breakdown p50/p95 per component.
acceptance:
  - Output includes all metrics + emergency recall separately + latency p50/p95.
scope: eval/metrics.py
task: TASK-A30 [A]
track: A
status: PENDING

### REQ-ablation
source: TASKGRAPH.md (TASK-A31), PLAN.md (Phase 3)
id: REQ-ablation
description: Ablation study comparing: with/without state-machine, with/without recall tuning,
  Qwen3 vs Vietnamese-tuned variant, laptop medium vs GPU large WER. Each run explicitly configured;
  delta table produced.
acceptance:
  - Comparison table with numbers for each ablation decision.
scope: eval/ (ablation runs)
task: TASK-A31 [A]
track: A
status: PENDING

### REQ-eval-report
source: TASKGRAPH.md (TASK-A32), PLAN.md (Phase 3), BLUEPRINT.md (§5 REQ-21)
id: REQ-eval-report
description: docs/EVALUATION_REPORT.md (Deliverable #4): all metrics + failure analysis
  (what failed + WHY + remediation direction) + latency + ablation + honest limitations + note
  stating "Naturalness scored by <JUDGE_MODEL>, eval-only, submitted version does not depend on this."
acceptance:
  - Covers >=5 categories + >=3 exception + >=1 automated metric + failure cases + latency per turn.
  - Does not gloss over failures.
scope: docs/EVALUATION_REPORT.md
task: TASK-A32 [A]
track: A
status: PENDING

### REQ-signature-demo
source: TASKGRAPH.md (TASK-B30), PLAN.md (§5.1, §5.2)
id: REQ-signature-demo
description: Record signature demo video via Gradio showing: (1) emergency-priority + correction +
  garbled-confirm + no-re-ask + normalization + JSON emergency=yes in ~90 seconds, AND (2) "calm
  voice" emergency case (caller sounds calm but is in danger). May swap to edge_tts for better
  voice quality during recording; submitted version uses Piper local (documented in report).
acceptance:
  - Video demonstrates: emergency detection, correction without re-ask, garbled readback,
    normalization of spoken numbers, final JSON with emergency=yes.
scope: Gradio UI + recording
task: TASK-B30 [B]
track: B
status: PENDING

### REQ-architecture-doc
source: TASKGRAPH.md (TASK-S30), PLAN.md (§6 Deliverable #1), BLUEPRINT.md (§5 REQ-20)
id: REQ-architecture-doc
description: docs/ARCHITECTURE.md (Deliverable #1) finalized: pipeline, model choices, conversation
  flow, 8 exception strategies, decisions + trade-offs including rejected alternatives (FSM-only,
  edge-tts primary, RAG). A writes dialogue/exception/eval sections; B writes ASR/TTS/normalization
  /pipeline sections.
acceptance:
  - Document is consistent with actual code.
  - Contains trade-off tables with rejected alternatives.
scope: docs/ARCHITECTURE.md
task: TASK-S30 [PAIR]
track: both
status: PARTIAL (B-side sections complete per PHASE_0_1_B_UPDATE.md)

### REQ-reproducibility
source: TASKGRAPH.md (TASK-S31), PLAN.md (Phase 3), BLUEPRINT.md (§5 REQ-19)
id: REQ-reproducibility
description: requirements.txt pinned == (including langgraph, langchain-core — D12). scripts/setup.ps1
  and setup.sh pull Ollama models + ASR/TTS weights + document minimum hardware. .env.example
  complete. README runnable. Repo scanned for secret leaks.
acceptance:
  - pip install -r requirements.txt on clean machine succeeds.
  - Bot runs following README instructions.
  - git grep finds no hardcoded secrets.
scope: requirements.txt, scripts/, .env.example, README.md
task: TASK-S31 [PAIR]
track: both
status: PENDING

### REQ-verify-gate3
source: TASKGRAPH.md (TASK-S32)
id: REQ-verify-gate3
description: Cross-check all requirements against REQ matrix in BLUEPRINT.md §5. Walk through all
  5 categories + >=3 exceptions. Generate Verify Report.
acceptance:
  - 5 deliverables complete.
  - 5 categories + >=3 exceptions covered in eval.
  - Latency report present.
  - Failure analysis honest.
  - Repro passes.
  - No secrets in code.
scope: verification pass
task: TASK-S32 [PAIR]
track: both
status: PENDING

---

## Requirements Cross-Reference (BLUEPRINT.md §5 REQ Matrix)

REQ-01  ASR mic->transcript Vietnamese      -> REQ-asr-wrapper, REQ-mic-vad
REQ-02  LLM local + LangGraph StateGraph    -> REQ-llm-client, REQ-langgraph-engine
REQ-03  5 categories + correct fields + JSON -> REQ-schemas, REQ-categories, REQ-nlu, REQ-langgraph-engine
REQ-04  Post-call summary/sentiment/emergency -> REQ-post-call
REQ-05  Exc #1 missing — no re-ask          -> REQ-langgraph-engine, REQ-exceptions
REQ-06  Exc #2 correction — update no repeat -> REQ-exceptions
REQ-07  Exc #3 ambiguous — 1 clarification  -> REQ-exceptions
REQ-08  Exc #4 out-of-scope — redirect      -> REQ-exceptions
REQ-09  Exc #5 garbled — parse_failed -> readback -> REQ-normalization, REQ-exceptions
REQ-10  Exc #6 emergency — hotline, skip low fields -> REQ-exceptions
REQ-11  Exc #7 stuck 2+ — offer human       -> REQ-exceptions
REQ-12  Exc #8 hangup — partial JSON null   -> REQ-langgraph-engine, REQ-exceptions, REQ-pipeline-cli
REQ-13  Normalization per-field post-extraction -> REQ-normalization (Team differentiator, P0)
REQ-14  Eval >=10 scenarios + >=3 exception -> REQ-corpus, REQ-eval-harness, REQ-metrics-full
REQ-15  >=1 automated metric                -> REQ-eval-harness (slot F1 minimum)
REQ-16  Failure analysis honest             -> REQ-eval-report
REQ-17  Latency E2E + breakdown p50/p95     -> REQ-pipeline-cli, REQ-metrics-full
REQ-18  TTS Vietnamese (+5 bonus)           -> REQ-tts-piper
REQ-19  requirements.txt pin + no secrets   -> REQ-reproducibility
REQ-20  Architecture Doc                    -> REQ-architecture-doc
REQ-21  Eval Report                         -> REQ-eval-report
REQ-22  Always readback phone/plate/VIN     -> REQ-exceptions (D10)
REQ-23  Allowed value sets (D9)             -> REQ-schemas (dialogue/values.py)
REQ-24  >=5 .wav Vietnamese + reference     -> REQ-wer-audio

# decisions.md — Architectural Decisions Intel
# Synthesized from: BLUEPRINT.md (ADR, locked, precedence 0), TECHSTACK.md (ADR, locked, precedence 1)
# Supporting sources: PLAN.md (PRD, precedence 2), TASKGRAPH.md (SPEC, precedence 3),
#                     ARCHITECTURE.md (DOC, precedence 5), PHASE_0_1_B_UPDATE.md (DOC, precedence 6)
# Generated: 2026-06-25

---

## DEC-01 — Architecture Philosophy: Thin LLM + Thick State Machine
source: BLUEPRINT.md, TECHSTACK.md
status: LOCKED (both ADRs agree, highest-precedence sources)
scope: overall dialogue architecture

Decision: The LLM handles only NLU/NLG. Deterministic FSM (LangGraph StateGraph) owns all slot
state and field-selection logic. The LLM performs exactly four functions: (1) classify intent,
(2) extract entities, (3) generate natural-language phrases, (4) summarize post-call.

Rejected alternatives: LLM holding conversation state through prompt history (re-asks field already
confirmed, forgets corrections, breaks at exception #1/#2/#8).

---

## DEC-02 — Dialogue Runtime: LangGraph StateGraph
source: BLUEPRINT.md (D12), TECHSTACK.md
status: LOCKED
scope: dialogue/graph.py, dialogue/engine.py, dialogue/nodes.py

Decision: LangGraph StateGraph is the dialogue orchestration runtime. The graph has exactly 5 nodes:
nlu -> route -> slot_update -> next_field -> respond. The graph is capped at <=7 nodes total.

LangGraph application constraints (4 hard rules, from BLUEPRINT.md §1A):
1. CallState IS the LangGraph StateGraph state schema — single source of truth. No parallel state objects.
2. One turn = one graph.invoke() call. NEVER use interrupt().
3. No persistent checkpointer. Engine holds CallState in-memory per call. MemorySaver thread-per-call
   is optional; no durable saver needed for demo scope.
4. ONE parameterized slot-filling loop via categories.py — NOT 5 subgraphs per category.

Node convention: every node is a pure function (state) -> update dict. No self/global mutation.
No hidden state outside CallState.

Rejected alternatives: hand-rolled FSM Python loop (loses native routing and checkpointing alignment
with VinSmart/XeCare stack).

---

## DEC-03 — ASR Runtime: PhoWhisper-CT2 Default, generic faster-whisper fallback
source: BLUEPRINT.md (D1), TECHSTACK.md, TASKGRAPH.md (D1)
status: LOCKED
scope: asr/faster_whisper_asr.py, asr/base.py

Decision: PhoWhisper-medium CT2 int8 is the default ASR model (best Vietnamese WER on CPU).
Generic faster-whisper (medium or small) is the fallback if CT2 conversion fails or latency is too
high. PhoWhisper-large on GPU PC is used only for offline WER evaluation, not for live demo.

Model configured via .env: ASR_MODEL=phowhisper-medium (default); compute_type=int8; device=cpu.
Language forced to "vi".

---

## DEC-04 — LLM Runtime: Ollama + Qwen 7-8B
source: TECHSTACK.md, BLUEPRINT.md
status: LOCKED
scope: llm/ollama_client.py, config.py

Decision: Ollama (Windows-native, OpenAI-compatible API) with Qwen 7-8B (qwen3:8b default,
qwen2.5:7b-instruct fallback). keep_alive keeps model resident to avoid cold-load per turn.
A/B with one Vietnamese-tuned Qwen variant for ablation eval.

Fallback ladder (triggered by measurement, not pre-optimized): Qwen3-8B -> 4B -> smaller.
No semantic cache (each turn is unique slot-filling).

Config: OLLAMA_HOST, LLM_MODEL from .env only. Never hardcoded.

Rejected alternatives: vLLM (requires GPU/Linux), llama.cpp (less ergonomic on Windows).

---

## DEC-05 — TTS: Piper Local ONNX Primary, Pluggable Interface
source: BLUEPRINT.md, TECHSTACK.md
status: LOCKED
scope: tts/piper_tts.py, tts/base.py

Decision: Piper local ONNX is the primary TTS engine (reproducible offline, safe +5pts bonus).
Voice model: vais1000 medium recommended. Interface tts/base.py is pluggable so edge_tts.py can be
swapped for the signature video demo (documented swap; submitted/reproduced version always uses Piper).
vixtts.py available for GPU premium clip only.

Rationale for Piper over edge-tts: reproducibility is 20pts; graders may run offline. edge-tts
cloud endpoint is unofficial and can be rate-limited. The architectural story requires a fully local
stack (ASR + LLM + TTS).

TTS is after the core is solid (TTS/UI only after core — PLAN.md principle).

---

## DEC-06 — Audio I/O: sounddevice + numpy
source: TECHSTACK.md, BLUEPRINT.md
status: LOCKED
scope: audio/recorder.py, audio/playback.py

Decision: sounddevice + numpy over PyAudio. Fewer Windows build issues; numpy-native 16 kHz mono
float32 buffers align with faster-whisper input format.

---

## DEC-07 — VAD: silero-vad for Turn Segmentation
source: TECHSTACK.md
status: LOCKED
scope: audio/vad.py

Decision: silero-vad for turn-boundary detection. Extended silence timeout for READBACK_REQUIRED
fields (phone, owner_phone, order_phone, license_plate_vin) to prevent garbled-exception false
positives when callers pause mid-number. Phase 1 uses EnergyVAD (deterministic, import-safe);
Phase 2 upgrades to full silero-vad behind the same interface.

Rejected alternatives: webrtcvad (does not capture full sentences as well for turn-taking).

---

## DEC-08 — Vietnamese Entity Normalization: Per-Field, Post-LLM-Extraction
source: BLUEPRINT.md (D2, D3), TECHSTACK.md, TASKGRAPH.md (D2, D3)
status: LOCKED
scope: normalization/vietnamese_numbers.py, normalization/base.py

Decision (D2): Normalization runs per-field AFTER LLM extraction, not pre-LLM whole-utterance.
Knowing the field type before normalizing prevents corruption of free-text fields
(e.g., "anh Nam" -> "anh 5" would be wrong for name fields).

Decision (D3): Garbled exception #5 is triggered by the validator's parse_failed flag, NOT by
ASR confidence score. This is deterministic and more reliable.

API: normalize_field(name: str, raw: str) -> NormResult(value: str | None, parse_failed: bool)

Field-specific normalization rules:
- phone fields: spoken digits -> exactly 10 digits
- license_plate_vin: spoken plates -> canonical form (e.g., 30A-567.89); 17-char VINs uppercased
- current_odo: spoken distance (e.g., "nam van cay") -> integer km
- free-text fields: whitespace cleaned; semantic content preserved

Rejected alternative: pre-LLM whole-utterance normalization (corrupts context).

---

## DEC-09 — Structured Output: Pydantic v2 + Ollama JSON/format Mode
source: TECHSTACK.md, BLUEPRINT.md
status: LOCKED
scope: models/schemas.py, llm/ollama_client.py

Decision: Pydantic v2 for all DTOs. Ollama JSON/format mode enforces schema-correct output.
No instructor or outlines dependency. Validators return parse_failed (not exceptions) for phone,
VIN, plate fields (D3).

---

## DEC-10 — Response Strategy: Template-First, LLM Only for High-Variance Turns
source: BLUEPRINT.md (§1A Part 1), TECHSTACK.md
status: LOCKED
scope: dialogue/response.py

Decision: Template responses (field questions, readback confirmations, simple acknowledgements) do
NOT call the LLM. Each template has 2-3 variants rotated to avoid robotic repetition.
response.render(next_action, state) -> str picks template or calls LLM by next_action type.

LLM is called ONLY for: emergency reassurance (#6), ambiguity clarification (#3), out-of-scope
redirect (#4), call-close + post-call summary.

This cuts ~1 LLM call per turn for the majority of turns (latency reduction + thin-LLM).

---

## DEC-11 — Data Contract: models/schemas.py FROZEN After Wave 0
source: BLUEPRINT.md (§2), TECHSTACK.md, PLAN.md, TASKGRAPH.md (TASK-002), WORKFLOW.md
status: LOCKED
scope: models/schemas.py, all */base.py interface files

Decision: models/schemas.py and all */base.py files are frozen after TASK-003 merges to main.
Signature changes require both tracks to agree and both to pull immediately.

Frozen schemas:
- SlotStatus (str, Enum): EMPTY | PENDING | CONFIRMED | CORRECTED
- Slot: value, status, raw_utterance, confirmed_at
- IntentSignals: emergency, out_of_scope, correction, hangup (all bool, default False)
- NLUResult: category (Category | None), extracted_fields, corrected_fields, signals
- PostCall: short_summary, sentimental_analysis, emergency (Literal["yes","no"])
- FinalOutput: category (Category | None), fields (dict[str, str | None]), post_call
- TurnResult: reply, done (bool), state (dict)
- READBACK_REQUIRED = {"phone", "owner_phone", "order_phone", "license_plate_vin"}

Frozen base protocols:
- ASR Protocol: transcribe(audio, sample_rate=16000) -> ASRResult; from_file(path) -> ASRResult
- LLM Protocol: complete(system, user, json_schema=None) -> LLMResult
- TTS Protocol: synthesize(text) -> TTSResult
- Normalizer Protocol: normalize_field(name, raw) -> NormResult
- DialogueEngine: process(user_text) -> TurnResult; finalize() -> FinalOutput; reset() -> None

---

## DEC-12 — READBACK_REQUIRED: Always Readback Phone/Plate/VIN Before Confirming
source: BLUEPRINT.md (D10), TASKGRAPH.md (D10)
status: LOCKED
scope: dialogue/nodes.py (slot_update_node), dialogue/categories.py

Decision: phone, owner_phone, order_phone, license_plate_vin ALWAYS require readback before slot
status reaches CONFIRMED. Exception: during an emergency (#6), readback is deferred (emergency
takes priority over readback). After the emergency is handled (hotline provided, minimum rescue
info collected), deferred readback for identity fields proceeds.

---

## DEC-13 — Emergency Detection: Hybrid (LLM flag OR keyword OR sentiment=="urgent")
source: BLUEPRINT.md (§1, §9)
status: LOCKED
scope: dialogue/exceptions.py, dialogue/nodes.py

Decision: Emergency (#6) is detected by ANY of three signals:
  - LLM NLU flag (signals.emergency=True)
  - keyword match (keyword list in code with tests, NOT in prompt; keywords: tai nan, chay, ket cao toc, mat phanh, etc.)
  - sentiment == "urgent" (frustrated != emergency, to avoid false positives)

Emergency is a RECALL-tuned problem (cost-asymmetry: missing a real emergency is worse than
false alarm). Emergency BEATS readback (D10): in emergency, skip low-priority fields, defer
readback, provide hotline immediately. Collect minimum for dispatch: location + callback number.

---

## DEC-14 — Hangup Handling: Two Paths Both Route to engine.finalize()
source: BLUEPRINT.md (D4), TASKGRAPH.md (D4)
status: LOCKED
scope: pipeline.py (B21), dialogue/engine.py

Decision (D4): Two hangup paths:
1. Verbal hangup: signals.hangup=True in NLUResult -> route_node politely closes -> engine.finalize()
2. I/O hangup: pipeline.turn() detects silence-timeout / disconnect / Ctrl-C -> calls engine.finalize() directly

Both paths: finalize() collects confirmed slots; unconfirmed slots -> null in FinalOutput.
Never raises. Post-call LLM call triggered on finalize().

---

## DEC-15 — No RAG for Policy (G_2/G_4)
source: BLUEPRINT.md, TECHSTACK.md, PLAN.md, ARCHITECTURE.md
status: LOCKED (all sources agree)
scope: dialogue/response.py, G_2 warranty, G_4 motorcycle warranty categories

Decision: Static warranty policy for G_2/G_4 (no RAG). Time freed by avoiding RAG is invested in
the eval framework (25pts). Static policy keeps complexity low, is reproducible, and avoids the
retrieval-quality risk.

---

## DEC-16 — Latency: Measure E2E + Per-Component Breakdown; Measure Before Optimizing
source: BLUEPRINT.md (D11, §1A Part 3-4), TASKGRAPH.md (D11, Measurement Gate)
status: LOCKED
scope: utils/latency.py, pipeline.py, eval/metrics.py

Decision (D11): Report latency as p50/p95 per component (ASR/LLM/TTS) AND E2E per turn.
Also measure template-only latency (no LLM call) vs LLM turn as a comparison data point.
Measurement Gate: MEASURE before any optimization. No pre-optimization allowed.

ASRResult.latency_ms, LLMResult.latency_ms, TTSResult.latency_ms are required fields on all
result objects.

Fallback ladder for latency (triggered by measurement): Qwen3-8B -> 4B; PhoWhisper medium -> small.

---

## DEC-17 — LLM-as-Judge: Strongest Available Cloud Model, Dev-Time Only, Documented
source: BLUEPRINT.md (D7), TASKGRAPH.md (D7)
status: LOCKED
scope: eval/metrics.py

Decision (D7): LLM-as-judge for naturalness eval uses the strongest available cloud model
(via .env JUDGE_MODEL), at dev-time only. Qwen-local as fallback. The submitted bot does not
depend on the judge model at inference time. Evaluation report must explicitly state:
"Naturalness scored by <JUDGE_MODEL>, eval-only; submitted version does not depend on this."

---

## DEC-18 — WER Audio Corpus: Collect >=5 Real Vietnamese Clips (Track B Owns)
source: BLUEPRINT.md (D5), TASKGRAPH.md (D5, TASK-B14)
status: LOCKED
scope: scenarios/audio/*.wav, TASK-B14

Decision (D5): Track B collects >=5 real Vietnamese audio clips (diverse speakers, must include
spoken phone numbers / plate numbers) with reference transcripts for jiwer WER evaluation.
Rationale: real voice + real domain is more convincing than Common Voice vi.

---

## DEC-19 — Track Ownership Split
source: BLUEPRINT.md (D6), PLAN.md (§4), TASKGRAPH.md, WORKFLOW.md
status: LOCKED
scope: all source files

Decision (D6): Current track split retained. Track A (Hiep) owns dialogue/llm/eval/tests(dialogue).
Track B (Phuong) owns audio/asr/tts/normalization/main.py/Gradio UI.

File ownership rules:
- Each file has exactly one owner.
- Touching another person's file requires notifying them first.
- pipeline.py is owned by Track B, reviewed by Track A. B must not write pipeline.py
  until TASK-A13 (engine) has merged to main.
- requirements.txt: append-only, alphabetical, union-on-conflict (never delete other track's lines).
- models/schemas.py + */base.py: frozen after Wave 0. Changes require both tracks to agree and pull.

---

## DEC-20 — Allowed Value Sets for Classification Fields (D9)
source: BLUEPRINT.md (D9), TASKGRAPH.md (D9, TASK-002)
status: LOCKED (field NAMES frozen; value SETS provisional pending real VinFast data confirmation)
scope: dialogue/values.py, models/schemas.py

Decision (D9): Allowed value sets defined in dialogue/values.py:
- vehicle_type (G_1): {"o to dien", "xe may dien"}
- vehicle_usage_type (G_2): {"ca nhan", "kinh doanh/dich vu", "taxi (GSM)"}
- customer_type (G_3): {"ca nhan", "doanh nghiep", "dai ly"}

NOTE: Value sets are PROVISIONAL (see TODO in values.py). Wave 0 freezes field NAMES; value sets
can be tightened later without breaking the contract (fields remain str type).

---

## DEC-21 — Setup Scripts Pull Models; Pin Minimum Hardware Requirements
source: BLUEPRINT.md (D8), TASKGRAPH.md (D8, TASK-S31)
status: LOCKED
scope: scripts/setup.ps1, scripts/setup.sh, README.md

Decision (D8): scripts/setup.ps1 and setup.sh pull Ollama models + ASR/TTS weights and document
minimum hardware requirements. This is required because pip install does not pull ~7GB model weights.

Hardware split:
- Zenbook CPU laptop: live demo (faster-whisper medium int8, Qwen Q4, Piper)
- GPU PC: offline WER eval (PhoWhisper-large), optional premium TTS clip

---

## DEC-22 — Evaluation Stack (Comprehensive)
source: TECHSTACK.md (§6), BLUEPRINT.md (§5 REQ matrix), PLAN.md (§3 Phase 3), TASKGRAPH.md
status: LOCKED
scope: eval/run_eval.py, eval/metrics.py

Decision: Full evaluation stack required:
- pytest + scenario JSON fixtures (turn-by-turn, text mode, no ASR noise)
- Routing confusion matrix (5x5)
- Slot precision/recall/F1 per field
- Emergency recall (adversarial set with "calm voice" emergency cases)
- WER via jiwer on >=5 real .wav clips
- LLM-as-judge naturalness (dev-time only, documented — DEC-17)
- Latency p50/p95 breakdown ASR/LLM/TTS + E2E
- Ablation study: state-machine vs no-state-machine, recall tuning, Qwen vs Vietnamese-tuned,
  laptop medium vs GPU large WER
- Failure analysis: sai gi + VI SAO + huong sua (honest, not glossed over)

Minimum per brief: >=2 scenario/category (>=10 total) + >=3 exception scenarios + >=1 automated
metric. Project plan exceeds minimums.

---

## DEC-23 — Category Fields Per Brief (FROZEN in schemas)
source: BLUEPRINT.md (§2, §8), TECHSTACK.md (§8), TASKGRAPH.md (TASK-002)
status: LOCKED
scope: models/schemas.py, dialogue/categories.py

Decision: Field names are EXACTLY per brief. No renaming.

G_1 (Roadside Rescue): current_location(10), vehicle_condition(20), phone(30), city_name(40),
  full_name(50), vehicle_model(60), license_plate_vin(70), vehicle_type(80), current_odo(95 — skip when emergency)
G_2 (Warranty/Repair): full_name, owner_phone, vehicle_model, vehicle_usage_type,
  license_plate_vin, service_center, vehicle_condition
G_3 (Orders): full_name, order_phone, order_code_dealer, customer_type
G_4 (Motorcycle Warranty): full_name, phone, vehicle_line, license_plate_vin,
  current_location, vehicle_condition
G_5 (Remote Tech Support): full_name, phone, license_plate_vin, vehicle_line,
  current_odo (optional/required=False), vehicle_condition_details

WARNING: field names differ per category:
  G_1/G_4/G_5 use "phone"; G_2 uses "owner_phone"; G_3 uses "order_phone"
  G_1/G_2 use "vehicle_model"; G_4/G_5 use "vehicle_line"
  Wrong field name = lost Pipeline points.

---

## DEC-24 — 8 Exception Handlers Required (All Deterministic)
source: BLUEPRINT.md (§9), TECHSTACK.md (§9), PLAN.md (Phase 2)
status: LOCKED
scope: dialogue/exceptions.py, dialogue/nodes.py

Decision: Exactly 8 exception strategies, all implemented deterministically based on NLU flags
(not LLM memory):
  #1 Missing field: ask next EMPTY field by priority; never re-ask CONFIRMED field
  #2 Correction: overwrite slot, acknowledge, continue — no repeat of confirmed fields
  #3 Ambiguous intent: ask EXACTLY 1 clarification question before routing
  #4 Out-of-scope: apologize + redirect or offer human transfer
  #5 Garbled: validator parse_failed -> readback + confirm before storing
  #6 Emergency: hybrid detect -> hotline immediately + skip low-priority fields + defer readback
  #7 Stuck 2+ turns: failed_turns >= 2 -> offer human transfer
  #8 Hangup: silence-timeout/disconnect/Ctrl-C -> finalize() -> partial JSON, unconfirmed = null

Post-call track runs once on done/hangup: full transcript -> 1 LLM call -> PostCall schema.

---

## DEC-25 — Text-First Development Principle
source: PLAN.md (§2 principle 3), BLUEPRINT.md (§3)
status: from PRD (precedence 2); consistent with all ADR sources
scope: eval/run_eval.py, dialogue/engine.py, main.py

Decision: Dialogue core must run and test in text mode before voice I/O is added. DialogueEngine
is interface-agnostic (accepts/returns text only). This decouples dialogue bugs from audio bugs.
TTS and UI are built only after the dialogue core is solid.

---

## DEC-26 — Secrets Handling: .env Only, Never Hardcoded
source: TECHSTACK.md, PLAN.md, WORKFLOW.md (§8), TASKGRAPH.md (TASK-S31)
status: LOCKED
scope: config.py, .env.example, .gitignore

Decision: python-dotenv + .env file for all secrets. .env is gitignored. .env.example documents
required keys: OLLAMA_HOST, LLM_MODEL, ASR_MODEL, ASR_DEVICE, ASR_COMPUTE_TYPE, JUDGE_MODEL, HF_TOKEN.
No secrets in code. Repo scanned before submission (Gate 3 / TASK-S32).

---

## DEC-27 — Python 3.11, pip + venv, requirements.txt with == Pinning
source: TECHSTACK.md
status: LOCKED
scope: pyproject.toml, requirements.txt, venv

Decision: Python 3.11 minimum (specified in pyproject.toml requires-python=">=3.11").
pip + venv (standard library only). No uv, poetry, or conda. requirements.txt with == pinning
(append-only, alphabetical, union-on-conflict). Grader must be able to run pip install -r
requirements.txt on a clean machine without internet at inference time.

---

## Current Status (from PHASE_0_1_B_UPDATE.md)
source: docs/PHASE_0_1_B_UPDATE.md (DOC, precedence 6)

Track B Phase 0 + Phase 1 (Waves 0-1) are COMPLETE:
- B10 Vietnamese normalization + 17 passing pytest tests
- B11 ASR wrapper with file-mode support
- B12 Microphone capture + VAD (EnergyVAD for Phase 1; SileroVAD slot ready)
- B13 Scenario corpus (G_1 through G_5 + exception cases)
- B14 Audio fixture support for WER evaluation
- Audio scaffolding: faster_whisper_asr.py, recorder.py, vad.py, playback.py all import-safe

Track B Phase 2 items still pending: B20 (TTS Piper), B21 (Pipeline + CLI), B22 (Gradio UI)
Track A status: not captured in B-side docs — coordinate before Phase 2 start.

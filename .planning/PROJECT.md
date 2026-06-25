# VinFast Callbot — Track B (Senses & Voice)

**Project:** VinSmart Future AI Internship · Task 3 · 2-week timeline
**Developer:** Phương (Person B — Track B)
**Teammate:** Hiệp (Person A — Track A, owns dialogue/llm/eval)
**Status:** Active — Wave 2 pending (B20/B21/B22)
**Branch:** phuong (PRs target main)

## Overview

Track B owns the "Giác quan & Giọng" (Senses & Voice) half of a Vietnamese-language customer-service voice callbot for VinFast. This covers everything between the microphone and the dialogue engine, plus voice output: Vietnamese spoken-entity normalization, ASR (PhoWhisper-CT2 / faster-whisper), mic capture and VAD (silero-vad), TTS (Piper local ONNX), the full audio pipeline with per-component latency measurement, the CLI and Gradio demo UI, the evaluation corpus, WER audio fixtures, the signature demo video, and the team's primary technical differentiator — robust normalization of spoken Vietnamese phone numbers, license plates, VINs, and odometers. The dialogue "brain" (LangGraph state machine, 8 exception handlers, eval harness) is Track A's work and is not built here; Track B builds against its frozen interface using the FakeDialogueEngine stub.

## Success Criteria

Per PLAN.md §0 — graders ask: "Are these the people we want to hire?"

1. **Clear design thinking:** Architecture Doc shows decisions with rejected alternatives; every line of code traceable to a brief requirement.
2. **Smooth conversation:** 5 categories run happy-path end-to-end; bot never re-asks a confirmed field; 8 exception situations all demo-able.
3. **Honest edge cases:** Failure analysis in eval report is candid; bot handles garbled numbers, calm-voice emergencies, mid-number pauses without false triggers.
4. **Vietnamese entity normalization is rock-solid:** spoken digits → phone/plate/VIN/odo normalizes correctly with ≥15 passing unit tests (currently 17).
5. **Reproducibility:** `pip install -r requirements.txt` works on a clean machine; no secrets in code; Piper TTS runs fully offline.

## Non-Goals

- Production-ready deployment or scaling
- RAG / retrieval-augmented generation for warranty policy (static only)
- Multi-caller state or persistent checkpointer
- GPU dependency at demo time (Zenbook CPU laptop is the live demo target)
- Semantic cache (each turn is unique slot-filling)

<decisions>
## Locked Decisions (BLUEPRINT.md + TECHSTACK.md ADRs)

**DEC-01 — Thin LLM + Thick State Machine:** LLM handles only NLU/NLG. LangGraph StateGraph owns all slot state and field-selection logic. LLM performs exactly: classify intent, extract entities, generate natural phrases, summarize post-call.

**DEC-02 — LangGraph 5-node graph, 4 hard rules:** nlu→route→slot_update→next_field→respond. (1) CallState IS the StateGraph schema — single source of truth. (2) One turn = one graph.invoke(), never interrupt(). (3) No persistent checkpointer. (4) One parameterized slot-filling loop — NOT 5 subgraphs per category. Graph capped at ≤7 nodes.

**DEC-03 — ASR: PhoWhisper-CT2 default, generic faster-whisper fallback.** language="vi", compute_type="int8", device=cpu. Model from .env ASR_MODEL.

**DEC-04 — LLM: Ollama + Qwen3:8b** (qwen2.5:7b-instruct fallback). keep_alive to prevent cold-load per turn. Config from .env only.

**DEC-05 — TTS: Piper local ONNX primary.** vais1000 medium voice. Pluggable via tts/base.py; edge_tts.py swap only for demo video recording. Grader repro uses Piper offline.

**DEC-06 — Audio I/O: sounddevice + numpy.** 16 kHz mono float32. Cross-platform; avoids PyAudio Windows build issues.

**DEC-07 — VAD: silero-vad for turn segmentation.** Extended silence timeout for READBACK_REQUIRED fields to prevent false garbled triggers mid-number. Phase 1 used EnergyVAD; Phase 2 upgrades to silero-vad behind same interface.

**DEC-08 — Vietnamese normalization: per-field, post-LLM-extraction (D2/D3).** Knowing the field type prevents corrupting free-text fields. parse_failed=True triggers garbled exception #5 — NOT ASR confidence score.

**DEC-09 — Pydantic v2 + Ollama JSON/format mode.** All DTOs are Pydantic BaseModel. No instructor or outlines dependency.

**DEC-10 — Template-first response strategy.** Templates (field questions, readback, acks) do NOT call LLM. LLM only for: emergency reassurance, ambiguity clarification, out-of-scope redirect, call-close + post-call summary.

**DEC-11 — Data contract FROZEN after Wave 0 (TASK-003).** models/schemas.py and all */base.py are frozen. Signature changes require both tracks to agree and both to pull immediately.

**DEC-12 — READBACK_REQUIRED = {phone, owner_phone, order_phone, license_plate_vin}.** Always readback before CONFIRMED. Emergency (#6) overrides readback — speed of dispatch > accuracy of one field.

**DEC-13 — Emergency detection: hybrid (LLM flag OR keyword OR sentiment=="urgent").** Recall-tuned: missing a real emergency is worse than a false alarm.

**DEC-14 — Hangup: two paths, both call engine.finalize().** Verbal hangup via signals.hangup=True; I/O hangup via silence-timeout/disconnect/Ctrl-C in pipeline.turn(). Unconfirmed slots → null in FinalOutput.

**DEC-15 — No RAG.** Static warranty policy for G_2/G_4. Time freed used for eval framework (25pts).

**DEC-16 — Latency: measure E2E + per-component breakdown before any optimization.** asr_latency_ms, llm_latency_ms, tts_latency_ms on every result object. Measurement Gate: log template-only vs LLM-turn latency before optimizing.

**DEC-17 — LLM-as-judge: dev-time only, documented.** Evaluation report must state judge model name and that the submitted bot does not depend on it at inference time.

**DEC-19 — Track ownership: each file has exactly one owner.** pipeline.py owned by Track B, reviewed by Track A. B must not write pipeline.py until TASK-A13 merges to main.

**DEC-27 — Python 3.11, pip + venv, requirements.txt == pinning.** Append-only, alphabetical, union-on-conflict. No uv/poetry/conda.
</decisions>

<constraints>
## Key Constraints

- **CONSTRAINT-03:** requirements.txt == pinning, append-only, alphabetical. Never delete the other track's lines.
- **CONSTRAINT-04:** No secrets in code. All config from .env via python-dotenv. .env is gitignored. Violating this risks the Code Quality 20pt score.
- **CONSTRAINT-06:** models/schemas.py and */base.py are FROZEN after Wave 0. Cross-track contract.
- **CONSTRAINT-07:** LangGraph ≤7 nodes, one invoke() per turn, no interrupt(), no persistent checkpointer, no 5 subgraphs per category.
- **CONSTRAINT-08:** No RAG.
- **CONSTRAINT-09:** CPU laptop (Zenbook) is the live demo target. No GPU at demo time.
- **CONSTRAINT-10:** TTS/UI only after core is solid. (Order enforced by task dependencies.)
- **CONSTRAINT-11:** Dialogue core must run and test in text mode before voice I/O is added.
- **CONSTRAINT-12:** Node functions must be pure: (state) -> update dict. No self/global mutation.
- **CONSTRAINT-13:** pipeline.py cannot be written until TASK-A13 merges to main.
- **CONSTRAINT-20:** Evaluation must meet brief minimums: ≥2 scenarios/category (≥10 total), ≥3 exception scenarios, ≥1 automated metric, honest failure analysis, latency per turn.
- **CONSTRAINT-21:** Single-threaded per call. No module-level mutable state.

## Pending User Decisions (from INGEST-CONFLICTS.md)

- Warning 1: Confirm VinFast enum values in dialogue/values.py before Phase 3 eval runs (field names frozen; value sets provisional).
- Warning 2: Swap EnergyVAD → silero-vad in TASK-B21 (interface already compatible; required before demo).
</constraints>

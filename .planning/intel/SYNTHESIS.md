# SYNTHESIS.md — Intel Entry Point for gsd-roadmapper
# Generated: 2026-06-25
# Mode: new (net-new bootstrap)

---

## Documents Synthesized: 8

| Source | Type | Locked | Precedence |
|--------|------|--------|------------|
| BLUEPRINT.md | ADR | YES | 0 (highest) |
| TECHSTACK.md | ADR | YES | 1 |
| PLAN.md | PRD | no | 2 |
| TASKGRAPH.md | SPEC | no | 3 |
| WORKFLOW.md | DOC | no | 4 |
| docs/ARCHITECTURE.md | DOC | no | 5 |
| docs/PHASE_0_1_B_UPDATE.md | DOC | no | 6 |
| README.md | DOC | no | 7 |

Cycle detection: PASS — no cycles in cross-reference graph.
UNKNOWN-confidence-low docs: 0

---

## Decisions (27 total, 2 sources LOCKED)

Locked ADR decisions (from BLUEPRINT.md precedence 0 + TECHSTACK.md precedence 1):
  BLUEPRINT.md — 12 numbered decisions (D1..D12), all locked
  TECHSTACK.md — 14 architecture decisions, all locked

Synthesized decision entries: 27 (DEC-01 through DEC-27)

Key locked decisions:
  DEC-01  Thin LLM + Thick State Machine philosophy
  DEC-02  LangGraph StateGraph (5 nodes, 4 hard rules)
  DEC-03  PhoWhisper-CT2 default ASR + faster-whisper fallback
  DEC-04  Ollama + Qwen 7-8B LLM
  DEC-05  Piper local ONNX primary TTS, pluggable interface
  DEC-08  Vietnamese normalization per-field post-extraction (D2, D3)
  DEC-11  models/schemas.py + */base.py FROZEN after Wave 0 (TASK-003)
  DEC-12  READBACK_REQUIRED = {phone, owner_phone, order_phone, license_plate_vin}
  DEC-13  Emergency detection hybrid (LLM flag OR keyword OR sentiment==urgent)
  DEC-15  No RAG (G_2/G_4 static policy)
  DEC-19  Track A/B ownership split (all files single-owned)
  DEC-24  8 exception handlers, all deterministic (not LLM-memory)

Full detail: D:/Task4/AI-Callbot-Vinfast/.planning/intel/decisions.md

---

## Requirements (23 items extracted)

By wave and track:

Wave 0 (COMPLETE — both tracks):
  REQ-scaffold, REQ-schemas, REQ-interfaces

Wave 1 Track A (status: coordinate with A before Wave 2):
  REQ-llm-client, REQ-categories, REQ-nlu, REQ-langgraph-engine, REQ-post-call

Wave 1 Track B (COMPLETE):
  REQ-normalization, REQ-asr-wrapper, REQ-mic-vad, REQ-corpus, REQ-wer-audio

Wave 2 (PENDING):
  REQ-exceptions, REQ-eval-harness, REQ-tts-piper, REQ-pipeline-cli, REQ-gradio-ui

Wave 3 (PENDING):
  REQ-metrics-full, REQ-ablation, REQ-eval-report, REQ-signature-demo,
  REQ-architecture-doc, REQ-reproducibility, REQ-verify-gate3

Full detail: D:/Task4/AI-Callbot-Vinfast/.planning/intel/requirements.md

---

## Constraints (22 total)

Type breakdown:
  api-contract: 7 (schemas frozen, LangGraph rules, node purity, no circular imports, etc.)
  protocol: 8 (secrets, gitignore, requirements.txt, Wave 0 sequencing, PR cadence, etc.)
  nfr: 7 (Python 3.11, pip+venv, CPU target, no RAG, text-first, single-threaded, eval minimums)

Key hard constraints:
  CONSTRAINT-03  requirements.txt == pinning, append-only, alphabetical
  CONSTRAINT-06  models/schemas.py + */base.py FROZEN (cross-track contract)
  CONSTRAINT-07  LangGraph <=7 nodes, 1 invoke/turn, no interrupt(), no persistent checkpointer
  CONSTRAINT-08  No RAG
  CONSTRAINT-09  CPU laptop (Zenbook) is live demo target — no GPU dependency at demo time
  CONSTRAINT-10  TTS/UI only after core is solid
  CONSTRAINT-12  Node functions must be pure (state) -> update dict

Full detail: D:/Task4/AI-Callbot-Vinfast/.planning/intel/constraints.md

---

## Context Topics (9)

  Topic: Project Identity (team, scope, mission statement, grading rubric)
  Topic: Current Implementation Status (Wave 0+1 Track B complete; Track A coordinate)
  Topic: Five Call Categories (G_1..G_5 field lists, critical name differences)
  Topic: Eight Exception Strategies (deterministic, flag-driven)
  Topic: VAD Behavior for Numeric Identity Fields (pause tolerance)
  Topic: Team Coordination Rules (branching, standup, pipeline.py timing)
  Topic: Differentiator — Vietnamese Entity Normalization
  Topic: Signature Demo Scenario (two demo calls)
  Topic: Evaluation Philosophy (recall-tuning, ablation, failure analysis)

Full detail: D:/Task4/AI-Callbot-Vinfast/.planning/intel/context.md

---

## Conflicts Summary

Blockers: 0
Competing variants (WARNINGS): 2
Auto-resolved (INFO): 5

Full report: D:/Task4/AI-Callbot-Vinfast/.planning/INGEST-CONFLICTS.md

Warning 1: Allowed value sets in dialogue/values.py are PROVISIONAL (TODO in BLUEPRINT.md).
  Field names are frozen; enum values are not. Confirm before Phase 3 eval.

Warning 2: EnergyVAD used in Phase 1 implementation; silero-vad is locked tech stack target.
  Interface is already compatible; swap required before demo in TASK-B20/B21.

---

## Status

STATUS: READY — safe to route (0 blockers)
Note: 2 warnings require user decisions before Phase 3 (not blocking Wave 2 start).

---

## Intel Files Index

D:/Task4/AI-Callbot-Vinfast/.planning/intel/decisions.md    — 27 architectural decisions
D:/Task4/AI-Callbot-Vinfast/.planning/intel/requirements.md — 23 functional requirements
D:/Task4/AI-Callbot-Vinfast/.planning/intel/constraints.md  — 22 hard constraints
D:/Task4/AI-Callbot-Vinfast/.planning/intel/context.md      — 9 context topics
D:/Task4/AI-Callbot-Vinfast/.planning/INGEST-CONFLICTS.md   — conflict detection report

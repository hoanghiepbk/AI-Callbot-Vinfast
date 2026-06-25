# Project State — VinFast Callbot Track B

**Project:** VinFast Callbot — Track B (Senses & Voice)
**Last Activity:** 2026-06-25
**Current Phase:** 03 — integration-voice (planning in progress; Phase 02 work is pending)

---

## Phase Status

| Phase | Name | Status | Plans |
|-------|------|--------|-------|
| 01 | foundation-dialogue | Complete | (pre-GSD) |
| 02 | exception-voice-pipeline | In Progress | 0 |
| 03 | integration-voice | Planning | 0 |

**Current Focus:** Phase 02 — complete B20 (TTS Piper), B21 (pipeline + CLI), B22 (Gradio UI). Track A B20/B21 exception handlers and eval harness status unknown — confirm with Hiệp before writing pipeline.py.

---

## Performance Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Normalization tests | 17 passing | TASK-B10 complete |
| ASR wrapper | Complete | TASK-B11 complete |
| VAD / mic capture | Complete (EnergyVAD) | Silero-vad swap pending in B21 |
| Scenario corpus | Complete | G_1..G_5 + exceptions |
| WER audio fixtures | Complete | ≥5 wav+reference |
| TTS | Not started | B20 pending |
| Pipeline (voice) | Not started | B21 pending |
| Gradio UI | Not started | B22 pending |
| Exception handlers | Not started (Track A) | A20 status: check with Hiệp |
| Eval harness | Not started (Track A) | A21 status: check with Hiệp |

---

## Accumulated Context

### Decisions Made
- EnergyVAD used in Phase 1 as temporary implementation; silero-vad is the locked target (DEC-07). Interface already compatible — swap happens in TASK-B21 without changing callers.
- pipeline.py is Track B owned, Track A reviewed. Must not be written until TASK-A13 has merged to main. (TASK-A13 is listed as complete — confirm before writing pipeline.py.)
- TTS primary is Piper local ONNX (offline, reproducible). edge_tts may be used during signature demo video recording only; report must document this clearly.
- VinFast enum values in dialogue/values.py are PROVISIONAL (TODO in BLUEPRINT.md). Field names are frozen; value sets are not. Confirm before Phase 3 eval runs.

### Open Items / Blockers
1. **[ACTION REQUIRED]** Confirm with Hiệp: status of TASK-A20 (8 exception handlers) and TASK-A21 (eval harness + slot F1). Track B's TASK-B21 (pipeline) depends on A13 being merged; A20 is needed before TASK-B30 (demo video).
2. **[ACTION REQUIRED]** Confirm VinFast enum values in dialogue/values.py before Phase 3 eval runs (provisional values may affect eval accuracy scores).
3. **[WARNING]** EnergyVAD must be swapped for silero-vad in TASK-B21 before demo. Interface is already compatible (same VAD base.py).
4. **[NOTE]** docs/ARCHITECTURE.md has B-side sections complete. A-side sections (dialogue/exception/eval) are pending — TASK-S30 is Wave 3 PAIR work.

### Key Implementation Notes
- Branch convention: Track B uses `b/<task>` branches targeting main. Current branch is `phuong`.
- Wave 2 start condition: both tracks confirm readiness after Phase 01 review. Do not start B21 until A13 is confirmed merged.
- Measurement Gate is mandatory in B21: log template-only latency AND E2E latency before any size/model optimization.
- Gradio UI (B22) wraps pipeline.turn() only — no new logic inside the UI layer.
- Signature demo video (B30): may swap edge_tts for recording; must document in EVALUATION_REPORT.md that submitted version uses Piper local.

### Session Continuity
- GSD initialized: 2026-06-25
- Intel files synthesized from: BLUEPRINT.md, TECHSTACK.md, PLAN.md, TASKGRAPH.md, WORKFLOW.md, docs/ARCHITECTURE.md, docs/PHASE_0_1_B_UPDATE.md, README.md
- Conflict report: 0 blockers, 2 warnings (EnergyVAD swap, provisional enum values) — see .planning/INGEST-CONFLICTS.md
- Next step: `/gsd-plan-phase 3` to create the execution plan for Phase 03 (integration-voice), OR address Phase 02 pending work first.

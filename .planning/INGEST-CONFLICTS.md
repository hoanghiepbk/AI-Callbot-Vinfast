# Conflict Detection Report
# Mode: new (net-new bootstrap)
# Sources processed: 8 classification files
# Generated: 2026-06-25

---

## BLOCKERS (0)

No blockers detected.

No LOCKED-vs-LOCKED ADR contradictions found. BLUEPRINT.md (ADR, locked, precedence 0) and
TECHSTACK.md (ADR, locked, precedence 1) are fully consistent on all shared scope. No cycles
detected in the cross-reference graph (all refs are DAG: ADRs cite each other and PLAN/TASKGRAPH;
no back-edges found up to traversal depth checked).

No UNKNOWN-confidence-low documents present. All 8 classifications are high confidence.

---

## WARNINGS (2)

[WARNING] Competing variant on allowed value sets (DEC-20 / TASK-002)
  Found: BLUEPRINT.md §2 (locked ADR) defines vehicle_type, vehicle_usage_type, customer_type value
    sets as PROVISIONAL with an explicit TODO: "xac nhan theo danh muc case Salesforce/VinFast that
    truoc khi siet enum". Value sets are declared as subject to change.
  Found: TASKGRAPH.md (SPEC) TASK-002 acceptance criteria treats these value sets as fixed for
    the current implementation pass.
  Impact: Downstream consumers (gsd-roadmapper, eval harness) cannot rely on these enum values
    being stable. The Wave 0 freeze covers field NAMES (safe); the value sets are not frozen.
  Source references:
    BLUEPRINT.md §2 (values.py block with TODO comment)
    TASKGRAPH.md TASK-002 Specs block
  Resolution: Confirm value sets against real VinFast/Salesforce data before Phase 3 eval runs.
    Until confirmed, treat as str fields with soft validation only. No action required to unblock
    Wave 2 work — field names are frozen; only the enum tightening is deferred.

[WARNING] EnergyVAD (Phase 1 impl) vs silero-vad (locked tech stack)
  Found: TECHSTACK.md (locked ADR) specifies silero-vad as the VAD choice.
  Found: ARCHITECTURE.md (DOC) and PHASE_0_1_B_UPDATE.md (DOC) document that Phase 1 uses
    EnergyVAD (deterministic, import-safe) behind the same VAD interface, with silero-vad
    deferred to Phase 2 via the same public interface.
  Impact: The submitted bot for Phase 1 eval uses EnergyVAD, not silero-vad. This is a known,
    intentional temporary deviation — the interface is designed for swap-in (vad.py public API
    unchanged). If Phase 2 does not complete silero-vad, the submitted bot may not match the
    locked tech stack claim.
  Source references:
    TECHSTACK.md (tech stack table row "VAD")
    ARCHITECTURE.md ("EnergyVAD is the deterministic Phase 1 turn-cutter. SileroVAD currently
      keeps the same public interface so Phase 2 can replace the internals.")
    PHASE_0_1_B_UPDATE.md (B12 completion note)
  Resolution: TASK-B20/B21 must include upgrading vad.py internals to silero-vad before demo.
    The interface is already compatible. If time-constrained, EnergyVAD can be submitted with an
    honest note in the architecture doc that silero-vad is the target and the interface is ready.

---

## INFO (5)

[INFO] Auto-resolved: BLUEPRINT.md (ADR, locked) > TASKGRAPH.md (SPEC) on normalization trigger
  Note: BLUEPRINT.md §1 clarifies that garbled exception #5 does NOT trigger when VAD cuts mid-
    number (caller pausing). TASKGRAPH.md TASK-B10 acceptance criteria adds a "short-pause" test
    case consistent with this. The SPEC extends (does not contradict) the ADR. ADR definition is
    authoritative; SPEC acceptance criteria treated as supplementary.
  Sources: BLUEPRINT.md §1 "Garbled #5 vs ngat-nghi so dai"; TASKGRAPH.md TASK-B10 acceptance

[INFO] Auto-resolved: BLUEPRINT.md (ADR, locked) > ARCHITECTURE.md (DOC) on TTS primary
  Note: ARCHITECTURE.md trade-off table says "TTS primary: Piper local later" (slightly ambiguous
    "later"). BLUEPRINT.md and TECHSTACK.md both lock Piper as the primary TTS for reproducibility.
    ADR language is authoritative. The "later" in ARCHITECTURE.md refers to Phase 2 timing (B20),
    not a deferral of Piper as primary choice.
  Sources: TECHSTACK.md §4 "Primary = Piper (local)"; ARCHITECTURE.md trade-offs table

[INFO] Auto-resolved: BLUEPRINT.md (locked ADR, precedence 0) > PLAN.md (PRD, precedence 2)
  on response rendering
  Note: PLAN.md §3 Phase 2 mentions "TTS Piper -> bot noi tieng Viet; giu interface tts/base.py
    (swap edge-tts cho video sau)". BLUEPRINT.md §1A Part 1 defines the full response strategy
    (template-first, LLM only for high-variance turns). These are not contradictory but BLUEPRINT
    is the authoritative source for response generation behavior. PLAN.md describes the timeline
    of implementation; BLUEPRINT defines the behavioral contract.
  Sources: BLUEPRINT.md §1A Part 1; PLAN.md Phase 2 checklist

[INFO] Auto-resolved: BLUEPRINT.md (locked ADR) > WORKFLOW.md (DOC) on pipeline.py timing
  Note: WORKFLOW.md §4 says B must not write pipeline.py until TASK-A13 (engine) has merged to
    main. TASKGRAPH.md TASK-B21 dependency list confirms A13 is a prerequisite. Both sources
    agree; WORKFLOW.md elaborates the rule. No contradiction, just additional specificity in DOC
    layer. ADR-backed rule applied.
  Sources: WORKFLOW.md §4; TASKGRAPH.md TASK-B21 "Depends: A13, B11, B12, B20"

[INFO] Auto-resolved: TECHSTACK.md (ADR, locked, precedence 1) > README.md (DOC, precedence 7)
  on tech stack summary
  Note: README.md is a high-level orientation document with a tech stack summary. Where it
    simplifies or omits details (e.g., does not mention CT2 conversion step for PhoWhisper,
    does not detail the fallback ladder), TECHSTACK.md is the authoritative source. README.md
    is not contradictory — it is intentionally high-level. All detail-level decisions sourced
    from TECHSTACK.md ADR.
  Sources: README.md intro; TECHSTACK.md §3 full table

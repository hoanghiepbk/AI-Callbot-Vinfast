# context.md — Project Context Intel
# Synthesized from: WORKFLOW.md (DOC, precedence 4), ARCHITECTURE.md (DOC, precedence 5),
#                   PHASE_0_1_B_UPDATE.md (DOC, precedence 6), README.md (DOC, precedence 7)
# Also incorporating: BLUEPRINT.md, TECHSTACK.md, PLAN.md for cross-referencing
# Generated: 2026-06-25

---

## TOPIC: Project Identity

source: BLUEPRINT.md (PROJECT INFO), TECHSTACK.md, README.md
Project: VinFast Vietnamese Customer Service Voice Callbot
Context: VinSmart Future AI Internship Task 3 (2-person team, 2-week timeline)
Track B (this person): Phuong — "Giac quan & Giong" (Senses & Voice)
Track A (teammate): Hiep — "Bo nao" (Brain / Dialogue)

Nature: CLI + Gradio web demo. Realtime turn-based dialogue + post-call batch. Prototype/demo scope.
Primary language: Vietnamese (vi)
Target hardware: CPU laptop (Zenbook) for live demo; GPU PC for offline WER eval only.

Core mission statement: "We are not building a chatbot demo. We are building a customer service
system resilient to real Vietnamese callers and safe in emergencies, then proving it with real eval
— and honest about its weaknesses." Three pillars: ben (resilient) · an toan (safe) · do duoc
(measurable).

---

## TOPIC: Grading Rubric and Priority Mapping

source: TECHSTACK.md (§0), PLAN.md (§0, §1)

| Score category         | Weight | What graders look for                                  |
|------------------------|--------|--------------------------------------------------------|
| Pipeline Functionality | 30     | 5 categories end-to-end mic->ASR->LLM->JSON            |
| Dialogue Design+Exc    | 25     | Smooth conversation + 8 exception situations handled   |
| Evaluation Framework   | 25     | Rigor of eval design, not score values                 |
| Code Quality+Repro     | 20     | Clean code, pip install -r works on clean machine      |
| TTS Bonus              | +5     | Bot speaks Vietnamese                                  |

Implication: Dialogue+Exception (25) + Eval (25) = 50/100. This is nearly double Pipeline (30).
Investment priority: state management + evaluation >> ASR/TTS polish.

---

## TOPIC: Current Implementation Status

source: PHASE_0_1_B_UPDATE.md (primary), cross-referenced with TASKGRAPH.md

Track B (Phuong) — COMPLETE through Wave 1:
  Phase 0 / Wave 0:
    - docs/ARCHITECTURE.md B-side sections written
    - models/schemas.py plate/phone validation support (frozen contract)
    - Audio scaffolding import-safe: faster_whisper_asr.py, recorder.py, vad.py, playback.py
  Phase 1 / Wave 1:
    - B10: Vietnamese normalization (vietnamese_numbers.py) + 17 passing pytest tests
    - B11: ASR wrapper (faster_whisper_asr.py) with file-mode support
    - B12: Mic capture (recorder.py) + VAD (vad.py) — Phase 1 uses EnergyVAD
    - B13: Scenario corpus for G_1..G_5 + exception cases (JSON fixtures)
    - B14: Audio fixture support for WER evaluation

Track A (Hiep) — status unknown from B-side docs. Coordinate before starting Wave 2.

Remaining Track B work (Wave 2+):
  - B20: TTS Piper (PENDING)
  - B21: Pipeline integration + CLI (PENDING — requires A13 to merge first)
  - B22: Gradio UI (PENDING — requires B21)
  - B30: Signature demo + video (PENDING — requires B22, A20)
  - B contributions to S30/S31/S32 (PENDING)

---

## TOPIC: Five Call Categories

source: BLUEPRINT.md (§2), TECHSTACK.md (§8)

G_1 — Roadside Rescue (Cuu ho): Priority-ordered fields starting with location/condition/phone
  to get minimum dispatch info fast. Skips current_odo (priority 95) in emergency.
  Demonstrates: domain knowledge (rescue-first field ordering)

G_2 — Warranty/Repair (Bao hanh & Sua chua): Standard warranty slot collection.
  Uses owner_phone (not phone); vehicle_model (not vehicle_line).

G_3 — Orders (Don hang): Simplest category (4 fields). Uses order_phone.

G_4 — Motorcycle Warranty (Xe may bao hanh): Uses phone; vehicle_line (not vehicle_model).

G_5 — Remote Tech Support (Ho tro ky thuat tu xa): Uses phone; vehicle_line; current_odo optional.
  vehicle_condition_details includes software version.

Critical field name differences (wrong name = lost Pipeline points):
  phone vs owner_phone vs order_phone
  vehicle_model vs vehicle_line

---

## TOPIC: Eight Exception Strategies

source: BLUEPRINT.md (§9), TECHSTACK.md (§9), PLAN.md (Phase 2)

All exceptions are deterministic, flag-driven from NLU output — NOT held in LLM memory.
This is what makes the bot "gradeable and testable" (25pts).

#1 Missing: ask next EMPTY field by priority order; never re-ask CONFIRMED
#2 Correction: overwrite slot, acknowledge, continue without repeating confirmed fields
#3 Ambiguous: exactly 1 clarification question before routing; category=None from NLU
#4 Out-of-scope: polite apology + redirect or offer human transfer
#5 Garbled: parse_failed from validator -> readback + confirm before storing (not ASR confidence)
#6 Emergency: hybrid detect (LLM flag OR keyword OR sentiment==urgent) -> hotline immediately +
   skip priority>=90 fields + defer readback; faster to dispatch > perfect one field accuracy
#7 Stuck: failed_turns >= 2 with no slot progress -> offer human transfer
#8 Hangup: silence-timeout/disconnect/Ctrl-C -> finalize() -> null unconfirmed fields -> post-call

Design note: Emergency (#6) overrides Readback (D10). In life-safety situations, speed of
dispatch trumps field confirmation accuracy.

---

## TOPIC: VAD Behavior for Numeric Identity Fields

source: ARCHITECTURE.md, PHASE_0_1_B_UPDATE.md, BLUEPRINT.md (§1 "Garbled #5 vs ngat-nghi so dai")
  
Vietnamese callers often pause while reading phone numbers, plate numbers, or VINs aloud.
The VAD must NOT cut the utterance at a short internal pause (that would falsely trigger garbled #5).

Implementation:
  - Phase 1: EnergyVAD with extended silence timeout for READBACK_REQUIRED fields
  - Phase 2: SileroVAD behind same interface (no pipeline code change needed)
  - Mechanism: longer silence window when current slot is in READBACK_REQUIRED set

Garbled #5 triggers only when the value has been fully read (silence timeout elapsed) and the
validator parse FAILS. Not when the caller is mid-number.

---

## TOPIC: Team Coordination Rules

source: WORKFLOW.md, PLAN.md (§4.3)

Standup: 10 minutes every morning — each person states which files they will touch today.
Branching: Track A uses a/<task>, Track B uses b/<task>. One task per branch.
PR cadence: <=1 day open. Squash merge. Both tracks on green main by end of each day.
Shared file protocol: notify before touching another person's file.
Wave 0 is sequential (one PR per task, both pull after each merge).
Wave 1+ is parallel (each track in their own directories).
pipeline.py integration (Wave 2): B writes AFTER A13 merges; A reviews.

---

## TOPIC: Differentiator — Vietnamese Entity Normalization

source: TECHSTACK.md (§5), BLUEPRINT.md (D2, D3)

This is the team's key technical differentiator. Other teams test with "textbook" Vietnamese text.
This bot handles how Vietnamese callers actually speak:

Examples:
  "khong tam tam le nam hai ba bon" -> 0885234...
  "ba muoi a nam sau bay cham tam chin" -> 30A-567.89
  "nam van cay" / "nam muoi nghin cay so" -> odo 50000

The normalization module (vietnamese_numbers.py) handles: spoken digits, le/linh variants,
muoi/muoi variants, plate number assembly, VIN 17-char compaction, odo. Pure Python, no LLM dependency.
Unit-tested with >=15 cases (currently 17 passing).

API: normalize_field(name: str, raw: str) -> NormResult(value: str | None, parse_failed: bool)
Runs per-field AFTER LLM extraction (knows field type -> safe normalization).

---

## TOPIC: Signature Demo Scenario

source: PLAN.md (§5.1, §5.2)

Signature demo call (~90 seconds, shows multiple differentiators):
  Caller panics: "Xe toi tong dai phan cach tren cao toc Ha Noi-Hai Phong!"
  Bot: (a) detects emergency immediately -> (b) provides hotline first -> (c) collects minimum
  for dispatch (location, callback number), skips current_odo -> (d) caller misreads phone number
  then corrects -> bot updates WITHOUT re-asking -> (e) plate number read out-of-order ->
  bot confirms via readback -> (f) final JSON with emergency=yes, sentiment=urgent

Second demo: "calm voice" emergency (caller sounds normal but is in danger):
  "Anh oi xe em do giua duong khong no duoc, troi toi qua..."
  This proves emergency detection is NOT keyword matching but recall-tuned classification.

---

## TOPIC: Evaluation Philosophy

source: TECHSTACK.md (§6), PLAN.md (§5.3)

The eval framework is designed as a controlled experiment, not just a score report:

1. Emergency = cost-asymmetry problem: tune RECALL (missing a real emergency is worse than
   false alarm). Test with adversarial "calm voice" cases. Measure recall separately.

2. Ablation study: measures delta of each key decision:
   - With vs without state machine (LangGraph vs LLM-holds-state)
   - With vs without recall tuning
   - Qwen3 vs Vietnamese-tuned variant (A/B model doubles as ablation)
   - Laptop medium ASR vs GPU large ASR WER delta

3. Turn-level failure analysis: when a turn fails, document WHAT failed + WHY + remediation.
   Exposing failures = professional confidence, not a weakness.

---

## TOPIC: Architecture Doc Deliverable Status

source: ARCHITECTURE.md (current content), PHASE_0_1_B_UPDATE.md

docs/ARCHITECTURE.md currently contains B-side sections:
  - Pipeline Overview (both tracks)
  - ASR section (B-owned)
  - VAD and Mic Capture section (B-owned)
  - Normalization section (B-owned)
  - Pipeline Ownership (B-owned)
  - Trade-Offs table

Missing from ARCHITECTURE.md (A-side sections, TASK-S30 PAIR work):
  - Dialogue engine internals
  - LangGraph graph and node descriptions
  - Exception handling strategies
  - Evaluation framework design
  - Decision log (full 12 decisions from BLUEPRINT.md §0)

---

## TOPIC: Technical Risk Register

source: TECHSTACK.md (§11), PLAN.md (§7)

HIGH risks:
  - ASR+LLM CPU latency too high for live demo: mitigated by template-first (cuts ~1 LLM/turn),
    Ollama keep_alive, fallback ladder (measure first at Measurement Gate, don't pre-optimize)
  - Re-asking confirmed fields: already solved by LangGraph state machine architecture

MEDIUM risks:
  - LLM returns invalid JSON schema: Pydantic validate + 1 retry + JSON mode
  - TTS edge-tts fails offline: Piper local is primary (edge-tts only for video)
  - Secret leak on push: .env + .gitignore from day 1 + Gate 3 scan
  - Overinvesting in TTS/UI: enforced by task sequencing (core first)
  - Two tracks diverge on contract: locked contract + both pull immediately on change

LOW risks:
  - PhoWhisper CT2 conversion: pre-converted versions on HuggingFace; generic faster-whisper fallback

---

## TOPIC: Git Branch State

source: gitStatus context
Current branch: phuong
Recent commits show: stateful FakeDialogueEngine + contract freeze tests (CTR-02),
  editable install fix, setup.ps1/setup.sh skeleton, pinned contract-layer deps.
Main branch: main (use for PRs)

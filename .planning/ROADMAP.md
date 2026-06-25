# VinFast Callbot — Roadmap

**Project:** VinSmart Future AI Internship · Task 3
**Owner:** Phương (Track B — Senses & Voice)
**Teammate:** Hiệp (Track A — Brain / Dialogue)
**Granularity:** Standard (3 phases — derived from PLAN.md 4-phase structure with Phases 0+1 collapsed as complete)

---

## Phases

- [x] **Phase 1: foundation-dialogue** — Scaffold, frozen data contract, Vietnamese normalization, ASR/VAD/mic stack, scenario corpus, WER audio fixtures, LangGraph dialogue engine + NLU + post-call (both tracks complete)
- [ ] **Phase 2: exception-voice-pipeline** — 8 exception handlers (Track A), TTS Piper, full audio pipeline + CLI with latency measurement, Gradio UI (Track B)
- [ ] **Phase 3: integration-voice** — Full eval suite, ablation study, signature demo video, finalized Architecture Doc, reproducibility gate, Gate 3 verification

---

## Phase Details

### Phase 1: foundation-dialogue
**Goal**: Repo foundation is solid, cross-track data contract is frozen, Track B audio/normalization stack is fully tested in isolation, and Track A dialogue engine runs 5 categories end-to-end in text mode with correct JSON output.
**Status**: Complete
**Depends on**: (none)
**Requirements**: REQ-001, REQ-002, REQ-003, REQ-A10, REQ-A11, REQ-A12, REQ-A13, REQ-A14, REQ-B10, REQ-B11, REQ-B12, REQ-B13, REQ-B14
**Success Criteria** (what must be TRUE):
  1. `python -c "import callbot"` succeeds; `git status` shows no .venv/.env
  2. models/schemas.py and all */base.py are frozen and passing import/mypy checks; phone/plate/VIN validators return parse_failed correctly
  3. Vietnamese normalization converts spoken digits to phone/plate/VIN/odo with ≥15 passing pytest cases (currently 17)
  4. ASR wrapper transcribes a Vietnamese .wav file via from_file() and returns latency_ms
  5. Track A dialogue engine runs G_3 happy path 4 turns and returns correct FinalOutput with null unconfirmed fields on early finalize()
**Plans**: (pre-GSD — completed without formal plans)
**UI hint**: no

### Phase 2: exception-voice-pipeline
**Goal**: The bot speaks Vietnamese, handles all 8 exception situations, and runs a complete live turn (mic → ASR → dialogue engine → TTS audio) with per-component latency logged — ready for demo recording.
**Status**: In Progress
**Depends on**: Phase 01
**Requirements**: REQ-A20, REQ-A21, REQ-B20, REQ-B21, REQ-B22
**Success Criteria** (what must be TRUE):
  1. All 8 exception scenarios demo-able: correction updates without re-asking confirmed fields; emergency routes to hotline + skips low-priority fields; garbled phone triggers readback before storing; stuck after 2 turns offers human transfer
  2. A spoken Vietnamese sentence through Piper synthesize() returns playable audio bytes with latency_ms
  3. One live mic turn runs: mic capture → VAD cut → ASR transcript → engine.process() → TTS audio → playback, with asr/llm/tts latency breakdown printed (Measurement Gate logged before any optimization)
  4. `python -m callbot --text` accepts keyboard input and produces a dialogue response (text mode works for eval)
  5. Gradio UI opens in browser, spoken input produces visible transcript and live JSON state panel update
**Plans**: TBD
**UI hint**: yes

### Phase 3: integration-voice
**Goal**: The complete evaluation suite runs and produces honest metrics, the signature demo video is recorded and shows the team's key differentiators in one call, and the submission package is fully reproducible on a clean machine.
**Status**: Not Started
**Depends on**: Phase 02
**Requirements**: REQ-A30, REQ-A31, REQ-A32, REQ-B30, REQ-S30, REQ-S31, REQ-S32
**Success Criteria** (what must be TRUE):
  1. eval/run_eval.py produces: routing confusion matrix 5×5, slot F1 per field, emergency recall on adversarial set (calm-voice cases), WER via jiwer on ≥5 real .wav clips, latency p50/p95 breakdown ASR/LLM/TTS
  2. Ablation table shows numeric delta for: with/without state-machine, with/without recall tuning, Qwen3 vs Vietnamese-tuned, laptop medium vs GPU large WER
  3. Signature demo video demonstrates in one ~90-second call: emergency detection → hotline first, phone correction without re-ask, garbled plate readback, spoken number normalization, final JSON with emergency=yes and sentiment=urgent
  4. docs/EVALUATION_REPORT.md covers all metrics + failure analysis with root causes (not glossed over) + honest LLM-as-judge disclosure
  5. `pip install -r requirements.txt` on a clean machine succeeds; `python -m callbot --text` runs following README; `git grep` finds no hardcoded secrets; Gate 3 verify report passes all checklist items
**Plans**: TBD
**UI hint**: yes

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 01. foundation-dialogue | (pre-GSD) | Complete | 2026-06-25 (approx) |
| 02. exception-voice-pipeline | 0/? | In Progress | - |
| 03. integration-voice | 0/? | Not Started | - |

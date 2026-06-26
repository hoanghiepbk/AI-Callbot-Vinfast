# Architecture — VinFast Vietnamese Callbot

A fully local Vietnamese customer-service voice bot: **ASR → LLM-NLU → deterministic
dialogue engine → TTS**, with the dialogue brain built as a *thin LLM over a thick state
machine*. Every claim below maps to a file in `src/callbot/`.

---

## 1. System overview

```
  mic / audio ──▶ VAD ──▶ ASR ──────▶ DialogueEngine.process(text) ──▶ reply text ──▶ TTS ──▶ speaker
 (sounddevice)  (energy/  (faster-     (LangGraph turn loop)          │              (Piper)
                 silero)   whisper)                                   ▼
                                                       FinalOutput JSON  (on done / hangup)
```

- **Seam (frozen contract).** The only coupling between the *senses* (audio) and the
  *brain* (dialogue) is `DialogueEngine.process(user_text) -> TurnResult` and
  `finalize() -> FinalOutput` ([engine.py](../src/callbot/dialogue/engine.py),
  [schemas.py](../src/callbot/models/schemas.py)). The engine is **text-in / text-out** — it
  never sees audio — so dialogue logic is testable without a microphone (DEC-25, text-first).
- **One-turn pipeline.** [pipeline.py](../src/callbot/pipeline.py) (`CallbotPipeline.turn`)
  wires ASR → engine → TTS and times each stage (`asr/llm/tts/engine/total_latency_ms`). It is
  owned by Track B; the engine stays interface-agnostic.
- **Frozen interfaces.** `asr/base.py`, `tts/base.py`, `llm/base.py`,
  `normalization/base.py`, `models/schemas.py` are frozen after Wave 0 (DEC-11) so both tracks
  build in parallel against stable signatures.

| Stage | Implementation | Key file |
|---|---|---|
| Capture | `MicrophoneRecorder` (16 kHz mono float32) | `audio/recorder.py` |
| VAD | `EnergyVAD` (Phase 1) / `SileroVAD` slot | `audio/vad.py` |
| ASR | `FasterWhisperASR` (PhoWhisper CT2, lazy load) | `asr/faster_whisper_asr.py` |
| NLU | `nlu_node` → `NLUResult` (Ollama + Qwen3-8B) | `dialogue/extraction.py`, `llm/ollama_client.py` |
| Dialogue | LangGraph `StateGraph`, 7 pure nodes | `dialogue/graph.py`, `dialogue/engine.py` |
| Normalization | `VietnameseNormalizer.normalize_field` | `normalization/vietnamese_numbers.py` |
| Response | template-first, 2–3 variants | `dialogue/response.py` |
| Post-call | transcript → 1 LLM summary call | `dialogue/post_call.py` |
| TTS | `PiperTTS` (local ONNX), pluggable | `tts/piper_tts.py`, `tts/__init__.py` |

---

## 2. Core principle — "Thin LLM, Thick State Machine"

The LLM does **only** NLU/NLG; all slot state and control flow is deterministic
([extraction.py](../src/callbot/dialogue/extraction.py),
[graph.py](../src/callbot/dialogue/graph.py)). The LLM performs exactly four functions:
classify intent, extract fields, (future) phrase high-variance replies, and summarize
post-call. It never holds conversation state in prompt history — that is what breaks
re-ask / correction / hangup (DEC-01).

**LangGraph StateGraph** ([graph.py](../src/callbot/dialogue/graph.py)) — the turn loop is a
straight chain of **7 pure nodes** (`(state) -> update dict`, no self/global mutation):

```
START ▶ nlu ▶ apply_signals ▶ route ▶ slot_update ▶ next_field ▶ stuck_check ▶ respond ▶ END
```

Branching lives only inside `respond`, which reads flags the earlier nodes set — so the loop
is trivially liftable back to a plain Python loop if LangGraph is ever dropped.

**4 LangGraph rules** (DEC-02, BLUEPRINT §1A):
1. `CallState` *is* the graph state schema — single source of truth, no parallel state
   ([state.py](../src/callbot/dialogue/state.py)).
2. One turn = one `graph.invoke()`; never `interrupt()`.
3. No persistent checkpointer — the engine holds `CallState` in memory per call.
4. ONE parameterized slot-filling loop driven by `categories.py` — **not** 5 sub-graphs per
   category ([categories.py](../src/callbot/dialogue/categories.py)).

> Note: the BLUEPRINT planned a 5-node graph; the shipped implementation has 7 (adds
> `apply_signals` and `stuck_check`), still within the ≤7-node cap.

---

## 3. Design decisions (problem → choice → rationale)

Each maps to source; the full ledger is in
[.planning/intel/decisions.md](../.planning/intel/decisions.md) (DEC-01…27).

1. **Thin LLM, thick FSM** (DEC-01). *Problem:* LLM-in-the-loop state forgets/repeats fields.
   *Choice:* deterministic FSM owns state; LLM only NLU/NLG. *Why:* exceptions #1/#2/#8 become
   testable, stable logic. → `graph.py`.
2. **LangGraph runtime** (D12/DEC-02). *Problem:* need routing + a single state object.
   *Choice:* `StateGraph`, 7 pure nodes, one invoke/turn. *Why:* native routing, liftable to a
   plain loop. → `graph.py`, `engine.py`.
3. **`think=False` for structured calls** (A10). *Problem:* Qwen3 is a reasoning model; with
   `format=schema` + thinking it historically returned empty content on calm-emergency inputs.
   *Choice:* disable thinking on schema calls + retry-on-empty. *Why:* safety-critical JSON
   validity. → `llm/ollama_client.py`. (Ablation: on the current model the empty bug no longer
   reproduces; it is now defense-in-depth — see [eval_report.md](eval_report.md).)
4. **Canonical field-name glossary in the NLU prompt** (A30). *Problem:* the live LLM invented
   field names (`order_code`, `company`) and mis-slotted them, so the engine dropped them.
   *Choice:* teach the exact brief field names + per-category field pin. *Why:* biggest
   measured win — slot-F1 0.267 → 0.862 (ablation). → `dialogue/extraction.py`.
5. **Hybrid emergency detection** (DEC-13). *Problem:* missing a real emergency is far worse
   than a false alarm. *Choice:* fire on `signals.emergency` **OR** keyword backstop; sentiment
   `urgent` is a post-call cross-check only. *Why:* recall-tuned, defense-in-depth. →
   `graph.py` (`_keyword_emergency`), `post_call.py`.
6. **Template-first responses** (DEC-10). *Problem:* an LLM call per reply is slow. *Choice:*
   deterministic templates (2–3 variants) for field questions / readback / closings; LLM only
   for high-variance turns. *Why:* cuts ~one LLM call/turn — ablation shows ~2.3 s/turn saved.
   → `dialogue/response.py`.
7. **Per-field normalization, post-extraction** (D2/DEC-08). *Problem:* global number
   normalization corrupts names ("anh Nam" → "anh 5"). *Choice:* normalize per field after the
   field type is known. *Why:* protects free-text while parsing phone/plate/VIN/odo. →
   `normalization/vietnamese_numbers.py`.
8. **Garbled via `parse_failed`, not ASR confidence** (D3/DEC-08). *Choice:* the validator's
   `parse_failed` flag triggers exception #5, not a confidence score. *Why:* deterministic and
   reliable. → `models/schemas.py` (`validate_field`).
9. **Readback before confirm** (D10/DEC-12). *Choice:* `phone/owner_phone/order_phone/`
   `license_plate_vin` must be read back before `CONFIRMED`; denial keeps them `PENDING`.
   *Why:* catch a wrong identifier. Emergency defers readback. → `graph.py`, `schemas.py`
   (`READBACK_REQUIRED`).
10. **Latency measured, not guessed** (D11/DEC-16). *Choice:* p50/p95 per stage + E2E via a
    latency proxy; template-vs-LLM compared. *Why:* measure before optimizing. →
    `pipeline.py` (`_LatencyLLMProxy`), `eval/latency.py`.
11. **Local Piper TTS, pluggable** (DEC-05). *Choice:* Piper local ONNX primary; `edge`/`vix`
    swappable behind `tts/base.py`. *Why:* reproducibility (fully local stack) over voice
    polish. → `tts/__init__.py`.
12. **Eval-as-code, honest failure analysis** (DEC-22). *Choice:* golden scenarios + pluggable
    metric registry + ablation, run on the real engine. *Why:* prove the bot works and *why*. →
    `eval/` (see [eval_report.md](eval_report.md)).

Other locked decisions: PhoWhisper-CT2 ASR (D1/DEC-03), Ollama+Qwen3-8B (DEC-04),
sounddevice+numpy (DEC-06), silero/energy VAD (D? /DEC-07), Pydantic v2 structured output
(DEC-09), frozen contract (DEC-11), hangup two-paths (D4/DEC-14), no-RAG static policy
(DEC-15), LLM-as-judge cloud dev-time (D7/DEC-17), WER on real clips (D5/DEC-18), `.env`-only
secrets (DEC-26), Python 3.11 + pinned deps (DEC-27).

---

## 4. Exception handling (8, all deterministic)

Full table with mechanism + eval scenario: [exceptions.md](exceptions.md). Summary — every
decision is state-machine logic in `graph.py`, not prompt behaviour:

| # | Situation | Mechanism |
|---|---|---|
| #1 | Missing field / no re-ask | `next_missing_field` skips CONFIRMED/CORRECTED slots |
| #2 | Correction | `corrected_fields` → slot overwritten, marked `CORRECTED` |
| #3 | Ambiguous intent | `need_clarify` → one clarifying question, no guess |
| #4 | Out-of-scope | polite redirect at any point, collected state kept |
| #5 | Garbled value | `parse_failed` → slot `PENDING`, ask to repeat |
| #6 | Emergency | hybrid detect → hotline once, skip low-priority, defer readback |
| #7 | Stuck 2+ turns | `failed_turns >= 2` → offer human |
| #8 | Hangup | `signals.hangup` → goodbye + `finalize()` partial JSON |

---

## 5. Safety architecture (defense-in-depth)

Emergency recall is the highest-cost-asymmetry path (missing a real emergency ≫ a false
alarm), so it is protected by **overlapping, deterministic layers**:

1. **Real-time detection (live trigger).** `emergency = LLM flag OR keyword backstop`, sticky
   once true — `apply_signals` in [graph.py](../src/callbot/dialogue/graph.py). The keyword
   list lives in code + tests, not the prompt.
2. **Emergency overrides flow.** Skips fields with `priority >= 90`, **defers readback**, and
   speaks the hotline once ([categories.py](../src/callbot/dialogue/categories.py),
   `respond`). Collect-minimum-for-dispatch first.
3. **Post-call cross-check (not a live trigger).** `sentiment == "urgent"` with no in-call
   emergency raises `possible_missed_emergency` — an eval/log signal, never a retro-flip
   ([post_call.py](../src/callbot/dialogue/post_call.py)).
4. **Readback-deny safety.** A denied identifier readback is never auto-confirmed
   (`_is_denial`, R1).
5. **Never-raise finalize.** Both hangup paths converge on `finalize()`, emitting partial JSON
   with unconfirmed slots = `null` (D4).

The ablation ([eval_report.md](eval_report.md)) shows emergency recall stays 100% precisely
*because* of this redundancy — the LLM alone, the keyword backstop, and the retry layer each
cover the others.

---

## 6. Eval-as-code

Metrics are pluggable functions over golden scenarios run through the **real** engine
([eval/](../eval/)): routing accuracy + confusion, slot-filling F1, emergency
recall/precision (keyword vs calm), latency p50/p95, LLM-as-judge naturalness, and WER/CER on
real audio. An ablation study quantifies each design decision's contribution. Numbers,
methodology, and honest failure analysis: **[eval_report.md](eval_report.md)**.

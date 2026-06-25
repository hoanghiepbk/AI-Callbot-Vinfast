# Exception handling strategy (#1–#8)

How the dialogue engine handles each of the brief's 8 exception situations. The engine
is a "thin LLM, thick state machine": the LLM only does NLU (category + fields + signals);
every exception decision below is **deterministic** state-machine logic in pure LangGraph
nodes ([graph.py](../src/callbot/dialogue/graph.py)), so behaviour is testable and stable.
Each row lists the mechanism, where it lives, and the eval scenario that covers it.

| # | Situation | Mechanism (deterministic unless noted) | Where | Eval scenario |
|---|-----------|----------------------------------------|-------|---------------|
| **#1** | Missing field / don't re-ask a filled one | `next_missing_field` returns the lowest-priority **required & not-yet-CONFIRMED/CORRECTED** field; confirmed slots are never offered again | `next_field` node · `categories.next_missing_field` | `adv_missing_no_reask`, all happy paths |
| **#2** | Correction ("à nhầm, …") | NLU sets `corrected_fields`; the slot is overwritten and marked `CORRECTED`, no loop | `slot_update` node | `adv_correction_midcall` |
| **#3** | Ambiguous intent | No category locked and NLU can't pick one → `need_clarify` → one clarifying question (does not guess a category) | `route` + `respond` (`clarify`) | `adv_ambiguous_first_turn` |
| **#4** | Out-of-scope | `signals.out_of_scope` → polite redirect **at any point in the call** (category locked or not); collected state is kept so the caller can resume | `respond` (`redirect`) | `adv_oos_midcall` |
| **#5** | Garbled / unparseable value | `normalize_field` returns `parse_failed` → slot stays `PENDING`, bot asks the caller to repeat | `slot_update` → `garbled_repeat` | `adv_garbled_repeat` |
| **#6** | Emergency | Hybrid: `signals.emergency` **OR** keyword backstop (`_EMERGENCY_KEYWORDS`, in code+tested) → sticky `emergency`; skips fields with `priority >= 90`, **defers readback**, speaks hotline once | `apply_signals` + `respond` (`emergency_msg`) | `adv_calm_emergency` |
| **#7** | Stuck (no progress 2+ turns) | Any non-progress turn — garbled, denied readback, empty NLU, nothing extracted — sets `turn_failed`; `failed_turns >= 2` → offer a human. OOS/hangup are digressions, not failures | `slot_update` + `stuck_check` → `offer_human` | `adv_stuck_offer_human` |
| **#8** | Hangup mid-call | `signals.hangup` → goodbye + `done`; `finalize()` emits partial `FinalOutput`, unfilled fields = `null` | `respond` + `DialogueEngine.finalize` | `adv_hangup_midway` |

## Readback (D10) — safety sub-protocol on top of #5/#2

Readback-required fields (`phone`, `owner_phone`, `order_phone`, `license_plate_vin`) are
read back before being recorded. The caller's next turn is resolved deterministically:

- **affirmation / silence** → `CONFIRMED`
- **explicit denial** (`_is_denial`: "không đúng", "sai rồi", bare "không", …) → stays
  `PENDING`, re-asked — readback must be able to *catch* a wrong value, so when in doubt we
  do **not** confirm (R1)
- **new value (correction)** → updated and read back again

Emergency **defers** readback (speed over confirmation). Covered by `adv_readback_deny`.

## Why deterministic

All eight are state-machine logic, not prompt behaviour. That keeps emergency/hangup/stuck
predictable (no LLM flakiness on safety paths) and makes the whole turn loop liftable back
to a plain loop if LangGraph is dropped. The LLM is used only for the high-variance *wording*
of emergency / clarify / redirect replies (future enhancement; today those are templates).

Run `python -m eval.run_eval` to see every scenario pass (turn-level + final-output checks).

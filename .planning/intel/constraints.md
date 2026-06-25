# constraints.md — Hard Constraints Intel
# Synthesized from: BLUEPRINT.md (ADR, locked, precedence 0), TECHSTACK.md (ADR, locked, precedence 1)
# Supporting: TASKGRAPH.md (SPEC, precedence 3), WORKFLOW.md (DOC, precedence 4)
# Generated: 2026-06-25

---

## CONSTRAINT-01 — Python 3.11 Minimum
source: TECHSTACK.md, pyproject.toml
type: nfr
severity: HARD (locked ADR)

Python 3.11 is the minimum runtime. Specified in pyproject.toml requires-python=">=3.11".
No other language. Python 3.12+ occasionally lacks audio-library wheels — 3.11 is the tested baseline.

---

## CONSTRAINT-02 — pip + venv Only (No uv, poetry, conda)
source: TECHSTACK.md
type: nfr / reproducibility
severity: HARD (locked ADR)

Standard library pip and venv only. No uv, no poetry, no conda. Grader must be able to run
"pip install -r requirements.txt" exactly as documented in the brief, without installing any
additional package manager.

---

## CONSTRAINT-03 — requirements.txt: == Pinning, Append-Only, Alphabetical
source: TECHSTACK.md, PLAN.md (§4.2), TASKGRAPH.md (D12), WORKFLOW.md (§5)
type: protocol
severity: HARD (locked ADR + workflow rule)

All dependencies pinned with == (never >= or ~=). requirements.txt is append-only — neither
track deletes the other's lines. Conflict resolution is union (keep both lines). Lines must
remain in alphabetical order. Includes langgraph and langchain-core pinned == (D12).

---

## CONSTRAINT-04 — No Secrets in Code: .env Only
source: BLUEPRINT.md (§4), TECHSTACK.md, WORKFLOW.md (§8), TASKGRAPH.md (TASK-S31)
type: protocol / security
severity: HARD (locked ADR, affects Code Quality 20pts grade)

All secrets (OLLAMA_HOST, LLM_MODEL, ASR_MODEL, ASR_DEVICE, ASR_COMPUTE_TYPE, JUDGE_MODEL,
HF_TOKEN) loaded from .env via python-dotenv. .env is gitignored. Never hardcoded. Repo must
be scanned before submission (TASK-S32 Gate 3). Violating this risks the Code Quality 20pt score.

---

## CONSTRAINT-05 — .gitignore Must Block: .venv/, *.onnx, scenarios/audio/*.wav, .env, __pycache__/
source: TASKGRAPH.md (TASK-001), WORKFLOW.md (§8)
type: protocol
severity: HARD (locked ADR)

These paths must be blocked in .gitignore from TASK-001 (day 1). *.onnx model weights and
scenarios/audio/*.wav (heavy binary files) must never be committed. Use Git LFS or keep outside repo
for audio fixtures.

---

## CONSTRAINT-06 — models/schemas.py and */base.py Are FROZEN After Wave 0 (TASK-003)
source: BLUEPRINT.md (§2, §3), TECHSTACK.md, PLAN.md (§4.2), TASKGRAPH.md (TASK-003), WORKFLOW.md
type: api-contract
severity: HARD (locked ADR, cross-track contract)

After TASK-003 merges to main, models/schemas.py and all */base.py interface files (asr/base.py,
llm/base.py, tts/base.py, normalization/base.py, dialogue/engine.py) are frozen. No signature
changes without both tracks agreeing and both pulling immediately. Implementation files behind
interfaces may evolve freely. A signature change mid-project breaks parallelism and risks the
submission contract.

---

## CONSTRAINT-07 — LangGraph: <=7 Nodes, 1 invoke() Per Turn, No interrupt(), No Persistent Checkpointer
source: BLUEPRINT.md (§1A Part 2), TECHSTACK.md
type: api-contract
severity: HARD (locked ADR)

Four non-negotiable LangGraph rules:
1. CallState IS the StateGraph state schema — one source of truth (no parallel state dict).
2. One turn = one graph.invoke() call — no interrupt() usage.
3. No persistent checkpointer — engine holds CallState in-memory per call. MemorySaver is
   thread-per-call only if needed; no durable store.
4. One slot-filling loop parameterized by categories.py — NOT 5 subgraphs per category.
5. Graph total nodes <= 7 (current target: exactly 5 nodes).

---

## CONSTRAINT-08 — No RAG
source: BLUEPRINT.md, TECHSTACK.md (§10 DEC-6), PLAN.md (§8), ARCHITECTURE.md
type: nfr
severity: HARD (locked ADR, all sources agree)

No RAG (retrieval-augmented generation) for G_2/G_4 policy. Static warranty policy only. RAG
is explicitly rejected to focus time on the eval framework (25pts) and avoid retrieval-quality risk.

---

## CONSTRAINT-09 — CPU Laptop (Zenbook) Is the Live Demo Target
source: TECHSTACK.md (§3.1), BLUEPRINT.md (D8)
type: nfr / hardware
severity: HARD (locked ADR)

The live demo runs on a CPU laptop (Zenbook class). GPU PC is only for offline WER evaluation
(PhoWhisper-large) and optional premium TTS clip. All model size decisions (faster-whisper medium
int8, Qwen Q4) must be validated on CPU-only hardware. Never require a GPU for the submitted demo.

---

## CONSTRAINT-10 — TTS/UI Only After Core Is Solid
source: PLAN.md (§8 principle 1), BLUEPRINT.md
type: nfr / development discipline
severity: HARD (ADR-backed planning constraint)

TTS (Piper) and Gradio UI are implemented only after dialogue core (engine, exceptions, text-mode
eval) is working. TTS is 5 bonus points; a broken dialogue core is fatal. Order: Wave 0-1 core
-> Wave 2 exceptions -> then TTS + pipeline + UI.

---

## CONSTRAINT-11 — Text-First Development: Dialogue Core Must Work in Text Mode First
source: PLAN.md (§2 principle 3), BLUEPRINT.md (§3 "interface-agnostic")
type: protocol
severity: HARD (ADR-backed)

DialogueEngine.process(text) -> TurnResult is the interface between audio and dialogue. The engine
is interface-agnostic (no knowledge of mic/ASR/TTS internals). All dialogue testing runs in text
mode. Voice integration is canned in pipeline.py only after engine is stable.

---

## CONSTRAINT-12 — Node Functions Must Be Pure: (state) -> update dict
source: BLUEPRINT.md (§1A Part 2 node convention)
type: api-contract
severity: HARD (locked ADR)

LangGraph node functions are pure: take state, return partial update dict. No self-mutation,
no global state, no hidden state outside CallState. This makes them directly unit-testable by
calling them without the graph infrastructure.

---

## CONSTRAINT-13 — pipeline.py Owned by Track B; Cannot Be Written Until TASK-A13 Merged
source: PLAN.md (§4.1, §4.2), TASKGRAPH.md (§3), WORKFLOW.md (§4)
type: protocol
severity: HARD (workflow constraint)

pipeline.py is the integration seam (audio -> ASR -> engine -> TTS). Track B owns it; Track A
reviews it. Track B must not write pipeline.py until TASK-A13 (engine) has merged to main.
No other file in either track may commit to pipeline.py.

---

## CONSTRAINT-14 — Wave 0 Tasks Run Sequentially, Not in Parallel
source: WORKFLOW.md (§2), TASKGRAPH.md (Wave 0)
type: protocol
severity: HARD (workflow constraint)

TASK-001 -> TASK-002 -> TASK-003 must run sequentially because all three touch shared files
(schemas.py + */base.py). Parallelism begins only after TASK-003 merges to main and the
contract is frozen.

---

## CONSTRAINT-15 — No Subgraph per Category (One Parameterized Loop)
source: BLUEPRINT.md (§1A Part 2 rule 4), TECHSTACK.md
type: api-contract
severity: HARD (locked ADR)

All 5 categories (G_1..G_5) share the same slot-filling loop (extract -> update -> next-field
-> respond). The category is set on state.category; the node logic reads categories.py to know
which fields to ask. Creating a subgraph per category is an anti-pattern explicitly rejected.

---

## CONSTRAINT-16 — LLM-as-Judge Is Dev-Time Only and Must Be Documented
source: BLUEPRINT.md (D7), TASKGRAPH.md (D7), TECHSTACK.md
type: protocol
severity: HARD (locked ADR)

The LLM-as-judge evaluation tool runs only at development time. The judge model (strongest
available cloud model via .env JUDGE_MODEL) must not be a runtime dependency of the submitted
bot. Evaluation report must state: "Naturalness scored by <JUDGE_MODEL>, eval-only; submitted
version does not depend on this."

---

## CONSTRAINT-17 — Emergency Priority Over Readback
source: BLUEPRINT.md (§1, §9 exc #6), DEC-13
type: api-contract
severity: HARD (locked ADR; emergency beats D10)

In an emergency (#6), the bot skips low-priority fields (priority >= 90, e.g., current_odo) and
defers readback for identity fields. Providing the hotline and collecting minimum dispatch info
(location, callback number) takes priority over accuracy of one field in a life-safety scenario.
Readback for deferred fields proceeds after the emergency is handled.

---

## CONSTRAINT-18 — PR Cadence: Max 1 Day Open; Both Tracks End Day on Green main
source: WORKFLOW.md (§6), PLAN.md (§4.3)
type: protocol
severity: SOFT (team workflow rule; affects Code Quality 20pts indirectly)

PRs must not stay open more than one day. Both tracks merge >= 1 PR per day. Both tracks end
each day on a green main (pull, build/test pass). Long-lived branches cause large merge conflicts.

---

## CONSTRAINT-19 — Ollama Must Run Locally; keep_alive to Prevent Cold-Load
source: TECHSTACK.md, BLUEPRINT.md (§1A Part 3)
type: nfr / infrastructure
severity: HARD

Ollama must run locally (no cloud LLM API at inference time). keep_alive parameter must be set
to keep the model resident between turns and avoid cold-load latency per turn. Ollama server is a
prerequisite; scripts/setup.ps1 and setup.sh must include model pull step.

---

## CONSTRAINT-20 — Evaluation Minimum Requirements (Must Exceed Brief Minimums)
source: PLAN.md (§6 note), BLUEPRINT.md (§5 REQ-14 through REQ-17), TASKGRAPH.md
type: nfr
severity: HARD (explicit project plan commitment)

Brief minimums (must meet):
  - >=2 scenarios per category (>=10 total)
  - >=3 exception scenarios
  - >=1 automated metric
  - Honest failure case documentation
  - Latency reported per turn

Project plan exceeds these with: slot F1 + routing confusion matrix + WER + emergency recall
adversarial set + latency p50/p95 breakdown + LLM-as-judge + ablation study + failure analysis.

---

## CONSTRAINT-21 — Single-Threaded per Call; No Global Mutable State
source: BLUEPRINT.md (§architectural constraints), TECHSTACK.md
type: nfr
severity: HARD (locked ADR)

pipeline.turn() is synchronous and single-threaded per call. No module-level mutable state.
DialogueEngine holds CallState as an instance attribute only. reset() clears it for new calls.
Config loaded once at startup from .env.

---

## CONSTRAINT-22 — Circular Import Prevention
source: BLUEPRINT.md (§architectural constraints)
type: schema / api-contract
severity: HARD

Import hierarchy:
  models/schemas.py -> imports nothing from dialogue/
  dialogue/ -> imports from models/ and llm/ and normalization/ protocols only
  pipeline.py -> imports from dialogue/engine.py and asr/ + tts/ impls
Circular imports between layers are explicitly prohibited.

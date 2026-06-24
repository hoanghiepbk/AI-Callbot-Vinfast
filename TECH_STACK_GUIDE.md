# Tech Stack & Build Guide — Vietnamese Callbot (Task 3)

A recommended, opinionated tech stack for each phase, with a step-by-step path
through the project. Defaults target a **Windows 11 machine** and work CPU-only,
but run much better with an NVIDIA GPU (noted where it matters).

> **Philosophy** (matches the brief): favour *clear design + robust dialogue +
> honest evaluation* over a heavy production stack. Pick boring, well-documented
> tools so your time goes into conversation logic and edge cases.

---

## 0. Foundation (do this first)

| Concern | Recommendation | Why |
|---|---|---|
| Language | **Python 3.11** | Best ecosystem fit for ASR/LLM/TTS; 3.12+ can have wheel gaps for audio libs |
| Env manager | **`uv`** (or `venv` + `pip`) | `uv` is fast and reproducible; `venv` is fine if you prefer |
| Config / secrets | **`python-dotenv`** + `.env` | Brief requires no creds in code — keys/tokens via `.env` only |
| Data validation | **`pydantic` v2** | Typed field schemas per category = clean JSON output + validation |
| Logging | **`structlog`** or stdlib `logging` | You must report per-turn latency — structured logs make this trivial |

**Setup**

```bash
# in d:\Task4\AI-Callbot-Vinfast
uv venv  &&  .venv\Scripts\activate      # or: python -m venv .venv
uv pip install -r requirements.txt        # build this file as you go, pin versions
```

Create `.env` (and add it to `.gitignore`):

```
# .env — never commit
OLLAMA_HOST=http://localhost:11434
# any cloud TTS keys, etc.
```

---

## 1. Phase 1 — ASR (mandatory)

Capture live mic audio → Vietnamese transcript.

### Recommended stack

| Component | Pick | Alternative | Notes |
|---|---|---|---|
| Mic capture | **`sounddevice`** | `pyaudio` | `sounddevice` has cleaner numpy integration, fewer Windows build issues |
| Voice activity detection (VAD) | **`silero-vad`** | `webrtcvad` | Detects when the caller stops talking → defines a "turn". Critical for a callbot |
| ASR model | **PhoWhisper** (`vinai/PhoWhisper-medium`) | `faster-whisper` (Whisper large-v3) | PhoWhisper is fine-tuned on Vietnamese and is the strongest VI option |
| Inference runtime | **`faster-whisper`** (CTranslate2) | `transformers` | 4× faster, lower memory; runs CPU or GPU |

> **Choosing the ASR model:**
> - **Best Vietnamese accuracy:** PhoWhisper (VinAI). Use `-medium` as a balance,
>   `-large` if you have GPU headroom.
> - **Best speed / easiest:** `faster-whisper` with `large-v3` or `medium`. Multilingual,
>   set `language="vi"`. On CPU use `compute_type="int8"`; on GPU `float16`.
> - For a 2-week task, **`faster-whisper` (medium, int8)** is the pragmatic default.
>   Upgrade to PhoWhisper if WER on your test clips is poor.

### How to build it
1. Stream mic frames with `sounddevice` (16 kHz mono — what all these models expect).
2. Feed frames to **silero-vad**; accumulate audio until ~700 ms of trailing silence → end of turn.
3. Pass the buffered utterance to the ASR model → transcript string.
4. Measure and log `asr_latency_ms` here (start of speech-end → transcript ready).

**Smoke test:** speak a sentence, print the transcript. Build a tiny harness that can
also feed a `.wav` file instead of the mic — you'll need that for automated evaluation.

```bash
uv pip install sounddevice silero-vad faster-whisper numpy
```

---

## 2. Phase 2 — LLM dialogue (mandatory)

Process transcript → manage dialogue across 5 categories → emit response + extracted fields JSON.

### Recommended stack

| Component | Pick | Alternative | Notes |
|---|---|---|---|
| Local LLM runtime | **Ollama** | llama.cpp, vLLM | Ollama is the easiest local backend on Windows; vLLM is Linux/GPU-oriented |
| Model | **Qwen2.5-7B-Instruct** | `PhoGPT-4B`, `VinaLLaMA-7B` | Qwen2.5 has strong Vietnamese + reliable JSON / tool-calling |
| Structured output | **`pydantic` + Ollama JSON mode** | `instructor`, `outlines` | Forces the model to return your field schema, not freeform text |
| Dialogue state | **Hand-rolled state machine** | LangGraph | A small explicit FSM is easier to debug and grade than a framework |

> **Why not a framework (LangChain/LangGraph)?** For 5 well-defined slot-filling
> flows, an explicit state machine is more transparent, easier to test, and shows
> "clear design thinking" (what the brief rewards). Reach for LangGraph only if you
> find yourself reinventing it.

> **Model choice detail:**
> - **Qwen2.5-7B-Instruct** — best all-round: good Vietnamese, excellent at returning
>   structured JSON and following slot-filling instructions. **Default pick.**
> - **PhoGPT-4B-Chat** (VinAI) — Vietnamese-native, lighter; test its JSON reliability.
> - If CPU-only and slow, drop to **Qwen2.5-3B-Instruct** or a 4-bit quant (`qwen2.5:7b-instruct-q4_K_M`).

### Architecture: split "understanding" from "talking"

Run the LLM in **two roles** per turn (can be one or two calls):

1. **NLU / extraction** → returns structured JSON:
   - `category` (G_1…G_5, or `null` if ambiguous)
   - `extracted_fields` (only fields the user just provided/corrected)
   - `intent_signals` (e.g. `emergency`, `out_of_scope`, `correction`)
2. **Response generation** → given current state (which fields are still missing),
   produce the next natural Vietnamese question — asking only for missing fields.

Keep a **`DialogueState`** object: `category`, `fields` dict, `turn_count`,
`failed_turns`, history. The state machine — not the LLM — decides *what to ask next*;
the LLM decides *how to phrase it* and *what was understood*. This makes exception
handling deterministic and gradeable.

### Define your schemas (Pydantic)

One model per category, e.g.:

```python
class RoadsideRescue(BaseModel):           # G_1
    full_name: str | None = None
    phone: str | None = None
    vehicle_model: str | None = None
    license_plate_vin: str | None = None
    vehicle_type: str | None = None
    current_odo: str | None = None
    current_location: str | None = None
    city_name: str | None = None
    vehicle_condition: str | None = None
```

`None` = not yet collected → drives "ask only for the missing field".

### Post-call output
At end of call, run one summarization pass over the full transcript →
`short_summary`, `sentimental_analysis`, `emergency`. Assemble final JSON:

```json
{ "category": "G_1", "fields": { }, "post_call": { } }
```

```bash
# install Ollama from ollama.com, then:
ollama pull qwen2.5:7b-instruct
uv pip install ollama pydantic
```

---

## 3. Phase 3 — TTS (optional, +5 pts)

Text response → spoken Vietnamese.

### Recommended stack

| Pick | Type | Notes |
|---|---|---|
| **`edge-tts`** | Cloud (free, no key) | Microsoft neural Vietnamese voices (`vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`). Easiest, very natural. **Default for the bonus.** |
| `viXTTS` | Local | Vietnamese fine-tune of XTTS-v2; fully offline, voice cloning. Heavier, GPU-friendly |
| `gTTS` | Cloud | Trivial fallback, more robotic |

> For +5 pts with minimal effort, **`edge-tts`** is the best ROI. If "fully local /
> offline" is a value you want to demonstrate, use **viXTTS** instead and say so in
> the architecture doc.

Play audio with `sounddevice` or `playsound`. Measure `tts_latency_ms`.

```bash
uv pip install edge-tts
```

---

## 4. Orchestration — wiring the pipeline

```
mic → [sounddevice+VAD] → audio buffer
    → [faster-whisper]  → transcript        (asr_latency_ms)
    → [LLM: NLU]        → category + fields  (llm_latency_ms)
    → [state machine]   → next action
    → [LLM: response]   → reply text
    → [edge-tts]        → audio out          (tts_latency_ms)   [optional]
```

- Build **one `turn()` function** that takes audio in and returns `(reply_text, state, latencies)`.
- Provide a **text-only mode** (type instead of speak) — invaluable for fast iteration
  and required for automated tests. The same `turn()` logic should serve both.
- Wrap the whole loop in a CLI entry point (`python -m callbot.run`).

Suggested layout (adapt to Codex's skeleton):

```
callbot/
  audio/      mic capture, VAD, playback
  asr/        whisper wrapper
  llm/        ollama client, prompts, NLU + response
  dialogue/   state machine, category schemas, exception rules
  tts/        edge-tts wrapper
  pipeline.py orchestrates one turn
  run.py      CLI loop (voice + text modes)
eval/         test scenarios + scripts (see §6)
prompts/      system prompts per role (versioned, easy to tweak)
```

---

## 5. Exception handling (25 pts — design here deliberately)

Map each brief situation to a concrete mechanism. Put this table in your architecture doc:

| Situation | Mechanism |
|---|---|
| Missing field | State machine asks next `None` field only; never re-asks filled slots |
| Customer corrects info | NLU emits `correction` + new value → overwrite slot, acknowledge, continue |
| Ambiguous intent | If NLU `category=null`, ask **one** clarifying question before routing |
| Out-of-scope | NLU `out_of_scope` flag → polite redirect / offer human transfer |
| Garbled input | Low ASR confidence or unparseable phone/plate → read back & confirm before saving |
| Emergency | NLU `emergency=true` → immediately give rescue hotline, skip low-priority slots |
| Stuck (2+ failed turns) | `failed_turns >= 2` counter → offer human handoff |
| Hangs up mid-call | On interrupt/timeout, dump partial JSON; unfilled slots = `null` |

The key design move: **make these deterministic in the state machine**, using flags the
LLM extracts. Don't rely on the LLM to "remember" to do them — that's what makes a
gradeable, testable bot.

---

## 6. Evaluation framework (25 pts)

| Component | Pick | Notes |
|---|---|---|
| Test runner | **`pytest`** | Each scenario = a test; scripted transcripts via text-mode `turn()` |
| Scenario format | **YAML/JSON fixtures** | Turn-by-turn user inputs + expected category/fields/flags |
| Field accuracy | custom metric | Slot precision/recall vs. expected JSON (automated metric ✓) |
| ASR quality | **`jiwer`** (WER) | Run on recorded `.wav` clips with reference transcripts |
| Dialogue quality | **LLM-as-judge** | Score naturalness/correctness with a rubric prompt (use Qwen or a cloud model) |
| Latency | timing harness | Log per-turn `asr/llm/tts` ms; report p50/p95 |

**Meet the minimums explicitly:**
- ≥2 scenarios × 5 categories = **10+**
- ≥3 exception scenarios (pick from §5)
- ≥1 **automated** metric (field-extraction F1 and/or WER both qualify)
- Honest **failure cases** — log what the bot got wrong and *why*
- **Latency per turn** — table with breakdown by stage

```bash
uv pip install pytest jiwer pyyaml
```

---

## 7. Recommended stack — summary

| Phase | Default pick | Lighter / fallback |
|---|---|---|
| Mic + VAD | sounddevice + silero-vad | pyaudio + webrtcvad |
| ASR | faster-whisper (medium, int8) | PhoWhisper-medium for higher VI accuracy |
| LLM runtime | Ollama | llama.cpp |
| LLM model | Qwen2.5-7B-Instruct | Qwen2.5-3B / PhoGPT-4B |
| Structured output | Pydantic + JSON mode | instructor / outlines |
| Dialogue | hand-rolled state machine | LangGraph |
| TTS (+5) | edge-tts | viXTTS (local) / gTTS |
| Eval | pytest + jiwer + LLM-judge | — |

---

## 8. Suggested build order (maps to the brief's timeline)

1. **Days 1–3:** Foundation (§0) + ASR (§1). Get mic → transcript working, plus
   file-based transcription for tests. Draft the architecture doc skeleton.
2. **Days 4–7:** LLM dialogue (§2). Define Pydantic schemas, build the state machine,
   get all 5 categories slot-filling end to end in **text mode**. Emit final JSON.
3. **Days 8–10:** Exception handling (§5) + edge-case tests. Add TTS (§3) if time.
4. **Days 11–14:** Evaluation framework (§6): write scenarios, run metrics, measure
   latency, write the honest evaluation report. Reproducibility check
   (`requirements.txt` pinned, clean `README`, `.env` only).

> **First milestone to aim for:** a working **text-mode** single-category loop
> (e.g. G_1) end to end. Once that's solid, add categories, then swap in voice I/O.
> Text-first keeps iteration fast and decouples dialogue quality from audio bugs.

# VinFast Vietnamese Customer Service Callbot — Task 3

**VinSmart Future — AI Internship Program**

A Vietnamese-language customer-service voice callbot for the VinFast domain.
Pipeline: **Mic → ASR → LLM dialogue → structured JSON (+ optional TTS)**,
covering 5 inbound call categories with robust exception handling and a
rigorous, honest evaluation framework.

> What this is graded on (per brief): *clear design thinking, smooth conversation
> logic across all 5 categories, honest handling of edge cases and failures.*
> A bot that gracefully recovers and escalates correctly beats one that only
> works on the happy path.

---

## Approach (in one minute)

- **"Thin LLM, Thick State Machine".** The LLM only does NLU (intent + entity
  extraction), response phrasing, and post-call summarisation. A **deterministic
  state machine** owns all dialogue control — which field to ask next, what is
  already confirmed, when to escalate. This is what makes the bot reliable and
  testable, and is the key to passing the hardest exceptions (no re-ask, update
  on correction, partial JSON on hang-up).
- **Fully local & reproducible.** Local ASR (faster-whisper), local LLM (Ollama),
  local TTS (Piper). No cloud dependency → runs on a clean machine, offline.
- **Spoken-Vietnamese entity normalization.** A dedicated layer converts
  spoken numbers / phone / license plate / VIN into structured values — so the
  bot survives how Vietnamese callers actually speak.
- **Evaluation as a first-class deliverable.** Routing confusion matrix, slot F1,
  emergency recall on adversarial cases, WER, latency p50/p95, and honest failure
  analysis.

---

## Pipeline

| Phase | Status | Description |
|---|---|---|
| **Phase 1 — ASR** | Mandatory | Live microphone input → Vietnamese transcript |
| **Phase 2 — LLM** | Mandatory | Process transcript, manage dialogue, generate response (local LLM) |
| **Phase 3 — TTS** | Optional (+5 pts) | Text response → spoken Vietnamese. If absent, the bot responds in text only |

---

## Domain & Categories

The bot identifies the correct category and collects all required fields through
natural conversation.

| Cat | Name | Required fields |
|---|---|---|
| **G_1** | Cứu hộ (Roadside Rescue) | `full_name`, `phone`, `vehicle_model`, `license_plate_vin`, `vehicle_type`, `current_odo`, `current_location`, `city_name`, `vehicle_condition` |
| **G_2** | Bảo hành & Sửa chữa (Warranty & Repair) | `full_name`, `owner_phone`, `vehicle_model`, `vehicle_usage_type`, `license_plate_vin`, `service_center`, `vehicle_condition` |
| **G_3** | Đơn hàng (Order Status & Management) | `full_name`, `order_phone`, `order_code_dealer`, `customer_type` |
| **G_4** | Xe máy – Bảo hành (Motorbike Warranty) | `full_name`, `phone`, `vehicle_line`, `license_plate_vin`, `current_location`, `vehicle_condition` |
| **G_5** | Hỗ trợ kỹ thuật từ xa (Remote Tech Support) | `full_name`, `phone`, `license_plate_vin`, `vehicle_line`, `current_odo` (optional), `vehicle_condition_details` (incl. software version) |

**Post-call output** (generated from the full transcript at the end of every call):

```json
{
  "category": "G_1",
  "fields": { },
  "post_call": {
    "short_summary": "...",
    "sentimental_analysis": "urgent",
    "emergency": "yes"
  }
}
```

---

## Exception Handling

All 8 situations are handled deterministically in the state machine, driven by
flags the LLM extracts:

| Situation | Behaviour |
|---|---|
| Missing field | Ask only for the missing field — never re-ask confirmed info |
| Customer corrects info | Acknowledge, update the value, continue without repeating |
| Ambiguous intent | Ask one clarifying question before routing |
| Out-of-scope query | Acknowledge politely, redirect or offer human transfer |
| Unclear / garbled input | Read back and confirm before recording |
| Emergency detected | Prioritise immediately — provide rescue hotline, skip low-priority fields |
| Stuck after 2+ failed turns | Offer to transfer to a human agent |
| Customer hangs up mid-call | Output partial JSON; unfilled fields = `null` |

---

## Evaluation (minimum coverage, exceeded)

- All 5 categories — ≥ 2 scenarios each (≥ 10 total)
- ≥ 3 exception-handling scenarios
- ≥ 1 automated metric (slot-extraction F1, WER)
- Honest failure analysis — what the bot got wrong and why
- End-to-end latency per turn (p50 / p95, broken down by ASR / LLM / TTS)

---

## Planning & Design Documents

| Doc | Purpose |
|---|---|
| [TECHSTACK.md](TECHSTACK.md) | Tech-stack choices and the rationale behind each |
| [PLAN.md](PLAN.md) | Execution plan, 2-person split, git/code-push strategy |
| [BLUEPRINT.md](BLUEPRINT.md) | Detailed design: turn loop, data contract, interfaces |
| [TASKGRAPH.md](TASKGRAPH.md) | Dependency-mapped task breakdown by track |

---

## Project Structure

```
src/callbot/
  main.py            # CLI entry (voice + text mode)
  pipeline.py        # one turn: audio → ASR → engine → TTS, with latency timers
  config.py          # .env loading
  audio/             # mic capture, VAD, playback
  asr/               # faster-whisper wrapper (interface + impl)
  llm/               # Ollama client, versioned prompts
  dialogue/          # engine (LangGraph), graph, nodes, state, categories, values, intent, extraction,
                     # exceptions, response, post_call
  normalization/     # spoken-Vietnamese number/plate/VIN normalization
  models/            # Pydantic schemas (data contract)
  tts/               # Piper (interface + pluggable impls)
  utils/             # logging, latency
scenarios/           # evaluation fixtures (turn-by-turn) + audio clips
tests/               # pytest unit/exception tests
eval/                # eval runner + metrics + ablation + WER (results committed)
docs/                # ARCHITECTURE.md, eval_report.md, exceptions.md
```

---

## Tech Stack (summary)

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| VAD | silero-vad |
| ASR | PhoWhisper-medium (CT2/faster-whisper) default; generic faster-whisper fallback |
| LLM runtime | Ollama |
| LLM model | Qwen-class 7–8B (+ A/B against a Vietnamese-tuned model) |
| Structured output | Pydantic v2 + JSON mode |
| Dialogue | LangGraph StateGraph (deterministic state machine) |
| TTS (+5) | Piper (local); pluggable interface |
| Frontend | CLI (dev/eval) + Gradio (demo) |
| Eval | pytest + jiwer (WER) + LLM-as-judge |

See [TECHSTACK.md](TECHSTACK.md) for full rationale and trade-offs.

---

## Setup

**Target runtime: Python 3.11** (per TECHSTACK §3 — newer versions may lack audio/ML wheels).

```bash
python -m venv .venv
.venv\Scripts\activate                 # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"                # callbot + pinned runtime + eval/dev tools (jiwer, pytest…)
# pip install -e .                      # runtime only (no eval/dev tooling)
# pip install -e ".[asr,ui]"           # ASR conversion deps + Gradio demo (for voice/UI)
cp .env.example .env                    # configure OLLAMA_HOST, model names, etc.
```

All dependencies are pinned with `==` in [pyproject.toml](pyproject.toml). Verified from a
clean Python 3.11 venv: `pip install -e ".[dev]"` exits 0 and `python -m eval.run_eval`
prints metrics (see [docs/eval_report.md](docs/eval_report.md)).

### Setup ASR (required for voice mode)

PhoWhisper is the best Vietnamese Whisper model, but ships as a transformers checkpoint —
faster-whisper needs CTranslate2. Convert it once:

```bash
pip install -e ".[asr]"        # transformers + ctranslate2
python scripts/setup_asr.py    # builds models/phowhisper-medium-ct2 (int8); set HF_TOKEN if gated
```

`FasterWhisperASR` then auto-detects `models/phowhisper-medium-ct2`. Without this step, voice
mode raises a clear error pointing back here. (Text mode + eval do not need ASR.) The converted
weights are git-ignored. To skip PhoWhisper, set `ASR_MODEL=medium` (generic faster-whisper).

> Audio for `pipeline.turn(audio=…)` must be **16 kHz mono** (live mic capture already is;
> `from_file()` handles other rates, so WER on 48 kHz clips works).

### System / external dependencies (not pip)

- **Ollama** — install separately and pull the model: `ollama pull qwen3:8b` (LLM runtime).
- **PortAudio** — needed by `sounddevice` for mic I/O. Linux: `apt install libportaudio2`;
  macOS: `brew install portaudio`; Windows: bundled with the wheel.
- **torch** — pulled in by `silero-vad` (large download, CPU build is fine).

No credentials in code — API keys / tokens via `.env` only.

---

## Run

```bash
python -m callbot.main --text                 # text dialogue (type caller utterances)
python -m callbot.main --voice                # voice dialogue (mic in, TTS out)
python -m callbot.main --gradio               # Gradio web demo
```

Text mode needs only Ollama running. Voice mode additionally needs a microphone, ASR
weights, and a TTS engine (`TTS_ENGINE=none` for text-only output).

## Eval

```bash
python -m eval.run_eval                        # scripted: routing, slot-F1, emergency (no Ollama)
python -m eval.run_eval --ollama               # real LLM extraction + real per-stage latency
python -m eval.ablation                        # ablation study (real Ollama)
python -m eval.run_wer                          # WER/CER on the audio set (needs jiwer + ASR_MODEL)
```

Scripted eval is deterministic and needs no Ollama. Results land in `eval/results.json`
(+ committed `eval/results_snapshot.json`, `eval/ablation_results.json`,
`eval/wer_results.json`). Full numbers + methodology: [docs/eval_report.md](docs/eval_report.md).

### Audio / WER (B14)

Raw `*.wav` recordings are **not** committed (real voices + size). The reference transcripts
(`scenarios/audio/manifest.json`), per-clip results (`eval/wer_results.json`) and the runner
(`eval/run_wer.py`) are committed so WER/CER stays verifiable. To reproduce on your own audio,
see [scenarios/audio/README.md](scenarios/audio/README.md).

---

## Status

Dialogue core, exception handling, evaluation suite (eval + ablation + WER) implemented and
green on the lean CI gate. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/eval_report.md](docs/eval_report.md).

# Module Reference — VinFast Callbot

A per-file technical reference for `src/callbot/` (+ `scripts/`). For the *why* (design
decisions, data flow), see [ARCHITECTURE.md](ARCHITECTURE.md); for setup/run, the
[README](../README.md). Frozen-contract files are marked 🔒 — their signatures may not change
without both tracks agreeing (WORKFLOW §5).

Legend: **Track B** = senses & voice (audio/asr/tts/normalization/pipeline/main). **Track A** =
dialogue brain (dialogue/llm/eval). **Shared** = the frozen contract.

---

## Top level

| Module | Purpose | Key API |
|---|---|---|
| `main.py` | CLI entry. `--text` keyboard loop, `--voice` real-time mic loop (bot greets first), `--gradio` web demo. | `main(argv)`, `run_text_mode`, `run_voice_mode`, `build_parser` |
| `pipeline.py` | One turn: audio→ASR→engine→TTS with per-stage latency. Builds deps from `.env`. Short-circuits empty ASR. | `CallbotPipeline.from_env()`, `.turn(audio=…/text=…)` → `PipelineTurnResult`, `.finalize()`, `.reset()` |
| `gradio_app.py` | 2-tab web demo (📞 real-time call · 🎙️ intercom). Live transcript, slot/final JSON, latency panel; error-resilient handlers. | `create_demo(pipeline?)` → `GradioDemo` |
| `voice_call.py` | Server-side **half-duplex** streaming-call state for the Gradio call tab. Mutes mic during bot playback. | `VoiceCallSession(pipeline)`: `.greet()`, `.feed(samples, sr)` → result\|None, `.reset()` |
| `config.py` | Loads `.env` into `os.environ` (stdlib only) and exposes typed constants. | `OLLAMA_HOST`, `LLM_MODEL`, `ASR_ENGINE`, `ASR_MODEL`, `ASR_BEAM_SIZE`, `MIC_GAIN`, `GROQ_*`, `TTS_ENGINE`, `EDGE_VOICE`, `PIPER_*` |
| `__main__.py` | `python -m callbot` → `main()`. | — |

`PipelineTurnResult` fields: `user_text`, `reply_text`, `done`, `state` (dict), `final_output`,
`reply_audio`(+`_sample_rate`), and `asr/llm/tts/engine/total_latency_ms`, `filler_text`.

---

## `audio/` — capture, VAD, playback (Track B)

| Module | Purpose | Key API |
|---|---|---|
| `recorder.py` | `sounddevice` fixed-window capture, 16 kHz mono float32. | `MicrophoneRecorder.record_seconds(s)`, `RecorderConfig` |
| `stream.py` | **Real-time** capture + endpointing. `VadEndpointer` is a frame-by-frame energy-VAD state machine (consecutive-frame onset, pre-roll ring buffer, read-back-aware silence, optional `adaptive` noise-floor calibration). `StreamingMicrophone` pulls frames off a live stream and applies `MIC_GAIN`. | `StreamingMicrophone.listen_utterance(field_name?, max_wait_seconds, max_utterance_seconds)`, `VadEndpointer.push_frame(frame)` / `.flush()` |
| `vad.py` | Batch energy VAD (trims one buffer); `silence_ms` widened for read-back numeric fields. | `EnergyVAD.trim_utterance(audio, field_name?)`, `VADConfig`, `SileroVAD` (fallback shim) |
| `playback.py` | WAV encode/decode + speaker output. | `play_wav_bytes(b)`, `decode_wav_bytes(b)` → `(sr, samples)` |

---

## `asr/` — speech-to-text (🔒 base; Track B)

| Module | Purpose | Key API |
|---|---|---|
| `base.py` 🔒 | `ASR` Protocol + result. | `ASR.transcribe(audio, sample_rate)` / `from_file(path)` → `ASRResult(text, confidence?, latency_ms)` |
| `__init__.py` | **Factory** selecting backend by `ASR_ENGINE` (lazy imports). | `create_asr(engine?)` → `ASR` |
| `faster_whisper_asr.py` | Local PhoWhisper-CT2 / faster-whisper (default, canonical). Lazy model load; auto-detects the CT2 export; `vad_filter`+`condition_on_previous_text=False` (anti-hallucination); CUDA DLLs on PATH for GPU; `ASR_BEAM_SIZE`. | `FasterWhisperASR(...)` |
| `groq_asr.py` | Cloud `whisper-large-v3` (OpenAI-compatible, opt-in, non-canonical). Encodes the buffer to WAV, POSTs via `httpx`. Needs `GROQ_API_KEY`. | `GroqASR(...)` |

---

## `dialogue/` — the brain (Track A)

| Module | Purpose | Key API |
|---|---|---|
| `engine.py` 🔒 | Public seam between tracks; wraps the graph, holds `CallState` in memory, memoizes `finalize()`. | `DialogueEngine(llm, normalizer)`: `.process(text)` → `TurnResult(reply, done, state)`, `.finalize()` → `FinalOutput`, `.reset()` |
| `graph.py` | LangGraph `StateGraph`: 7 pure nodes `nlu→apply_signals→route→slot_update→next_field→stuck_check→respond`. Hosts the deterministic backstops: emergency keywords, **category keyword backstop** (`_keyword_category`), **answer-binding** + non-answer/hesitation guards, readback/denial logic. | `build_graph(llm, normalizer)` → compiled app |
| `state.py` 🔒 | `CallState` = the StateGraph schema. Persistent fields (category, slots, emergency, failed_turns, transcript, pending_field, `last_asked_field`…) + transient per-turn fields. | `CallState` |
| `categories.py` | Per-category field specs `(name, priority, required)` + next-field policy (emergency skips priority ≥ 90). | `fields_for(cat)`, `next_missing_field(cat, filled, emergency)`, `requires_readback(field)` |
| `extraction.py` | NLU node: one utterance → `NLUResult` via the LLM. Tuned prompt (canonical field glossary, per-category pin, balanced few-shot). Never raises — bad output → empty result. | `nlu_node(llm, text, current_category?)`, `build_system(cat?)` |
| `response.py` | Template-first replies (2–3 rotated variants): field questions, readback, format-aware garbled re-ask, clarify, redirect, emergency, offer-human, closings, fillers. | `ask_field`, `readback`, `garbled_repeat`, `clarify`, `emergency_msg`, `offer_human`, `closing_*`, `filler` |
| `post_call.py` | One LLM call over the transcript → `PostCall(short_summary, sentimental_analysis, emergency)`. | `generate_post_call(llm, transcript, state)` |
| `fake_engine.py` | Stateful fake `DialogueEngine` for tests/UI without a real LLM. | `FakeDialogueEngine(llm, normalizer)` |

---

## `llm/` — local LLM (🔒 base; Track A)

| Module | Purpose | Key API |
|---|---|---|
| `base.py` 🔒 | `LLM` Protocol + result. | `LLM.complete(system, user, json_schema?)` → `LLMResult(text, latency_ms)` |
| `ollama_client.py` | Ollama wrapper (Qwen3-8B). Structured calls force `format=schema`, `think=False`, `temperature=0`, retry-on-empty (≤2); never raises (empty → safe default). `OLLAMA_KEEP_ALIVE` keeps the model resident. | `OllamaClient(host?, model?)` |
| `prompts.py` | Versioned prompt strings (NLU / response / post-call). | prompt constants |

---

## `normalization/` — spoken Vietnamese → values (🔒 base; Track B, the differentiator)

| Module | Purpose | Key API |
|---|---|---|
| `base.py` 🔒 | `Normalizer` Protocol. | `normalize_field(name, raw)` → `NormResult(value, parse_failed)` |
| `vietnamese_numbers.py` | Pure-Python: spoken digits → number ("không tám tám" → `088…`), "lẻ/linh", "mươi/mười", plate assembly, VIN, odometer ("năm vạn" → `50000`). Per-field, post-extraction; `parse_failed=True` triggers garbled #5. | `VietnameseNormalizer.normalize_field(name, raw)` |

---

## `tts/` — text-to-speech (🔒 base; Track B)

| Module | Purpose | Key API |
|---|---|---|
| `base.py` 🔒 | `TTS` Protocol + result. | `TTS.synthesize(text)` → `TTSResult(audio, latency_ms)` |
| `__init__.py` | **Factory** by `TTS_ENGINE` (`none`→`None`). | `create_tts(engine?)` |
| `piper_tts.py` | Local Piper ONNX (default, instant). Digit-run expansion so phone/VIN read out; no voice → silence + warning (never a beep). | `PiperTTS(voice_path?)` |
| `edge_tts.py` | Microsoft Edge neural voice (cloud, natural; `vi-VN-HoaiMyNeural`). MP3→WAV via PyAV; offline → silence + warning. | `EdgeTTS(voice?)` |
| `vixtts.py` | Stub extension point (GPU XTTS) — raises if selected. | `ViXTTS` |

---

## `models/` — data contract (🔒 Shared)

`schemas.py` 🔒 — every inter-module type. `SlotStatus` (empty/pending/confirmed/corrected),
`Slot`, `IntentSignals`, `Category` (`Literal["G_1"…"G_5"]`), `NLUResult`, `NormResult`,
`PostCall`, `FinalOutput` (unfilled fields → `null`). `READBACK_REQUIRED` set + `validate_field`
(phone = exactly 10 digits, VIN = 17 chars, VN plate regex; failure → `parse_failed` → #5).

---

## `utils/`

| Module | Purpose |
|---|---|
| `latency.py` | Per-turn timer helpers (asr/llm/tts/E2E ms). |
| `logging.py` | Structured logging setup. |

---

## `scripts/`

| Script | Purpose |
|---|---|
| `setup_asr.py` | Convert PhoWhisper-medium → CTranslate2 int8 into `models/phowhisper-medium-ct2/`. |
| `setup_tts.py` | Download the Vietnamese female Piper voice into `models/piper/`. |
| `mic_check.py` | Mic diagnostic — lists input devices, measures level vs the VAD threshold, verdicts SILENT/TOO-QUIET/OK (tune `MIC_GAIN`). |
| `measure_latency.py` / `measure_emergency.py` / `measure_nlu.py` | Measurement-gate spikes (latency, emergency recall, NLU). |

---

## Data flow (one turn)

```
audio ─▶ pipeline.turn ─▶ create_asr().transcribe ─▶ text
                              (empty? short-circuit, re-listen)
text ─▶ engine.process ─▶ graph.invoke:
        nlu (LLM) ─▶ apply_signals ─▶ route ─▶ slot_update ─▶ next_field ─▶ stuck_check ─▶ respond
        │ backstops: emergency kw · category kw · answer-binding · readback · #7 stuck
        └▶ per-field normalize (parse_failed → garbled #5)
reply ─▶ create_tts().synthesize ─▶ audio ─▶ playback
on done/hangup ─▶ engine.finalize ─▶ FinalOutput JSON (+ post-call LLM)
```

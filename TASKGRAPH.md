# TASK GRAPH: VinFast Callbot

> Cắt [BLUEPRINT.md](BLUEPRINT.md) thành 22 task, dependency-mapped, chia **Track A (Hiệp)** / **Track B (Phương)**.
> Quy ước: `[PAIR]` = hai người cùng làm/merge trước · `[A]` Track A · `[B]` Track B.
> Luật push code không đụng nhau: [PLAN.md §4.1–4.3](PLAN.md).

---

## 1. Dependency Graph

```
            ┌──────────────────── WAVE 0 — CONTRACT FREEZE [PAIR] ────────────────────┐
            │   TASK-001 scaffold ──► TASK-002 schemas ──► TASK-003 interfaces            │
            └───────────────────────────────┬─────────────────────────────────────────┘
                                             │ (merge main TRƯỚC — cả hai pull)
          ┌──────────────────────────────────┴───────────────────────────────────┐
          ▼ TRACK A (Bộ não)                                  TRACK B (Giác quan) ▼
  ┌─────────────────────────────┐                      ┌──────────────────────────────┐
  │ TASK-A10 llm client+prompts   │                      │ TASK-B10 normalization (+test) │◄─ chỉ cần 001
  │ TASK-A11 categories+priority  │                      │ TASK-B11 asr wrapper (+file)   │
  │ TASK-A12 nlu (intent+extract) │◄─A10                 │ TASK-B12 mic + VAD             │◄─ chỉ cần 001
  │ TASK-A13 SlotState+FSM loop   │◄─A11,A12             │ TASK-B13 conversation corpus   │◄─002 (A duyệt expected)
  │ TASK-A14 post-call track      │◄─A10                 └──────────────┬───────────────┘
  └──────────────┬──────────────┘                                     │
                 ▼ WAVE 2                                              ▼ WAVE 2
  ┌─────────────────────────────┐                      ┌──────────────────────────────┐
  │ TASK-A20 8 exception handlers │◄─A13,A12             │ TASK-B20 TTS Piper             │◄─003
  │ TASK-A21 eval harness+slotF1  │◄─A13,A20,B13         │ TASK-B21 pipeline+CLI  ◄─A13,B11,B12,B20  (integration owner B)
  └──────────────┬──────────────┘                      │ TASK-B22 Gradio UI     ◄─B21   │
                 │                                      └──────────────┬───────────────┘
                 ▼ WAVE 3 (gộp dần)                                    │
  ┌──────────────────────────────────────────────────────────────────┴───────────────┐
  │ TASK-A30 metric suite đầy đủ ◄─A21,B11,B13   │ TASK-B30 signature demo+video ◄─B22,A20 │
  │ TASK-A31 ablation ◄─A30                       │ TASK-S30 [PAIR] Architecture Doc        │
  │ TASK-A32 eval report ◄─A30,A31                │ TASK-S31 [PAIR] repro/requirements/README│
  │                                              │ TASK-S32 [PAIR] VERIFY (Gate 3) ◄─all   │
  └────────────────────────────────────────────────────────────────────────────────────┘
```

**Đường găng (critical path):** 002 → A12 → A13 → A20 → A21 → A30 → A32. Track B chạy song song; điểm chờ duy nhất của B là `engine.py` interface (có từ Wave 0) → B không bị A block.

**Mẹo khởi động:** B bắt **TASK-B10 (normalization)** ngay sau scaffold — thuần Python, 0 phụ thuộc engine → B có việc làm ngay trong lúc A dựng FSM.

---

## 2. Task Cards

### ───────── WAVE 0 · CONTRACT FREEZE `[PAIR]` ─────────

#### TASK-001 · Repo scaffold & tooling `[PAIR]`
- **Depends:** None · **Priority:** P0 · **Effort:** ~30m
- **Task:** Dựng cây thư mục theo [TECHSTACK.md §7](TECHSTACK.md); tạo `venv`; `requirements.txt` skeleton; `.env.example`; `.gitignore`; mọi `__init__.py`; file `base.py`/module rỗng có docstring.
- **Specs:** `.gitignore` chặn `.venv/`, `__pycache__/`, `.env`, `*.onnx`, `scenarios/audio/*.wav`. `.env.example` có `OLLAMA_HOST=http://localhost:11434`. README skeleton (setup steps).
- **Acceptance:**
  - Given repo trống, When chạy scaffold, Then cây thư mục khớp Blueprint §4, `python -c "import callbot"` OK.
  - Given `.gitignore`, Then `git status` không thấy `.venv`/`.env`.
- **Constraints:** Không viết logic. Chỉ scaffold. Merge main trước mọi task khác.

#### TASK-002 · Pydantic schemas (DATA CONTRACT) `[PAIR]`
- **Depends:** 001 · **Priority:** P0 · **Effort:** ~45m
- **Task:** Hiện thực `models/schemas.py` đúng [BLUEPRINT.md §2](BLUEPRINT.md): `SlotStatus`, `Slot`, `IntentSignals`, `NLUResult`, `PostCall`, `FinalOutput`.
- **Specs:** Field name 5 category **đúng tuyệt đối** brief (G_1/G_4/G_5 `phone`; G_2 `owner_phone`; G_3 `order_phone`; G_1/G_2 `vehicle_model`; G_4/G_5 `vehicle_line`; G_5 `current_odo` optional). Validator phone (10 số), VIN (17 ký tự).
- **Acceptance:**
  - Given `FinalOutput` với fields thiếu, When serialize, Then field thiếu = `null`, đúng cấu trúc `{category, fields, post_call}`.
  - Given phone "0885234567", Then validator pass; "abc" → fail.
- **Constraints:** **FROZEN sau merge.** Đổi field phải sync 2 người. Không thêm field ngoài brief.

#### TASK-003 · Interface base classes `[PAIR]`
- **Depends:** 002 · **Priority:** P0 · **Effort:** ~30m
- **Task:** Định nghĩa Protocol/ABC: `asr/base.py` (`ASR`, `ASRResult`), `llm/base.py` (`LLM`, `LLMResult`), `tts/base.py` (`TTS`, `TTSResult`), `normalization/base.py` (`Normalizer`), `dialogue/engine.py` (`DialogueEngine` signature + `TurnResult`, chưa cần logic).
- **Acceptance:** Given các base file, Then `mypy`/import OK, signature khớp [BLUEPRINT.md §3](BLUEPRINT.md); tạo được fake impl trong test.
- **Constraints:** **FROZEN sau merge.** Chỉ signature + docstring, không implement.

---

### ───────── WAVE 1 · TRACK A (Bộ não) ─────────

#### TASK-A10 · LLM client + prompts `[A]`
- **Depends:** 002, 003 · **P0 · ~60m**
- **Task:** `llm/ollama_client.py` implement `LLM` (gọi Ollama, hỗ trợ `json_schema` → format mode, đo `latency_ms`, retry 1 lần khi JSON sai). `llm/prompts.py`: prompt versioned cho NLU, response, post-call.
- **Specs:** Model qua `.env` (`OLLAMA_MODEL`, default `qwen3:8b`, fallback `qwen2.5:7b-instruct`). NLU prompt yêu cầu trả đúng `NLUResult` JSON. Response prompt: nhận field cần hỏi + state → 1 câu tiếng Việt tự nhiên, lịch sự.
- **Acceptance:**
  - Given câu "xe tôi chết máy trên cao tốc", When `complete(nlu_schema)`, Then trả JSON parse được thành `NLUResult`, `signals.emergency=true`.
  - Given JSON sai lần 1, Then retry, fail lần 2 → raise rõ ràng.
- **Constraints:** Không hardcode model/host. Prompt để file riêng (dễ tweak cho ablation).

#### TASK-A11 · Category config + next-field policy `[A]`
- **Depends:** 002 · **P0 · ~45m**
- **Task:** `dialogue/categories.py`: mỗi category → list field `(name, priority, required)` đúng [BLUEPRINT.md §2](BLUEPRINT.md). Hàm `pick_next_missing(category, state, emergency)` deterministic.
- **Acceptance:**
  - Given G_1 đã confirm `current_location`, Then next = `vehicle_condition` (priority kế).
  - Given emergency=true, Then field `priority>=90` (vd `current_odo`) bị bỏ qua.
  - Given mọi required đã confirm, Then trả `None`.
- **Constraints:** Pure function, không gọi LLM. Test được độc lập.

#### TASK-A12 · NLU layer: intent + extraction `[A]`
- **Depends:** A10 · **P0 · ~60m**
- **Task:** `dialogue/intent.py` (classify category / ambiguity) + `dialogue/extraction.py` (trích field + signals → `NLUResult`). Gọi `LLM` qua prompt A10.
- **Specs:** `extracted_fields` chỉ chứa field khách **vừa** cung cấp. `corrected_fields` tách riêng (exc #2). `category=None` khi mơ hồ (exc #3).
- **Acceptance:**
  - Given "à không phải, số em là 0912...", Then `signals.correction=true`, `corrected_fields={phone:"0912..."}`.
  - Given "tôi cần hỏi chút", Then `category=None`.
- **Constraints:** Không tự update state (đó là việc engine). Chỉ trả `NLUResult`.

#### TASK-A13 · SlotState + FSM happy-path loop `[A]`
- **Depends:** A11, A12 · **P0 · ~90m**
- **Task:** `dialogue/state.py` (`CallState`: dict các `Slot`, `category`, `turn_index`, `failed_turns`, `emergency`, `complete`). `dialogue/engine.py` implement `process()`/`finalize()`/`reset()` theo [BLUEPRINT.md §1](BLUEPRINT.md) — **chưa cần 8 exception đầy đủ**, chỉ happy path + missing-field (exc #1) + hangup finalize (exc #8).
- **Acceptance:**
  - Given G_3 happy path 4 lượt, When chạy, Then `finalize()` trả đúng `FinalOutput` schema, không re-ask field đã confirm (exc #1).
  - Given gọi `finalize()` giữa chừng, Then field chưa confirm = `null` (exc #8).
- **Constraints:** Dùng `LLM`/`Normalizer` qua protocol (test bằng fake). Không nhảy vào audio/asr.

#### TASK-A14 · Post-call track `[A]`
- **Depends:** A10 · **P1 · ~45m**
- **Task:** `dialogue/post_call.py`: feed full transcript → 1 LLM call → `PostCall(short_summary, sentimental_analysis, emergency)`.
- **Acceptance:** Given transcript ca tai nạn, Then `emergency="yes"`, `sentimental_analysis` ∈ {urgent, frustrated,...}, summary 1–2 câu.
- **Constraints:** Chạy 1 lần cuối call, không trong vòng lặp turn.

---

### ───────── WAVE 1 · TRACK B (Giác quan & Giọng) ─────────

#### TASK-B10 · Vietnamese normalization (+test) `[B]` ⚡ START NGAY
- **Depends:** 001 · **P0 · ~90m**
- **Task:** `normalization/vietnamese_numbers.py` implement `Normalizer`: chữ→số ("không tám tám lẻ năm"→`0885`), "lẻ/linh", "mươi/mười", ghép biển số ("ba mươi a năm sáu bảy"→`30A-567`), VIN, odo ("năm vạn cây"→`50000`). `tests/test_normalization.py` ≥15 case.
- **Acceptance:**
  - Given "không chín một hai ba bốn năm sáu bảy tám", Then `0912345678`.
  - Given "ba mươi a chấm năm sáu bảy chấm tám chín", Then chuẩn hóa biển số hợp lệ.
  - Given test suite, Then ≥15 case pass.
- **Constraints:** Pure Python, 0 dependency engine/LLM. **Đây là differentiator — đầu tư test kỹ.**

#### TASK-B11 · ASR wrapper + file mode `[B]`
- **Depends:** 003 · **P0 · ~75m**
- **Task:** `asr/faster_whisper_asr.py` implement `ASR`: mic buffer→text (`language="vi"`, `compute_type="int8"`), `from_file()` cho WER eval, đo `latency_ms`.
- **Specs:** Model size qua `.env` (`ASR_MODEL=medium`). Fallback `small` nếu latency cao.
- **Acceptance:**
  - Given 1 `.wav` tiếng Việt, When `from_file()`, Then trả transcript hợp lý + `latency_ms`.
  - Given mic buffer, Then `transcribe()` trả `ASRResult`.
- **Constraints:** Không xử lý dialogue. PhoWhisper là nâng cấp sau (ghi TODO).

#### TASK-B12 · Mic capture + VAD `[B]`
- **Depends:** 001 · **P0 · ~75m**
- **Task:** `audio/recorder.py` (sounddevice, 16kHz mono) + `audio/vad.py` (silero-vad: gom audio tới ~700ms im lặng = hết lượt).
- **Acceptance:** Given nói 1 câu rồi im, When VAD chạy, Then cắt đúng 1 utterance, trả buffer numpy.
- **Constraints:** Cross-platform; không phụ thuộc ASR (trả raw audio).

#### TASK-B13 · Conversation corpus `[B]` (A duyệt expected)
- **Depends:** 002 · **P1 · ~90m**
- **Task:** `scenarios/g1..g5.json` + `exceptions.json`: kịch bản khách Việt **thật** (lộn xộn, cáu, nói tắt, đọc số bằng lời). Mỗi file turn-by-turn `user input` + `expected {category, fields, signals}`.
- **Specs:** ≥2 scenario/category (≥10) + ≥3 exception. **B viết `user input`, A định nghĩa `expected`** (sửa phần khác nhau → ít conflict).
- **Acceptance:** Given mọi file, Then parse JSON OK, đủ ≥10 + ≥3 exception, field name khớp schema.
- **Constraints:** Tiếng Việt đời thật, không "sách giáo khoa". Dùng dòng xe VinFast thật.

---

### ───────── WAVE 2 ─────────

#### TASK-A20 · 8 exception handlers `[A]`
- **Depends:** A13, A12 · **P0 · ~120m**
- **Task:** `dialogue/exceptions.py` + tích hợp vào `engine.process()`: đủ 8 exception theo [BLUEPRINT.md §1](BLUEPRINT.md) / [TECHSTACK.md §9](TECHSTACK.md).
- **Acceptance (Gherkin, mỗi exc 1 case):**
  - #2 correction: confirm field rồi sửa → giá trị mới, **không hỏi lại field đã confirm**.
  - #3 ambiguous: input mơ hồ → hỏi **đúng 1 câu** trước khi route.
  - #4 out-of-scope: hỏi ngoài phạm vi → xin lỗi + đề nghị human.
  - #5 garbled: phone không parse → **đọc lại xác nhận** trước khi lưu.
  - #6 emergency: bắt ngay → cấp hotline + bỏ field priority thấp.
  - #7 stuck: 2 lượt không tiến triển → offer human.
- **Constraints:** Tất cả deterministic dựa cờ NLU. Không để LLM "tự nhớ".

#### TASK-A21 · Eval harness + slot F1 + exception tests `[A]`
- **Depends:** A13, A20, B13 · **P0 · ~90m**
- **Task:** `eval/run_eval.py` (feed scenario qua text-mode), `eval/metrics.py` (slot precision/recall/F1, routing accuracy), `tests/test_exception_handling.py` (≥3 exc), `test_dialogue_state.py`, `test_field_extraction.py`, `test_final_output_schema.py`.
- **Acceptance:** Given corpus B13, When `run_eval.py`, Then in slot F1 + routing accuracy per category; pytest ≥3 exception pass.
- **Constraints:** Deterministic (feed text, không qua ASR).

#### TASK-B20 · TTS Piper `[B]`
- **Depends:** 003 · **P2 (+5đ) · ~60m**
- **Task:** `tts/piper_tts.py` implement `TTS` (Piper ONNX, giọng VN, đo `latency_ms`). `audio/playback.py` phát audio.
- **Acceptance:** Given câu tiếng Việt, When `synthesize()`, Then ra audio phát được + `latency_ms`. Swap-able qua `.env` (`TTS_ENGINE=piper`).
- **Constraints:** Local, không gọi mạng. `edge_tts.py`/`vixtts.py` để stub pluggable (làm sau nếu dư).

#### TASK-B21 · Pipeline integration + CLI `[B]` (integration owner)
- **Depends:** A13, B11, B12, B20 · **P0 · ~90m**
- **Task:** `pipeline.py` (`turn()`: audio→ASR→engine.process→TTS, log `asr/llm/tts latency_ms` riêng) + `main.py` CLI (voice mode + **text mode**).
- **Acceptance:**
  - Given mic live, When 1 lượt, Then ASR→engine→reply chạy end-to-end, latency breakdown in ra.
  - Given `--text`, Then gõ input thay vì nói (cho dev/eval).
- **Constraints:** **B sở hữu file này, A review** (chỗ ráp 2 track). Dùng interface, không sửa nội bộ engine.

#### TASK-B22 · Gradio UI `[B]`
- **Depends:** B21 · **P2 · ~60m**
- **Task:** Gradio: mic-in + ô transcript + **panel JSON live** (state/final output) + nút phát TTS.
- **Acceptance:** Given browser, When nói, Then thấy transcript + JSON cập nhật realtime → quay video đẹp.
- **Constraints:** Bọc `pipeline.turn()`, không nhúng logic mới.

---

### ───────── WAVE 3 ─────────

#### TASK-A30 · Metric suite đầy đủ `[A]`
- **Depends:** A21, B11, B13 · **P0 · ~120m**
- **Task:** Mở rộng `metrics.py`: confusion matrix 5×5, **emergency recall** (adversarial set gồm ca "giọng bình tĩnh"), sentiment accuracy, **WER (jiwer)** trên `scenarios/audio/`, **LLM-as-judge** naturalness, **latency p50/p95** breakdown ASR/LLM/TTS.
- **Acceptance:** Given full suite, Then sinh bảng mọi metric + emergency recall tách riêng + latency p50/p95.
- **Constraints:** WER cần ≥5 `.wav` + reference (B13/B11 cấp).

#### TASK-A31 · Ablation study `[A]`
- **Depends:** A30 · **P1 · ~90m**
- **Task:** Chạy & ghi delta: có/không FSM · có/không tune recall · Qwen vs Việt-tuned · laptop medium vs GPU large WER.
- **Acceptance:** Given ablation runs, Then bảng so sánh có số liệu cho từng quyết định.
- **Constraints:** A/B model qua `.env` (tái dùng A10). Ghi rõ cấu hình mỗi run.

#### TASK-A32 · Evaluation Report `[A]`
- **Depends:** A30, A31 · **P0 · ~90m**
- **Task:** `docs/EVALUATION_REPORT.md` (Deliverable #4): mọi metric + **failure analysis (sai gì + VÌ SAO + hướng sửa)** + latency + ablation + đánh giá hạn chế trung thực.
- **Acceptance:** Given report, Then phủ 5 category + ≥3 exception + ≥1 automated metric + failure cases + latency per turn (đủ minimum brief §4).
- **Constraints:** Trung thực, phơi lỗi. Không tô hồng.

#### TASK-B30 · Signature demo + video `[B]`
- **Depends:** B22, A20 · **P1 · ~90m**
- **Task:** Dựng & quay "signature call" ([PLAN.md §5.1](PLAN.md)) + ca emergency "giọng bình tĩnh" (§5.2). Video demo qua Gradio.
- **Acceptance:** Given video, Then 1 call thể hiện: emergency-priority + correction + garbled-confirm + no-re-ask + normalization + JSON `emergency=yes`.
- **Constraints:** Có thể swap `edge_tts` cho giọng đẹp khi quay; **report ghi rõ bản nộp dùng Piper local**.

#### TASK-S30 · Architecture Doc finalize `[PAIR]`
- **Depends:** đa số (draft từ Wave 0) · **P0 · ~90m**
- **Task:** `docs/ARCHITECTURE.md` (Deliverable #1): pipeline, model choices, conversation flow, **8 chiến lược exception**, decisions & trade-offs (kể cả đã loại: LangGraph, edge-tts-primary, RAG).
- **Specs:** **A** viết phần dialogue/exception/eval; **B** viết ASR/TTS/normalization/pipeline (section khác nhau → ít conflict).
- **Acceptance:** Given doc, Then đồng bộ với code thực tế, có trade-off table.

#### TASK-S31 · Reproducibility `[PAIR]`
- **Depends:** all code · **P0 · ~60m**
- **Task:** `requirements.txt` pin `==`; `.env.example` đủ biến; README chạy được; **quét repo tránh leak secret**; test `pip install -r` trên máy/venv sạch.
- **Acceptance:** Given máy sạch, When `pip install -r` + theo README, Then bot chạy; `git grep` không thấy secret.
- **Constraints:** Không secret trong code (ô 20đ).

#### TASK-S32 · VERIFY — Gate 3 `[PAIR]`
- **Depends:** all · **P0 · ~60m**
- **Task:** Đối chiếu REQ matrix [BLUEPRINT.md §5](BLUEPRINT.md): mỗi REQ implemented & tested? Walkthrough 5 category + ≥3 exception. Sinh Verify Report.
- **Acceptance:** Given checklist, Then 5 deliverable đủ · 5 cat + ≥3 exc phủ eval · latency report có · failure analysis trung thực · repro pass · không secret.

---

## 3. Phân bổ & thứ tự khởi động (chống block & chống trùng)

| Ngày (gợi ý) | Track A (Hiệp) | Track B (Phương) |
|---|---|---|
| 1 | `[PAIR]` 001→002→003 (merge main) | `[PAIR]` cùng |
| 1–2 | — | **B10 normalization** (start ngay) |
| 2–3 | A10 llm, A11 categories | B11 asr, B12 mic+vad |
| 3–4 | A12 nlu, A14 post-call | B13 corpus (A duyệt expected) |
| 4–6 | **A13 FSM loop** | B20 tts |
| 6–8 | **A20 exceptions** | **B21 pipeline+CLI** (A review), B22 gradio |
| 8–10 | A21 eval harness | B30 signature demo dựng |
| 10–13 | A30 metrics, A31 ablation, A32 report | B30 quay video, hỗ trợ A30 (WER audio) |
| 13–14 | `[PAIR]` S30 arch-doc · S31 repro · S32 VERIFY | `[PAIR]` cùng |

> **Bất biến chống trùng:** mỗi task đụng file thuộc đúng 1 track (xem owner ở [PLAN.md §4.1](PLAN.md)); file shared (`schemas.py`, `*/base.py`, `pipeline.py`, `requirements.txt`) theo luật [PLAN.md §4.2–4.3](PLAN.md). Wave 0 merge trước → interface đóng băng → A/B song song không chờ nhau.

---

## 4. Bước tiếp theo

1. Review BLUEPRINT + TASK GRAPH → chốt thiết kế.
2. Thực thi lần lượt từ Wave 0; mỗi task làm đúng spec + acceptance criteria của nó.
3. Mỗi task xong → tự kiểm theo acceptance criteria → review chéo → merge rồi sang task kế.

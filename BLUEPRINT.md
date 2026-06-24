# BLUEPRINT: VinFast Callbot

> **Thiết kế chi tiết để code không mơ hồ.** Dẫn xuất từ [TECHSTACK.md](TECHSTACK.md) + [PLAN.md](PLAN.md), bám `intern_task3_callbot_brief.pdf`.
> Companion: [TASKGRAPH.md](TASKGRAPH.md) (cắt Blueprint này thành TASK-001… chia Track A/B).

### PROJECT INFO
| Field | Value |
|---|---|
| Project | VinFast Vietnamese Customer Service Callbot |
| Nature | CLI + Gradio · Realtime turn-based dialogue + post-call batch · Prototype/demo |
| Team | 2 người — Track A (Hiệp, "Bộ não") · Track B (Phương, "Giác quan & Giọng") |
| Date | 2026-06-24 |

### GOALS
- **Primary:** 5 category chạy end-to-end mic→ASR→LLM→JSON, xử lý đẹp 8 exception, eval rigorous → ăn chắc job offer.
- **Key message:** *bền · an toàn · đo được*.
- **Design system:** N/A (không phải UI project; Gradio chỉ để demo, dùng layout mặc định).

---

## 0. Decision Log (12 quyết định đã chốt — nguồn sự thật)

| ID | Quyết định | Lý do | Phương án đã loại |
|---|---|---|---|
| D1 | **PhoWhisper-CT2 first**, generic faster-whisper fallback | WER tiếng Việt tốt nhất từ đầu | Generic-default (defer PhoWhisper) |
| D2 | Normalize **theo field-type, SAU extraction** | Tránh phá ngữ cảnh ("anh Năm"→"anh 5") | Pre-LLM whole-utterance |
| D3 | Garbled (#5) trigger = **parse-fail của validator field** | Deterministic, đáng tin hơn ASR-confidence | LLM `unclear` / ASR confidence |
| D4 | Hangup (#8): **I/O timeout/disconnect → `finalize()`** | Bắt disconnect im lặng, không chỉ "nói cúp" | Chỉ xử lý hangup bằng lời |
| D5 | **Tự thu ≥5 clip Việt thật** cho WER (B sở hữu) | Giọng & domain thật → thuyết phục hơn | Common Voice vi / bỏ WER |
| D6 | **Giữ split hiện tại** (A solo critical path) | Quyết định của nhóm | Pair A13/A20 · dời task sang B |
| D7 | LLM-judge = **model cloud mạnh nhất sẵn có, dev-time-only, documented** | Judge là đồ nghề eval, bot vẫn local | Qwen self-judge / bỏ hẳn |
| D8 | **Script setup + pull model + note min-HW** | `pip install` không kéo ~7GB model | README prose only |
| D9 | **Định nghĩa tập giá trị** field phân loại | Giúp extraction + eval ổn định | Để free-text |
| D10 | **Luôn readback** phone/plate/VIN | Field "sai-thì-đắt", an toàn domain | Chỉ readback khi garbled |
| D11 | Report **latency E2E tổng/lượt** + breakdown | Brief đòi "end-to-end" | Chỉ breakdown thành phần |
| D12 | **Dùng LangGraph** (StateGraph) | Routing đa-intent + checkpointing + đúng stack VinSmart/XeCare | FSM Python thuần |

> **Bất biến qua mọi quyết định:** **"Thin LLM, Thick State Machine"** + seam `process(text)→(reply, SlotState)`. LangGraph chỉ là *nền orchestration*; logic slot-filling vẫn deterministic trong node Python → **Track B không bị ảnh hưởng.**

---

## 1. ARCHITECTURE — Vòng lặp một lượt (turn loop)

`DialogueEngine` là trái tim, **interface-agnostic** (chỉ nhận/trả text). Thuật toán một lượt:

```
process(user_text):                          # = một lượt traversal trên LangGraph StateGraph
  1. nlu = nlu_node(user_text, category)      # LLM: category + extracted_fields(raw) + corrected + signals
  2. apply_signals(nlu.signals):              # node deterministic
       emergency → flag + đẩy hotline + hạ ưu tiên field thấp        (#6)
       out_of_scope → redirect / transfer human                      (#4)
       correction → đánh dấu corrected_fields                        (#2)
  3. if category is None and nlu.category is None:                    (#3)
        → hỏi ĐÚNG 1 câu làm rõ; return
     else: lock category
  4. for (field, raw) in nlu.extracted_fields + corrected_fields:     # ← NORMALIZE Ở ĐÂY (D2)
        norm = normalizer.normalize_field(field, raw)                 # per-field, typed
        if norm.parse_failed:                                         # (#5 garbled, D3)
             slot.status = PENDING; queue readback(field); continue
        if field in READBACK_REQUIRED and not slot.readback_done:     # phone/plate/VIN (D10)
             slot.value = norm.value; slot.status = PENDING; queue readback(field); continue
        slot.value = norm.value; slot.status = confirmed | corrected
  5. next_field = pick_next_missing(category, state)                  # deterministic; emergency bỏ prio>=90
  6. if next_field is None: state.complete = True
  7. if failed_turns >= 2: offer human                               (#7)
  8. reply = response_node(next_field | pending_readback | closing, state)   # LLM: chỉ phrasing
  9. return TurnResult(reply, state, done=state.complete)

# (#8) Hangup: pipeline/IO phát hiện silence-timeout / disconnect / Ctrl-C → engine.finalize() (D4)
#      LangGraph checkpoint giữ CallState xuyên lượt → interrupt finalize từ checkpoint cuối.
```

> **Bất biến:** bước 2,3,5,6,7 + vòng 4 là **deterministic Python trong node**; LLM chỉ ở `nlu_node` & `response_node`. Bot vẫn gradeable & test được (25đ).

**Post-call track** (chạy 1 lần khi `done` hoặc hangup): feed full transcript → 1 LLM call → `short_summary` + `sentimental_analysis` + `emergency`.

---

## 2. DATA CONTRACT — `models/schemas.py` (đóng băng ở Wave 0)

> Đây là **contract** cả 2 track build dựa vào. Field name **đúng tuyệt đối** theo brief. Đổi file này = phải sync 2 người.

```python
# models/schemas.py — FROZEN CONTRACT. Changes require both tracks to agree.
from enum import Enum
from typing import Literal
from pydantic import BaseModel

# ---- Slot lifecycle ----
class SlotStatus(str, Enum):
    EMPTY = "empty"          # not asked yet
    PENDING = "pending"      # asked, awaiting / needs confirm (garbled)
    CONFIRMED = "confirmed"  # value accepted
    CORRECTED = "corrected"  # value overwritten after a correction

class Slot(BaseModel):
    value: str | None = None
    status: SlotStatus = SlotStatus.EMPTY
    raw_utterance: str | None = None   # what the caller actually said
    confirmed_at: int | None = None    # turn index when confirmed

# ---- NLU output (contract between extraction.py and engine.py) ----
class IntentSignals(BaseModel):
    emergency: bool = False
    out_of_scope: bool = False
    correction: bool = False
    hangup: bool = False
    unclear: bool = False        # caller gave garbled/uncertain value

Category = Literal["G_1", "G_2", "G_3", "G_4", "G_5"]

class NLUResult(BaseModel):
    category: Category | None = None         # None => ambiguous (exc #3)
    extracted_fields: dict[str, str] = {}    # ONLY fields provided/corrected this turn
    corrected_fields: dict[str, str] = {}    # field -> new value (exc #2)
    signals: IntentSignals = IntentSignals()

# ---- Post-call ----
class PostCall(BaseModel):
    short_summary: str
    sentimental_analysis: str                # calm / frustrated / urgent / ...
    emergency: Literal["yes", "no"]

# ---- Final output per call ----
class FinalOutput(BaseModel):
    category: Category | None
    fields: dict[str, str | None]            # null for unfilled (exc #8)
    post_call: PostCall
```

**Field định nghĩa per category** (dùng để validate + drive next-field). Ở `categories.py`, mỗi field có `(name, priority, required)`. `priority` nhỏ = hỏi trước; emergency bỏ field `priority >= 90`.

| Cat | Fields (đúng brief) — thứ tự priority gợi ý |
|---|---|
| **G_1** Cứu hộ | `current_location`(10) `vehicle_condition`(20) `phone`(30) `city_name`(40) `full_name`(50) `vehicle_model`(60) `license_plate_vin`(70) `vehicle_type`(80) `current_odo`(95←bỏ khi emergency) |
| **G_2** Bảo hành | `full_name` `owner_phone` `vehicle_model` `vehicle_usage_type` `license_plate_vin` `service_center` `vehicle_condition` |
| **G_3** Đơn hàng | `full_name` `order_phone` `order_code_dealer` `customer_type` |
| **G_4** Xe máy BH | `full_name` `phone` `vehicle_line` `license_plate_vin` `current_location` `vehicle_condition` |
| **G_5** HT từ xa | `full_name` `phone` `license_plate_vin` `vehicle_line` `current_odo`(optional) `vehicle_condition_details` |

> G_1 ưu tiên location/condition/phone **trước** identity → ca cứu hộ lấy đủ thông tin điều xe nhanh nhất (chứng minh hiểu nghề). `current_odo` của G_5 là `required=False`.

**Bổ sung contract (12 quyết định):**
- `READBACK_REQUIRED = {"phone", "owner_phone", "order_phone", "license_plate_vin"}` — luôn đọc lại xác nhận (D10).
- Validator trả `parse_failed`: phone (10 số), VIN (17 ký tự), plate (regex VN) (D3).
- `normalization/base.py`: `normalize_field(name, raw) -> NormResult(value: str | None, parse_failed: bool)` — per-field, chạy SAU extraction (D2).
- `dialogue/values.py` — tập giá trị field phân loại (D9, nền — chỉnh theo chính sách VinFast thật):
  - `vehicle_type` (G_1): `{"ô tô điện", "xe máy điện"}`
  - `vehicle_usage_type` (G_2): `{"cá nhân", "kinh doanh/dịch vụ", "taxi (GSM)"}`
  - `customer_type` (G_3): `{"cá nhân", "doanh nghiệp", "đại lý"}`

---

## 3. INTERFACE CONTRACTS (đóng băng ở Wave 0)

```python
# dialogue/engine.py — the seam between Track A and Track B
class TurnResult(BaseModel):
    reply: str
    done: bool = False
    state: dict           # snapshot of CallState for display/debug

class DialogueEngine:
    def __init__(self, llm: "LLM", normalizer: "Normalizer"): ...
    def process(self, user_text: str) -> TurnResult: ...   # one turn
    def finalize(self) -> FinalOutput: ...                  # assemble final JSON (also on hangup)
    def reset(self) -> None: ...                            # new call

# asr/base.py
class ASRResult(BaseModel):
    text: str
    confidence: float | None = None
    latency_ms: float

class ASR(Protocol):
    def transcribe(self, audio, sample_rate: int = 16000) -> ASRResult: ...
    @classmethod
    def from_file(cls, path: str) -> ASRResult: ...   # for WER eval on .wav

# llm/base.py
class LLMResult(BaseModel):
    text: str
    latency_ms: float

class LLM(Protocol):
    # json_schema set => force structured output (Ollama format mode)
    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult: ...

# tts/base.py
class TTSResult(BaseModel):
    audio: bytes
    latency_ms: float

class TTS(Protocol):
    def synthesize(self, text: str) -> TTSResult: ...

# normalization/base.py
class Normalizer(Protocol):
    def normalize(self, text: str) -> str: ...   # spoken VN numbers -> digits/plate/VIN
```

> **Vì sao đây là chìa khóa song song:** A code `DialogueEngine` chỉ phụ thuộc `LLM` + `Normalizer` *protocol* — test bằng fake/stub. B code `ASR/TTS/Normalizer` impl thật. Ráp ở `pipeline.py` (Wave 2) là khớp vì cùng interface. Không ai chờ ai.

---

## 4. FILE STRUCTURE + CHỦ SỞ HỮU

Đầy đủ ở [TECHSTACK.md §7](TECHSTACK.md) (cây thư mục) + [PLAN.md §4.1](PLAN.md) (bản đồ sở hữu). Tóm tắt seam:

| Vùng | Chủ | Phụ thuộc contract |
|---|---|---|
| `dialogue/ llm/ eval/ tests(dialogue)` | **A** | đọc `schemas.py`, gọi `LLM`/`Normalizer` protocol |
| `audio/ asr/ tts/ normalization/ main.py Gradio` | **B** | implement `ASR`/`TTS`/`Normalizer`, đọc `engine.py` interface |
| `models/schemas.py` `*/base.py` `pipeline.py` `requirements.txt` | **shared** | luật ở [PLAN.md §4.2](PLAN.md) |

---

## 5. REQUIREMENTS MATRIX (brief → blueprint → task)

| REQ-ID | Yêu cầu (brief) | Priority | Blueprint § | Task |
|---|---|---|---|---|
| REQ-01 | ASR mic→transcript tiếng Việt | P0 | §3 ASR | B11, B12 |
| REQ-02 | LLM local quản hội thoại — **qua LangGraph StateGraph** | P0 | §1, §3 LLM | A10, A13 |
| REQ-03 | 5 category + đúng field + final JSON | P0 | §2 | 002, A11, A12, A13 |
| REQ-04 | Post-call: summary/sentiment/emergency | P0 | §1 post-call | A14 |
| REQ-05 | Exc #1 missing — không re-ask | P0 | §1 b6 | A13, A20 |
| REQ-06 | Exc #2 correction — update không lặp | P0 | §1 b3 | A20 |
| REQ-07 | Exc #3 ambiguous — 1 câu hỏi | P0 | §1 b4 | A20 |
| REQ-08 | Exc #4 out-of-scope — redirect/human | P1 | §1 b3 | A20 |
| REQ-09 | Exc #5 garbled — **validator parse-fail → readback** | P0 | §1 b4 | A20, B10 |
| REQ-10 | Exc #6 emergency — hotline, skip field thấp | P0 | §1 b3,b6 | A20 |
| REQ-11 | Exc #7 stuck 2+ — offer human | P1 | §1 b8 | A20 |
| REQ-12 | Exc #8 hangup — partial JSON null + **I/O timeout/disconnect → finalize()** | P0 | §1, §2 | A13, A20, B21 |
| REQ-13 | Chuẩn hóa số/biển/VIN — **per-field, sau extraction** | P0* | §3 Normalizer | B10 |
| REQ-14 | Eval: ≥10 scenario + ≥3 exception | P0 | — | B13, A21, A30 |
| REQ-15 | Eval: ≥1 automated metric | P0 | — | A21, A30 |
| REQ-16 | Eval: failure analysis trung thực | P0 | — | A32 |
| REQ-17 | Eval: latency **E2E tổng/lượt** + breakdown p50/p95 | P0 | §1 + utils/latency | A30, B21 |
| REQ-18 | TTS bot nói tiếng Việt (+5) | P2 | §3 TTS | B20 |
| REQ-19 | requirements.txt pin, no secret in code | P0 | §4 | S31 |
| REQ-20 | Architecture Doc | P0 | toàn bộ | S30 |
| REQ-21 | Eval Report | P0 | — | A32 |
| REQ-22 | Luôn readback phone/plate/VIN (D10) | P0 | §2 | A13, A20 |
| REQ-23 | Tập giá trị field phân loại (D9) | P1 | §2 values.py | 002 |
| REQ-24 | Thu ≥5 .wav Việt + reference cho WER (D5) | P1 | — | B14 |

\* REQ-13 không bắt buộc trong brief nhưng là **differentiator** → P0 với nhóm.

---

## 6. TASK DECOMPOSITION PREVIEW

23 task, 4 wave (chi tiết + dependency graph ở [TASKGRAPH.md](TASKGRAPH.md)):

```
Wave 0 (PAIR, merge main TRƯỚC):  TASK-001 scaffold · TASK-002 schemas · TASK-003 interfaces
Wave 1 (song song):  A10 llm · A11 categories · A12 nlu · A13 langgraph-graph · A14 postcall
                     B10 normalize · B11 asr · B12 mic+vad · B13 corpus · B14 wer-audio
Wave 2 (song song):  A20 exceptions · A21 eval-harness
                     B20 tts · B21 pipeline+cli (+hangup) · B22 gradio
Wave 3 (gộp dần):    A30 metrics-full · A31 ablation · A32 eval-report
                     B30 signature-demo · S30 arch-doc · S31 repro · S32 VERIFY
```

### CHECKPOINT
- [ ] Architecture (turn loop §1) khớp kỳ vọng
- [ ] Data contract §2 (schemas + field names) đúng brief
- [ ] Interface §3 đủ để 2 track song song
- [ ] Requirements matrix §5 phủ hết brief
- [ ] Task decomposition §6 hợp lý

> Trả lời **"APPROVED"** để chốt thiết kế và bắt đầu thực thi từ Wave 0.

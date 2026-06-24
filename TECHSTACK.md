# VinFast Callbot — Tech Stack Tối Ưu (Bản Hợp Nhất)

> **Tài liệu này là nguồn sự thật duy nhất về *chọn công cụ gì và VÌ SAO*.**
> Companion: [PLAN.md](PLAN.md) (*làm theo trình tự nào*).
> Task 3 · VinSmart Future AI Internship · 2 tuần · Nhóm 2 người.
> Hợp nhất từ 4 nguồn: 2 file chiến lược/kế hoạch của nhóm + 2 file guide/skeleton của bạn,
> đã đối chiếu trực tiếp với `intern_task3_callbot_brief.pdf` và kiểm chứng web (6/2026).

---

## 0. Cách đọc tài liệu này

Mỗi lựa chọn dưới đây đi kèm **3 thứ**:
1. **Chọn gì** (quyết định đã chốt).
2. **Vì sao chọn** (trade-off, không phải sở thích).
3. **Vì sao điều này giúp ta hơn nhóm khác** — vì đây là cuộc thi tuyển dụng, không phải bài tập.

Brief chấm trên **4 ô điểm + 1 bonus**:

| Ô điểm | Trọng số | Cái thực sự được chấm |
|---|---|---|
| Pipeline Functionality | **30** | 5 category chạy end-to-end mic→ASR→LLM→JSON |
| Dialogue Design & Exception | **25** | Logic hội thoại mượt + 8 tình huống lỗi |
| Evaluation Framework | **25** | Độ *rigour* của thiết kế eval, **không** phải điểm số cao |
| Code Quality & Reproducibility | **20** | Code sạch, `pip install -r` chạy được máy sạch |
| TTS Bonus | **+5** | Bot nói tiếng Việt |

> **Hệ quả số học:** Dialogue+Exception (25) + Eval (25) = **50/100** — gần gấp đôi Pipeline (30).
> Tiền (thời gian) đổ vào **state management + evaluation**, không phải đánh bóng ASR/TTS.

---

## 1. Triết lý kiến trúc cốt lõi: "Thin LLM, Thick State Machine"

Đây là **quyết định quan trọng nhất** và là điểm cả 4 nguồn đều đồng thuận (chỉ khác cách hiện thực).

| Cách tiếp cận | Ưu | Nhược | Quyết định |
|---|---|---|---|
| LLM giữ toàn bộ state qua prompt history | Code ít, "tự nhiên" | Re-ask field đã confirm, quên giá trị đã sửa, vỡ ở exception #1/#2/#8 | ❌ Loại |
| **FSM xác định giữ state · LLM chỉ NLU + NLG** | Kiểm soát chặt từng field, partial JSON dễ, deterministic → test được | Phải tự code state machine | ✅ **Chọn** |

LLM **chỉ làm 4 việc**: (1) phân loại intent, (2) trích xuất entity, (3) sinh câu nói, (4) tóm tắt cuối call.
Toàn bộ logic *hỏi field nào tiếp theo · field nào đã confirm · khi nào escalate* do **FSM xác định** quản.

**`SlotState` theo dõi mỗi field 4 thuộc tính:** `value`, `status` (`empty`/`pending`/`confirmed`/`corrected`), `raw_utterance`, `confirmed_at`.
- FSM (không phải LLM) quyết định **hỏi gì tiếp** → deterministic.
- LLM chỉ quyết định **phrasing** câu hỏi và **hiểu** input.
- Khách cúp máy → dump `SlotState`, field `status != confirmed` → `null`. Sạch sẽ, đúng exception #8.

> **Vì sao hơn nhóm khác:** Đa số nhóm để LLM "tự nhớ" state qua history → re-ask, quên giá trị sửa, vỡ khi khách nói lộn xộn. Tách NLU/NLG khỏi state control chính là **"clear design thinking"** mà brief chấm ở ô 25đ.

### 1.1 Quyết định: dùng LangGraph (StateGraph), KHÔNG hand-roll loop

> **Chốt: hiện thực bằng LangGraph (StateGraph). Logic slot-filling vẫn deterministic trong node Python.**

| Tiêu chí | LangGraph (✅ chọn) | FSM hand-rolled |
|---|---|---|
| Routing đa-intent + subgraph 5 category | Native, khai báo rõ | Tự viết dispatch |
| Checkpointing / interrupt (phục vụ hangup #8, escalation #7) | Có sẵn | Tự quản |
| Đúng stack VinSmart + tái dùng nền XeCare | Cao — khoe năng lực liên quan | Không |
| Chi phí | +dep `langgraph`; phải giữ graph gọn kẻo over-engineer | 0 dep |

**Vì sao là tín hiệu senior:** chọn đúng công cụ cho bài toán *có* state máy + routing + interrupt; **giữ graph tối giản, document rõ từng node** → minh bạch như FSM nhưng tận dụng checkpointing. Ghi quyết định + phương án FSM-thuần đã cân nhắc vào Architecture Doc.

---

## 2. Sơ đồ pipeline

```
        ┌──────────────── CONVERSATION TRACK (realtime, mỗi lượt) ────────────────┐
        │                                                                          │
🎤 Mic ─►[VAD: silero-vad]─►[ASR: faster-whisper]─► transcript                      │
        │                            │                                             │
        │                            ▼                                             │
        │   ┌──────────── DialogueEngine (LangGraph StateGraph) ───────────┐       │
        │   │  1. Intent Classifier      (LLM)                              │       │
        │   │  2. Router  ──► G_1 / G_2 / G_3 / G_4 / G_5                   │       │
        │   │  3. Entity Extractor       (LLM → Pydantic)                   │       │
        │   │  4. Normalization (per-field, typed) ◄── differentiator       │       │
        │   │  5. SlotState update + 8 Exception handlers (deterministic) ──┼───────┼─ single
        │   │  6. Next-field policy      (deterministic)                    │       │  source
        │   │  7. Response Generator     (LLM phrasing)                     │       │  of truth
        │   └────────────────────────────────────────────────────────────────┘    │
        │                            │ text response + SlotState                   │
        │                  ┌─────────┴─────────┐                                   │
        │                  ▼                   ▼                                   │
        │         [TTS: Piper] (opt)    in-call JSON display                       │
        │                  ▼                                                       │
        │              🔊 Speaker                                                  │
        └──────────────────────────────────────────────────────────────────────────┘
                                     │ (khi call kết thúc / hangup)
                                     ▼
        ┌──────────────── POST-CALL TRACK (batch, cuối call) ──────────────────────┐
        │  full transcript ─► [LLM] ─► short_summary / sentimental_analysis /       │
        │                              emergency (yes/no)                           │
        └──────────────────────────────────────────────────────────────────────────┘
                                     ▼
        Final JSON: { "category", "fields": {...}, "post_call": {...} }
```

**Lớp tách biệt để eval được (điểm "design thinking"):** `DialogueEngine.process(text) → (response, SlotState)` — **interface-agnostic**, không biết gì về mic/ASR/TTS.
- Eval dialogue = feed transcript text → deterministic, không dính ASR noise.
- Eval ASR = đo WER riêng trên audio mẫu.
- Demo = bọc engine bằng CLI hoặc Gradio.

---

## 3. Tech Stack đầy đủ (đã kiểm chứng 6/2026)

| Lớp | Lựa chọn (chốt) | Phương án thay thế / fallback | Vì sao chọn |
|---|---|---|---|
| **Ngôn ngữ** | **Python 3.11** | 3.10 | Hệ sinh thái ASR/LLM/TTS chín; 3.12+ đôi khi thiếu wheel cho audio lib |
| **Env / Repro** | **`venv` + `pip` + `requirements.txt` pin `==`** | `uv` | Grader chạy đúng `pip install -r` như brief mô tả; chuẩn nhất, ít bất ngờ. (`uv` nhanh hơn nhưng thêm 1 thứ grader phải cài) |
| **VAD** | **`silero-vad`** | `webrtcvad` | Bắt hết câu (turn-taking) cho mic live; không có VAD bot không biết khi nào khách nói xong |
| **ASR (bắt buộc)** | **PhoWhisper-medium (CT2/faster-whisper)** mặc định | generic faster-whisper / `large-v3` trên GPU cho WER offline | WER tiếng Việt tốt nhất ngay từ đầu (differentiator "tiếng Việt thật"). CT2 convert một lần, có bản pre-converted trên HF; generic faster-whisper làm fallback |
| **LLM runtime (bắt buộc, local)** | **Ollama** (Windows-native) | llama.cpp, vLLM | Backend local dễ nhất trên Windows, API OpenAI-compatible → đổi model 1 dòng. (vLLM cần GPU rời/Linux → loại cho laptop) |
| **LLM model** | **Qwen-class 7–8B** (`qwen3:8b`, fallback `qwen2.5:7b-instruct`) + **A/B 1 bản Việt-tuned** | SeaLLM / Vistral-7B / PhoGPT-4B | Tiếng Việt tốt + JSON/tool-calling đáng tin, Apache-2.0. Q4 ~5GB vừa RAM. A/B **kiêm luôn 1 ablation eval** (xem §6) |
| **Structured output** | **Pydantic v2 + Ollama JSON/format mode** | `instructor`, `outlines` | Ép LLM trả đúng schema 5 category, validate phone/biển/VIN, bắt lỗi sớm |
| **Dialogue core** | **LangGraph (StateGraph)** (§1.1) | hand-rolled FSM | Native routing + checkpointing/interrupt; giữ graph gọn, logic vẫn deterministic trong node |
| **Chuẩn hóa thực thể VN** | **Module riêng `normalization/`** (chữ→số, "lẻ/linh/mươi", ghép biển/VIN/odo) **có test** | — | Khách Việt **nói** số điện thoại/biển số → ASR ra chữ. Không nhóm nào để ý lớp này (xem §5) |
| **TTS (+5, optional)** | **Piper (local, ONNX)** primary; interface để swap | edge-tts (video) / viXTTS (GPU) / VieNeu-TTS | Xem §4 — phân tích đầy đủ |
| **Audio I/O** | **`sounddevice` + `numpy`** | `pyaudio` | numpy-native, ít lỗi build trên Windows hơn PyAudio |
| **Frontend** | **CLI** (dev/eval) **+ Gradio** (video demo) | chỉ CLI | CLI cho iterate nhanh + chạy eval; Gradio mic-in + panel JSON live để quay video signature |
| **Eval** | **pytest + metric tự viết + `jiwer` (WER) + LLM-as-judge** | — | Routing confusion matrix, slot F1, WER, latency p50/p95, chấm naturalness bằng rubric. **LLM-judge = model mạnh nhất sẵn có (cloud thương mại, dev-time), dev-time-only, Qwen-local fallback, document bản nộp không phụ thuộc.** Xem §6 |
| **Logging / Latency** | **stdlib `logging`** (hoặc `structlog`) + timer thủ công | — | Brief bắt buộc report latency per turn → log có cấu trúc |
| **Config / Secrets** | **`python-dotenv` + `.env`** (+ `.env.example`) | — | **Tuyệt đối không hardcode** key/token — ô Reproducibility 20đ |

### 3.1 Phân bổ phần cứng

- **Laptop Zenbook (CPU)** — môi trường "thật" của bot: faster-whisper medium int8 + Qwen Q4 + Piper. Demo live chạy ở đây.
- **GPU PC riêng** — chạy *offline, không phải dependency của demo*: PhoWhisper-large cho WER chính xác nhất, viXTTS nếu muốn giọng premium cho clip signature, A/B model nặng hơn.

> **So sánh laptop-vs-GPU chính là một data point eval nữa** — biến hạn chế phần cứng thành một thí nghiệm có kiểm soát.

---

## 4. Quyết định TTS (đã nghiên cứu kỹ theo yêu cầu)

TTS chỉ **+5đ** và là optional → nguyên tắc: **lấy bonus an toàn nhất, không nổ latency, không phá câu chuyện kiến trúc.**

### 4.1 Bốn ứng viên — đối chiếu thực tế (kiểm chứng web 6/2026)

| Engine | Local? | Chất lượng giọng VN | Rủi ro | Phù hợp ở đâu |
|---|---|---|---|---|
| **Piper** | ✅ Hoàn toàn (ONNX ~15M, CPU real-time) | Trung bình (voice `vais1000` medium là tốt nhất; còn `25hours_single` low, `vivos` x_low) | Thấp nhất | **Primary** — bonus chắc, offline, reproducible |
| **edge-tts** | ❌ Cloud (endpoint Microsoft Edge) | Cao, rất tự nhiên (`vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`), không cần key | Cần internet; endpoint không chính thức → có thể đổi/bị rate-limit; **fail nếu grader chạy offline** | Swap cho **video demo** |
| **viXTTS** | ✅ Local nhưng cần GPU | Cao (fine-tune XTTS-v2 trên viVoice) | **Yếu với câu < 10 từ** (đuôi tiếng lạ) — mà callbot hay trả lời ngắn; nặng; license CPML non-commercial | Clip signature trên GPU PC nếu muốn premium |
| **VieNeu-TTS** | ✅ Local (CPU, ONNX, 24kHz, real-time) | Cao hơn Piper | Mới, ít kiểm chứng, thêm dep | Nâng cấp local nếu Piper chưa đạt |

### 4.2 Quyết định & lý do

> **Primary = Piper (local). TTS giấu sau interface `tts/base.py` → đổi engine trong 1 dòng.**

**Vì sao Piper, không phải edge-tts (dù edge-tts giọng đẹp hơn):**
1. **Reproducibility là 20đ và là deliverable chấm.** Grader có thể `pip install -r` rồi chạy trên máy **offline/sau firewall**. edge-tts sẽ **fail im lặng** ở đó; Piper vẫn chạy. TTS optional nên fail không chết pipeline — nhưng "TTS chỉ chạy khi có internet tới endpoint không chính thức" là một liability, không phải điểm cộng.
2. **Câu chuyện kiến trúc nhất quán:** brief bắt buộc LLM *local*. Một stack **fully local/offline** (ASR + LLM + TTS đều không gọi mạng) là một thông điệp mạch lạc và là tín hiệu kỹ thuật. edge-tts phá vỡ điều đó.
3. **Không rủi ro mạng khi quay video demo** — không có cảnh "bot đứng hình vì mất mạng giữa câu".
4. **Kỷ luật của nhóm:** TTS chỉ 5đ, không đua giọng đẹp. Piper là đường lấy +5 an toàn nhất.

**Vì sao vẫn giữ interface pluggable (đây mới là nước đi senior):**
- `tts/base.py` định nghĩa `synthesize(text) -> audio`. `piper_tts.py` là impl mặc định.
- **Khi quay video signature** có thể swap sang `edge_tts.py` (mạng của mình, mình kiểm soát) để khoe giọng tự nhiên — *vẫn report trung thực trong doc rằng bản nộp/repro dùng Piper local*.
- Muốn giọng premium offline → cắm `vixtts.py` chạy trên GPU PC cho riêng clip.
- **Quyết định TTS trở nên reversible trong 1 dòng** → không phải đặt cược. Đó chính là "design thinking".

> **Vì sao hơn nhóm khác:** Nhóm khác hoặc bỏ TTS, hoặc bolt edge-tts vào rồi **rớt ngay ở reproducibility check offline**. Ta: local-first chạy được trên máy sạch của grader, **vẫn** có thể khoe giọng đẹp trong video nhờ interface — và *nói thẳng* sự khác biệt đó trong report. Đó là cộng điểm kép: pipeline + code quality + honesty.

---

## 5. Differentiator kỹ thuật: Chuẩn hóa thực thể tiếng Việt nói

**Đây là lợi thế gần như không nhóm nào có**, và là lý do bot ta không vỡ khi khách nói thật.

Khách Việt **đọc** số điện thoại / biển số / VIN / odo bằng lời → ASR trả về chữ:
- `"không tám tám lẻ năm hai ba bốn"` → `0885234...`
- `"ba mươi a năm sáu bảy chấm tám chín"` → `30A-567.89`
- `"năm vạn cây"` / `"năm mươi nghìn cây số"` → odo `50000`

Module `normalization/vietnamese_numbers.py` (Python thuần, **có unit test riêng**) xử lý: chữ→số, các biến thể "lẻ/linh", "mươi/mười", ghép cụm biển số, chuẩn hóa VIN 17 ký tự, odo. Chạy **per-field SAU extraction** (biết field type mới chuẩn hóa → tránh phá ngữ cảnh kiểu "anh Năm"→"anh 5"). **Parse-fail = trigger garbled #5** (đọc lại xác nhận). API: `normalize_field(name, raw) → (value, parse_failed)`.

> **Vì sao hơn nhóm khác:** Bot nhóm khác nát khi gặp SĐT/biển số đọc bằng lời (vì họ test bằng text "sách giáo khoa"). Lớp này + test = bằng chứng nhóm **đã thực sự nghe khách Việt nói** — đúng chất domain CSKH thật.

---

## 6. Evaluation stack — nơi thắng job (25đ)

Brief chấm **độ rigour của thiết kế eval, KHÔNG phải điểm số**. Đây là deliverable biến "bot tốt" thành "tín hiệu tuyển dụng".

| Thành phần | Công cụ | Đo gì |
|---|---|---|
| Test runner | **pytest** | Mỗi scenario = 1 test, feed transcript qua text-mode |
| Scenario format | **JSON/YAML fixtures** | Turn-by-turn input + expected category/fields/flags |
| Routing accuracy | metric tự viết | **Confusion matrix** 5×5 |
| Slot accuracy | metric tự viết | **Precision/Recall/F1 per field** vs expected JSON (automated metric ✓) |
| ASR quality | **`jiwer`** | **WER** trên `.wav` clip có reference transcript |
| Dialogue quality | **LLM-as-judge** | Chấm naturalness/correctness theo rubric; **model mạnh nhất sẵn có (cloud thương mại, dev-time), dev-time-only, documented**, Qwen-local fallback |
| Emergency/Sentiment | metric tự viết | Accuracy + **recall riêng cho emergency** (xem dưới) |
| Latency | timer harness | **E2E tổng/lượt + breakdown ASR/LLM/TTS, p50/p95** |

**Ba thứ nâng eval từ "báo cáo điểm" lên "thí nghiệm có kiểm soát" (gần như không intern nào làm):**

1. **Emergency = bài toán cost-asymmetry, tune RECALL, đo riêng.** Thà báo nhầm hơn bỏ sót ca an toàn tính mạng. Có ca "giọng bình tĩnh" (*"Anh ơi xe em đỗ giữa đường không nổ được, trời tối quá..."*) — nghe thường nhưng nguy hiểm. Đo **recall trên bộ adversarial case**, không chỉ accuracy. → chứng minh emergency detection **không phải match keyword**.
2. **Ablation study:** đo delta của *có vs không state-machine* · *có vs không tune recall* · *Qwen3 vs bản Việt-tuned* · *laptop medium vs GPU large WER*. A/B model ở §3 **kiêm luôn** một dòng ablation — một mũi tên hai đích.
3. **Turn-level testing + failure analysis có root cause:** bắt re-ask giữa cuộc thoại; mỗi failure ghi *sai gì + VÌ SAO* + hướng sửa. Phơi lỗi = tự tin chuyên môn, không phải giấu.

> **Vì sao hơn nhóm khác:** Nhóm khác dừng ở *"đạt 87% accuracy"*. Ta giao một **eval framework như tác phẩm nghiên cứu**: confusion matrix + slot F1 + WER + latency p50/p95 + adversarial recall + ablation + failure analysis trung thực. Đây là 25đ dễ bị làm hời hợt nhất → cũng là chỗ dễ bứt phá nhất.

---

## 7. Cấu trúc thư mục (đã hợp nhất)

> Dialogue dựng trên LangGraph StateGraph (logic deterministic trong node); bổ sung `normalization/`, eval đầy đủ, TTS pluggable, `scripts/` setup.

```
AI-Callbot-Vinfast/
  README.md
  requirements.txt          # pin == — Deliverable #5
  .env.example
  .gitignore                # .env, audio out, __pycache__
  scripts/
    setup.ps1 / setup.sh    # pull Ollama models + ASR/TTS weights + min-HW note  ← NEW

  docs/
    ARCHITECTURE.md          # Deliverable #1
    EVALUATION_REPORT.md     # Deliverable #4

  src/callbot/
    __init__.py
    main.py                  # CLI entry (voice + text mode)
    pipeline.py              # turn(): audio→ASR→engine→TTS, đo latency
    config.py                # load .env

    audio/
      recorder.py            # mic capture (sounddevice)
      vad.py                 # silero-vad turn detection
      playback.py            # TTS playback
    asr/
      base.py                # ASR interface: transcribe(audio)->text
      faster_whisper_asr.py  # default impl (int8, language="vi")
    llm/
      base.py                # LLM interface
      ollama_client.py       # Ollama wrapper, JSON/format mode
      prompts.py             # versioned prompts: NLU / response / post-call
    dialogue/
      engine.py              # DialogueEngine.process/finalize/reset — public seam over the graph
      graph.py               # LangGraph StateGraph: build nodes + edges        ← NEW
      nodes.py               # node fns: nlu / route / slot_update / next_field / respond  ← NEW
      state.py               # CallState (LangGraph state schema)
      categories.py          # G_1..G_5 fields + priority + required + readback_required
      values.py              # allowed values for classification fields         ← NEW
      intent.py              # category classify / ambiguity (#3)
      extraction.py          # LLM structured extraction → Pydantic
      exceptions.py          # 8 handlers (deterministic, flag-driven)
      response.py            # response generation (LLM phrasing)
      post_call.py           # summary / sentiment / emergency
    normalization/           # ← DIFFERENTIATOR
      base.py
      vietnamese_numbers.py  # normalize_field(name, raw)->(value, parse_failed) — per-field/typed
    models/
      schemas.py             # Pydantic: 5 category models + final JSON
    tts/
      base.py                # TTS interface: synthesize(text)->audio
      piper_tts.py           # default (local); edge_tts.py / vixtts.py pluggable
    utils/
      logging.py
      latency.py             # per-turn timers (asr/llm/tts ms)

  scenarios/                 # eval fixtures
    g1_roadside_rescue.json ... g5_remote_tech_support.json
    exceptions.json
    audio/                   # ≥5 .wav Việt thật + reference cho WER (phải THU — TASK-B14)

  tests/
    test_dialogue_state.py
    test_field_extraction.py
    test_exception_handling.py
    test_normalization.py     # ← test cho lớp chuẩn hóa
    test_final_output_schema.py

  eval/
    run_eval.py
    metrics.py                # confusion matrix, slot F1, WER, latency, LLM-judge
    report_template.md
```

---

## 8. Schema dữ liệu (Pydantic v2) — bám sát brief

Mỗi category là 1 model, field `None` = chưa thu thập (drive "chỉ hỏi field thiếu"). Field name **đúng tuyệt đối** theo brief:

| Cat | Fields (theo brief) |
|---|---|
| **G_1** Cứu hộ | `full_name, phone, vehicle_model, license_plate_vin, vehicle_type, current_odo, current_location, city_name, vehicle_condition` |
| **G_2** Bảo hành & Sửa chữa | `full_name, owner_phone, vehicle_model, vehicle_usage_type, license_plate_vin, service_center, vehicle_condition` |
| **G_3** Đơn hàng | `full_name, order_phone, order_code_dealer, customer_type` |
| **G_4** Xe máy – Bảo hành | `full_name, phone, vehicle_line, license_plate_vin, current_location, vehicle_condition` |
| **G_5** Hỗ trợ kỹ thuật từ xa | `full_name, phone, license_plate_vin, vehicle_line, current_odo (optional), vehicle_condition_details (incl. software version)` |

**Post-call** (sinh từ full transcript cuối call, **không** thu trong dialogue): `short_summary` (string), `sentimental_analysis` (string: calm/frustrated/urgent), `emergency` (`yes`/`no`).

**Final JSON:** `{ "category": "G_1", "fields": {...}, "post_call": { "short_summary": "...", "sentimental_analysis": "urgent", "emergency": "yes" } }`

> ⚠️ Lưu ý field name khác nhau giữa category: G_1/G_4/G_5 dùng `phone`, G_2 dùng `owner_phone`, G_3 dùng `order_phone`. G_1/G_2 dùng `vehicle_model`, G_4/G_5 dùng `vehicle_line`. Sai tên field = mất điểm Pipeline. Chuẩn hóa từ brief vào `schemas.py` ngay Phase 0.

---

## 9. Map 8 Exception → cơ chế (đều deterministic trong node)

| # | Tình huống (brief) | Cơ chế |
|---|---|---|
| 1 | Missing field | Node hỏi field `status=empty` tiếp theo theo priority; **không bao giờ re-ask field đã confirm** |
| 2 | Customer corrects | NLU phát cờ `correction` + giá trị mới → overwrite slot, acknowledge, đi tiếp **không lặp lại field đã confirm** |
| 3 | Ambiguous intent | NLU `category=null` → hỏi **đúng 1 câu** làm rõ trước khi route |
| 4 | Out-of-scope | NLU cờ `out_of_scope` → xin lỗi lịch sự + redirect / đề nghị chuyển human |
| 5 | Garbled input | **Validator field parse-fail** (phone/plate/VIN) → **đọc lại + xác nhận** trước khi lưu (không dựa ASR-confidence) |
| 6 | Emergency | NLU `emergency=true` → **cấp hotline cứu hộ ngay**, bỏ qua field ưu tiên thấp (vd odo) |
| 7 | Stuck 2+ turns | counter `failed_turns >= 2` → đề nghị chuyển human |
| 8 | Hangs up mid-call | I/O **silence-timeout / disconnect / interrupt** → `finalize()` dump partial JSON, field chưa confirm = `null` |

> **Nước đi thiết kế then chốt:** các exception là **deterministic trong node dựa trên cờ LLM trích ra**, KHÔNG dựa vào việc "LLM nhớ phải làm". Đó là thứ làm bot **gradeable & testable** — và là 25đ.

---

## 10. Bảng quyết định cuối (đã chốt)

| # | Quyết định | Chốt | Vì sao |
|---|---|---|---|
| 1 | Dialogue core | **LangGraph (StateGraph)** | Routing đa-intent + checkpointing/interrupt + đúng stack VinSmart/XeCare; graph gọn, logic deterministic trong node |
| 2 | LLM | **Qwen 7–8B + A/B 1 bản Việt-tuned** | A/B kiêm ablation eval |
| 3 | TTS | **Piper local primary, interface pluggable** | An toàn +5, reproducible offline, swap được cho video |
| 4 | Frontend | **CLI + Gradio** | CLI cho eval, Gradio cho video signature |
| 5 | ASR | **PhoWhisper-medium (CT2) first** (laptop) + generic faster-whisper fallback + large trên GPU (WER eval) | WER tiếng Việt tốt nhất từ đầu; CT2 có bản pre-converted |
| 6 | G_2/G_4 policy | **Chính sách tĩnh thật, KHÔNG RAG** | Dồn thời gian cho eval; RAG không tạo khác biệt mà ăn thời gian |

---

## 11. Risk Register (rút gọn — chi tiết ở PLAN.md §7)

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Latency ASR+LLM trên CPU quá cao cho "live" | Cao | medium/small int8 + Qwen Q4; đo sớm Phase 0; hạ size / iGPU Vulkan nếu cần |
| LLM trả JSON sai schema | TB | Pydantic validate + retry + JSON mode |
| Re-ask field đã confirm | Cao | **Đã giải quyết bằng kiến trúc state-machine (LangGraph)** |
| TTS edge-tts fail khi repro offline | TB | **Piper local làm primary**; edge-tts chỉ cho video |
| Leak secret khi push | TB | `.env` + `.gitignore` + quét repo trước nộp |
| Sa đà TTS/UI, bỏ bê eval | Cao | Eval 25đ ≫ TTS 5đ; eval viết từ Phase 1 |
| PhoWhisper-CT2 là default — convert/pull | Thấp | Có bản pre-converted trên HF; generic faster-whisper là fallback chạy ngay |
| LangGraph thành over-engineering / khó đọc | TB | Giữ graph tối giản (≤7 node), document từng node, ví dụ chạy được |

---

## 12. Vì sao tổng thể dự án này hơn các nhóm khác (tóm tắt 1 trang)

| Trục | Nhóm khác thường làm | Nhóm ta | Phẩm chất phô ra |
|---|---|---|---|
| **State** | LLM tự nhớ qua history → re-ask, vỡ | FSM xác định, SlotState 4 thuộc tính | Clear design thinking |
| **Domain** | `xe A`, service center giả, tiếng Việt "sách giáo khoa" | Dòng xe VinFast thật, **cách khách Việt nói thật** + chuẩn hóa số | Hiểu domain, không bịa |
| **Emergency** | field tick yes/no | Cost-asymmetry, tune recall, đo recall riêng bằng adversarial | Hiểu nghề cứu hộ thật |
| **Eval** | "đạt 87% accuracy" rồi dừng | Confusion matrix + slot F1 + WER + latency p50/p95 + ablation + failure analysis | Rigour + trung thực |
| **TTS** | bỏ, hoặc edge-tts rớt khi repro offline | Piper local-first + interface pluggable, nói rõ trade-off | Phán đoán + honesty |
| **Tooling** | nhồi framework không lý do / hand-roll mọi thứ | LangGraph cho routing+checkpointing, graph tối giản + document từng node | Đúng công cụ, không over-engineer |

> **Một câu định vị (lặp ở mọi deliverable):**
> *"Tụi em không xây một con chatbot demo. Tụi em xây một hệ CSKH **bền với khách thật và an toàn với ca khẩn cấp**, rồi **chứng minh nó bằng eval thật** — và trung thực về chỗ nó còn yếu."*
> Ba trụ: **bền · an toàn · đo được**.

---

*Tài liệu kế hoạch thi công chi tiết: [PLAN.md](PLAN.md).*

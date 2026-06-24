# VinFast Callbot — Kế Hoạch Thi Công Chi Tiết (Bản Hợp Nhất)

> **Tài liệu này là *làm theo trình tự nào*.** Companion: [TECHSTACK.md](TECHSTACK.md) (*chọn công cụ gì & vì sao*).
> Task 3 · VinSmart Future AI Internship · 2 tuần · **Nhóm 2 người** · Mục tiêu: **ăn chắc job offer**.
> Hợp nhất từ 4 nguồn, đối chiếu trực tiếp `intern_task3_callbot_brief.pdf`.

---

## 0. Mục tiêu thật (đọc trước khi làm bất cứ gì)

Đây **không** phải bài tập để "hoàn thành". Đây là cuộc thi tuyển dụng. Người chấm trả lời một câu trong đầu: *"Hai đứa này có phải người mình muốn tuyển không?"*

Brief nói thẳng: **không** kỳ vọng production-ready; chấm **clear design thinking · smooth conversation · honest handling of edge cases**. → Thắng bằng **độ sâu + phán đoán**, không phải bề rộng feature.

> **⚠️ Cạm bẫy build-mode:** "làm tất tay" KHÔNG phải nhồi thêm feature. All-in đúng cách = **đào sâu vài thứ + một signature demo + eval thật**. Tuần 2 muốn xây thứ mới → hỏi: *"Cái này có vào signature demo hoặc eval không?"* Không → **cắt**.

**Trọng tâm đầu tư (theo số điểm):** Dialogue+Exception (25) + Eval (25) = **50/100** ≫ Pipeline (30) > Code Quality (20) > TTS (5).

---

## 1. Phân loại dự án (định hình mọi quyết định)

| Chiều | Phân loại | Hệ quả thiết kế |
|---|---|---|
| Interface | CLI (dev/eval) + Web demo (Gradio) — mic in, text/voice out | Engine phải **interface-agnostic** |
| Data flow | Mic → transcript → structured slots → JSON | Cần lớp normalize/validate giữa LLM và state |
| User model | Single caller, phiên 1-1 | Stateful trong 1 call, reset mỗi call |
| Lifecycle | Realtime turn-based + post-call batch | 2 track tách biệt: live vs hậu xử lý |
| Scale | Prototype/demo (không production) | Tối ưu cho **demo & eval reproducibility** |
| State | Session-scoped, in-memory per call | `SlotState` là single source of truth |

---

## 2. Nguyên tắc thi công

1. **Architecture trước code.** Architecture Doc là Gate 0; code không bắt đầu trước khi chốt thiết kế (tránh "doc hồi cố").
2. **Test viết song song, không để cuối.** Test-first định nghĩa "đúng nghĩa là gì".
3. **Text-first.** Lõi hội thoại chạy & test bằng text trước; voice I/O cắm sau → iterate nhanh, tách bug dialogue khỏi bug audio.
4. **Giữ repo sạch xuyên suốt.** `.env` + `.gitignore` từ ngày 1, không leak secret.
5. **Một sợi chuyện:** doc → demo → report đọc như **một dự án senior**, trụ **bền · an toàn · đo được** lặp ở mọi deliverable.

---

## 3. Kế hoạch 4 Phase / 2 Tuần (bám timeline brief)

### Phase 0 — Nền tảng & Kiến trúc · Ngày 1–3
**Mục tiêu:** dựng móng, spike rủi ro, viết Architecture Doc, chốt schema. **Hai người làm CÙNG NHAU.**

- [ ] Setup repo + venv + `requirements.txt` (pin dần) + `.env`/`.env.example` + `.gitignore`
- [ ] Cài Ollama + pull model (`qwen3:8b`, fallback `qwen2.5:7b-instruct`); spike Ollama trả tiếng Việt OK
- [ ] Spike faster-whisper: mic → transcript 1 câu tiếng Việt; **đo `asr_latency_ms` ngay** (rủi ro #1 là latency CPU)
- [ ] Định nghĩa **Pydantic schema** cho 5 category (field name đúng tuyệt đối theo brief — xem [TECHSTACK.md §8](TECHSTACK.md)) + `SlotState` + final JSON
- [ ] Viết **conversation corpus** nháp: kịch bản khách Việt **thật** (lộn xộn, cáu, nói tắt, đọc số bằng lời) cho cả 5 category
- [ ] Scaffold `DialogueEngine.process(text)->(reply, SlotState)` interface-agnostic + CLI rỗng
- [ ] **Architecture Doc (Deliverable #1)** nháp: pipeline, model choices, conversation flow, **8 chiến lược exception trên giấy**, decisions & trade-offs (kể cả phương án đã loại: LangGraph, edge-tts-primary, RAG)

**🚪 Gate 0:** Mic→transcript tiếng Việt OK · Ollama trả tiếng Việt OK · `asr_latency_ms` đo được · schema 5 category chốt · Architecture Doc nháp xong · corpus có ≥1 kịch bản/category.

---

### Phase 1 — Lõi Hội Thoại (text mode) · Ngày 4–7
**Mục tiêu:** 5 category chạy happy-path ở **text mode**, xuất đúng JSON. **Bắt đầu tách track.**

- [ ] Graph pipeline (LangGraph): Intent Classifier → Router → Entity Extractor → **SlotState update** → Next-field policy → Response Generator
- [ ] Slot-filling cho cả G_1..G_5 (hỏi field thiếu theo priority, từ state machine — không phải LLM)
- [ ] Module `normalization/` (số/biển/VIN/odo tiếng Việt nói) + **unit test** ngay
- [ ] Post-call track: summary + sentiment + emergency từ transcript
- [ ] **Song song:** khung **golden dataset** (scenario→expected) + harness pytest feed text + ≥1 metric tự động (slot F1)

**🚪 Gate 1:** Cả 5 category hoàn tất 1 call happy-path text mode · JSON cuối đúng schema · `normalization` test pass · ≥1 golden case/category chạy trong harness.

---

### Phase 2 — Exception Handling & Voice I/O · Ngày 8–10
**Mục tiêu:** 8 exception demo được; nối mic live; TTS (optional). **Track A/B chạy song song.**

- [ ] Code **8 exception** trên nền graph (LangGraph) (cơ chế ở [TECHSTACK.md §9](TECHSTACK.md)):
  - #1 missing (không re-ask) · #2 correction (update không lặp) · #3 ambiguous (1 câu hỏi rõ) · #4 out-of-scope (redirect/transfer) · #5 garbled (xác nhận phone/plate) · #6 emergency (hotline ngay, bỏ field thấp) · #7 stuck 2+ (đề nghị human) · #8 hangup (partial JSON)
- [ ] Nối **VAD + mic live** vào engine qua CLI (đo `asr/llm/tts_latency_ms` per turn)
- [ ] **TTS Piper** (local) → bot nói tiếng Việt; giữ interface `tts/base.py` (swap edge-tts cho video sau)
- [ ] **Gradio UI** cho demo (mic-in + panel JSON live)
- [ ] Viết test cho ≥3 exception scenario (đếm vào minimum eval)

**🚪 Gate 2:** 8 exception demo được bằng kịch bản · mic live → ASR → engine → response chạy end-to-end · TTS phát tiếng Việt · Gradio chạy.

---

### Phase 3 — Evaluation, Signature Demo & Báo Cáo · Ngày 11–14
**Mục tiêu:** hoàn tất eval + report + reproducibility + video. **Hai người làm CÙNG NHAU.**

- [ ] **Golden dataset đầy đủ:** **≥2 scenario/category (≥10)** + **≥3 exception scenario** (vượt minimum brief)
- [ ] **Metric tự động:** routing confusion matrix + slot F1 + emergency **recall** (adversarial) + sentiment accuracy + **WER (jiwer)** + LLM-as-judge naturalness + **latency p50/p95 breakdown ASR/LLM/TTS**
- [ ] **Ablation study:** có/không state-machine · có/không tune recall · Qwen vs Việt-tuned · laptop medium vs GPU large WER
- [ ] Chạy full suite, thu kết quả
- [ ] **Evaluation Report (Deliverable #4):** mọi metric + **failure analysis (sai gì + VÌ SAO + hướng sửa)** + latency + đánh giá hạn chế trung thực
- [ ] **Signature demo video** (xem §5) — quay bằng Gradio
- [ ] `requirements.txt` pin `==` + `.env.example` + README; **quét repo tránh leak secret**
- [ ] Finalize Architecture Doc (đồng bộ với code thực tế)

**🚪 Gate 3 (nghiệm thu):** đủ **5 deliverable** · 5 category + ≥3 exception phủ trong eval · latency report có · failure analysis trung thực · `pip install -r` chạy được trên máy sạch · không secret trong code · signature demo quay xong.

---

## 4. Phân chia 2 người

Dùng `DialogueEngine.process(text)->(reply, SlotState)` làm **contract** đường nối. Hai track song song, ráp qua interface sạch.

| | **Track A ** (Hiệp) | **Track B ** (Phương) |
|---|---|---|
| Sở hữu | DialogueEngine (LangGraph), 8 exception, **eval framework + report** | ASR/VAD/TTS + mic loop, **normalization số tiếng Việt**, domain corpus, Gradio + video |



**Đường nối (lock ở Phase 0, làm CÙNG trước khi tách):**
1. Contract `DialogueEngine.process(text) → (response, SlotState)`
2. Schema 5 category + **conversation corpus**

**Nhịp đội hình:** Phase 0 *cùng nhau* → Phase 1–2 *tách* → Phase 3 *cùng nhau* (ráp + signature demo + report). **Hai người không bao giờ block nhau quá nửa ngày.**

### 4.1 Bản đồ sở hữu file (mỗi file 1 chủ → không sửa chồng)

> Nguyên tắc vàng: **chia việc tới cấp FILE, không phải cấp mảng.** Xung đột git xảy ra ở cấp file. Người kia chỉ *đọc* qua interface, không sửa file của chủ.

**Track A (Hiệp) — "Bộ não":**
`dialogue/` (engine, graph, nodes, state, categories, values, intent, extraction, exceptions, response, post_call) · `llm/` (ollama_client, prompts) · `eval/` (run_eval, metrics, report_template) · `tests/` (test_dialogue_state, test_field_extraction, test_exception_handling, test_final_output_schema) · `docs/EVALUATION_REPORT.md`

**Track B (Phương) — "Giác quan & Giọng":**
`audio/` (recorder, vad, playback) · `asr/` (faster_whisper_asr) · `tts/` (piper_tts, edge_tts, vixtts) · `normalization/` (vietnamese_numbers) · `main.py` + Gradio UI · `tests/test_normalization.py`

**File DÙNG CHUNG (dễ đụng → phải có luật):**

| File | Chủ chính | Luật chống xung đột |
|---|---|---|
| `models/schemas.py` | A | **Contract** — freeze ở Phase 0. Đổi field/signature phải sync 2 phút + B pull ngay. |
| `dialogue/engine.py` interface, `asr/base.py`, `tts/base.py`, `llm/base.py` | A định nghĩa | **Freeze ở Phase 0.** Impl sau interface đổi tự do; **signature** đổi phải báo. |
| `pipeline.py` | B (vì là wiring audio→engine→tts) | Phase 1 **không ai đụng**; Phase 2 chỉ B sửa, A review. |
| `config.py` | A | Append-only, file nhỏ. |
| `requirements.txt` | Cả hai | **Append-only, giữ thứ tự alphabet.** Conflict → lấy **cả hai dòng** (union), không bao giờ xóa dòng người kia. |
| `scenarios/` (corpus + audio) | Đồng sở hữu | **A** định nghĩa `expected output`; **B** viết `user input` tiếng Việt thật → sửa phần khác nhau của cùng file, conflict thấp. |
| `README.md` | A dựng khung | Mỗi người append **section riêng** ở Phase 3. |
| `docs/ARCHITECTURE.md` | Đồng tác giả | Chia theo **section**: A viết dialogue/exception/eval; B viết ASR/TTS/normalization/pipeline. Sửa section khác nhau → conflict thấp. |

### 4.2 Git & kế hoạch push code (chống trùng)

1. **`main` luôn xanh (protected).** Không ai push thẳng vào `main`.
2. **Branch theo task, ngắn hạn:** `a/<task>` (Hiệp), `b/<task>` (Phương). VD `a/slot-fsm`, `b/vad-mic`. Một branch = một task nhỏ.
3. **Mỗi merge = 1 PR + review chéo 2 phút → squash merge** (history sạch, cộng điểm Code Quality 20đ).
4. **Đầu mỗi buổi: `git pull --rebase origin main`** trước khi code → luôn đứng trên bản mới nhất (hiện thực hóa luật "không block nhau quá nửa ngày").
5. **PR nhỏ, không để mở quá 1 ngày.** Merge ≥1 lần/ngày mỗi người. Cuối ngày cả hai đứng trên `main` xanh.
6. **Contract freeze (cơ chế chống xung đột quan trọng nhất):** Phase 0 hai người **pair** viết `schemas.py` + các `base.py` interface → merge vào `main` **TRƯỚC TIÊN**. Sau đó interface "đóng băng"; đổi signature phải sync + cả hai pull ngay.
7. **`.gitignore` từ ngày 1:** `.venv/`, `*.onnx`/model weights, `scenarios/audio/*.wav` (file nặng → để Git LFS hoặc ngoài repo), `__pycache__/`, `.env`, audio output. Tránh commit file nặng/nhị phân gây conflict & phình repo.

### 4.3 Nhịp đồng bộ & luật tránh xung đột

- **Standup 10 phút mỗi sáng:** mỗi người nói *hôm nay đụng file nào* → bắt trùng **trước khi** nó xảy ra.
- **Luật "nói trước khi đụng file chung":** muốn sửa file của track kia → nhắn 1 câu, không tự ý sửa.
- **Interface đóng băng, implementation tự do:** đây là thứ cho phép 2 người code song song mà không chờ nhau — A code `engine.py` với ASR giả (text), B code `asr/` trả text vào cùng interface; ráp ở Phase 2 là khớp.
- **Integration owner:** `pipeline.py` (chỗ ráp 2 track) do **B** sở hữu ở Phase 2, A review — tránh hai người cùng sửa chỗ ráp.

> **Lưu ý:** Phân công tới cấp **task cụ thể theo ngày** (TASK-001…) là **Task Graph** — artifact bước sau Blueprint. §4.1–4.3 ở đây đã đủ để hai người **push song song không đụng nhau**; Task Graph sẽ thêm *thứ tự* và *ai-làm-gì-ngày-nào*.

---

## 5. Phần cộng thêm "thắng job offer" (so với bản chỉ "điểm cao")

### 5.1 Một "signature call" mở đầu video (gói nhiều khác biệt trong ~90 giây)
> Khách hoảng loạn: *"Xe tôi tông dải phân cách trên cao tốc Hà Nội–Hải Phòng!"*
> Bot: (a) bắt **emergency ngay** → (b) trấn an + cấp **hotline cứu hộ trước** → (c) chỉ thu field tối thiểu, **bỏ qua odo** → (d) khách đọc sai SĐT rồi sửa → **update không re-ask** → (e) biển số đọc lộn xộn → **xác nhận lại** → (f) xuất JSON `emergency=yes, sentiment=urgent`.

Một call chứng minh: emergency-priority + correction + garbled-confirm + no-re-ask + domain thật + chuẩn hóa số. **Người chấm sẽ nhớ.**

### 5.2 Một ca emergency "giọng bình tĩnh" (chứng minh recall thật)
> *"Anh ơi xe em đỗ giữa đường không nổ được, trời tối quá..."*

Nghe thường nhưng là ca mắc kẹt nguy hiểm. Bot bắt được = emergency detection **không phải match keyword** mà tune recall có chủ đích. Bot nhóm khác trượt ca này.

### 5.3 Ablation study trong eval (tín hiệu nghiên cứu senior)
Đo delta thật của các quyết định (§3 Phase 3) → eval thành **thí nghiệm có kiểm soát**, không phải báo cáo điểm.

### 5.4 Một sợi chuyện xuyên suốt
Doc → demo → report đọc như **một dự án senior**. Sợi chỉ: **bền · an toàn · đo được**.

---

## 6. Map Deliverable → Phase → Điểm (5 deliverable theo brief)

| # | Deliverable | Hoàn tất ở | Ô điểm |
|---|---|---|---|
| 1 | Architecture Doc | Phase 0 (nháp) → 3 (final) | Dialogue/Exception (25) + Code Quality (20) |
| 2 | Working Bot (5 cat + JSON + mic) | Phase 1→2 | Pipeline (30) + Dialogue (25) + TTS (+5) |
| 3 | Eval Framework + scenarios | Phase 1 (khung) → 3 (đủ) | Evaluation (25) |
| 4 | Eval Report | Phase 3 | Evaluation (25) |
| 5 | `requirements.txt` + repro | Giữ sạch xuyên suốt → 3 | Code Quality (20) |

> **Minimum eval của brief — kế hoạch vượt rõ ràng:** ≥2 scenario × 5 cat (10) ✓ → ta làm ≥10 · ≥3 exception scenario ✓ → ta làm ≥3 + adversarial · ≥1 automated metric ✓ → ta có slot F1 + WER · failure cases trung thực ✓ · latency per turn ✓ → p50/p95 breakdown.

---

## 7. Risk Register (đầy đủ)

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Latency ASR+LLM trên CPU quá cao cho "live" | **Cao** | medium/small int8 + Qwen Q4; **đo sớm Gate 0**; hạ size hoặc iGPU (llama.cpp Vulkan) nếu cần |
| LLM trả JSON sai schema | TB | Pydantic validate + retry + Ollama JSON mode |
| Re-ask field đã confirm (mất điểm exception) | Cao | **Đã giải quyết bằng kiến trúc state-machine (LangGraph)** |
| TTS edge-tts fail khi grader repro offline | TB | **Piper local làm primary**; edge-tts chỉ swap cho video |
| Leak secret khi push | TB | `.env` + `.gitignore` từ ngày 1 + quét repo trước nộp (Gate 3) |
| Sa đà TTS/UI, bỏ bê eval | **Cao** | Eval 25đ ≫ TTS 5đ; bám map §6; eval viết từ Phase 1 |
| Build trước, doc sau | TB | Architecture Doc là Gate 0 |
| PhoWhisper cần convert CT2 | Thấp | Mặc định faster-whisper chạy ngay; PhoWhisper chỉ là bản nâng cấp có-WER-đỡ-lưng |
| Hai track lệch contract | TB | Lock `process()` signature + schema ở Phase 0, không đổi giữa chừng |

---

## 8. Kỷ luật (ghim lại vì all-in)

- **TTS/UI chỉ làm SAU KHI lõi vững.** TTS 5đ; bot vỡ khi khách nói lộn xộn = phản tác dụng.
- **Đừng giấu failure.** Phơi lỗi + root cause = tự tin chuyên môn.
- **G_2/G_4: chính sách bảo hành tĩnh nhưng THẬT** (term VinFast thật, cấu trúc rõ). **KHÔNG RAG** — dồn thời gian cho eval.
- **Đừng over-engineer.** Graph LangGraph tối giản (≤7 node, không nhồi node thừa); static policy > RAG. Mỗi dòng code phải truy được về yêu cầu brief.
- **Mọi thứ không phục vụ 3 trụ (bền·an toàn·đo được) hoặc signature demo = nhiễu → cắt.**

---

## 9. Vì sao kế hoạch này thắng các nhóm khác

| Nhóm khác | Nhóm ta |
|---|---|
| Build trước, doc hồi cố | Architecture Doc là Gate 0, decisions có trade-off |
| Eval dừng ở "87% accuracy" | Eval là tác phẩm: confusion matrix + slot F1 + WER + latency p50/p95 + ablation + failure analysis |
| 5 demo nhạt | 1 signature call gói nhiều khác biệt + 1 ca emergency giọng bình tĩnh |
| LLM tự nhớ state → vỡ | State machine xác định (LangGraph), partial JSON sạch khi hangup |
| Test bằng text "sách giáo khoa" | Corpus khách Việt thật + normalization số/biển/VIN có test |
| TTS rớt khi repro offline | Piper local-first, interface pluggable, nói rõ trade-off |
| Hai nửa dán lại | Một sợi chuyện senior: bền · an toàn · đo được |

---

*Tech stack & lý do chọn chi tiết: [TECHSTACK.md](TECHSTACK.md).*
*Bước tiếp theo: chốt kế hoạch này → dựng Blueprint chi tiết (từng node graph, schema đầy đủ, contract 2 track) → cắt thành Task Graph (TASK-001…) chia theo Track A / Track B.*

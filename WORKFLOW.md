# WORKFLOW — Quy trình phối hợp 2 người

> File tự-chứa cho **Hiệp (Track A)** và **Phương (Track B)**: mở ra làm theo được ngay, không cần tra chéo.
> Nguồn luật: [PLAN.md §4.1–4.3](PLAN.md) · [TASKGRAPH.md §1,§3](TASKGRAPH.md) · [BLUEPRINT.md §3](BLUEPRINT.md). File này chỉ *gom lại*, không thêm luật mới.

---

## 0. Nguyên lý gốc (mọi luật khác suy ra từ đây)

> **Conflict không được *giải quyết*, nó được *thiết kế để không xảy ra*** — bằng 3 lớp:
> 1. **Mỗi file một chủ.**
> 2. **Freeze file dùng chung TRƯỚC khi tách.**
> 3. **Luôn đứng trên `main` mới nhất trước khi code.**
>
> Nếu đang phải giải một merge-conflict **to ở file logic** (không phải `requirements.txt`) → **một trong ba lớp đã bị phá**. DỪNG lại, soát ai đã đụng nhầm file, đừng cố merge tay.

---

## 1. Vai trò & sở hữu file

**Luật vàng:** chỉ sửa file **mình sở hữu**. Cần đụng file người kia → **nhắn 1 câu trước**, không tự sửa.

| Vùng | Chủ | Nội dung |
|---|---|---|
| **Track A — Hiệp ("Bộ não")** | A | `dialogue/` · `llm/` · `eval/` · `tests/` (dialogue: state/extraction/exception/final_output) · `docs/EVALUATION_REPORT.md` |
| **Track B — Phương ("Giác quan & Giọng")** | B | `audio/` · `asr/` · `tts/` · `normalization/` · `main.py` + Gradio · `tests/test_normalization.py` |

**File dùng chung (có chủ rõ — xem §5 cho luật):**

| File | Chủ | Ghi chú |
|---|---|---|
| `models/schemas.py` | **A định nghĩa** | Contract — freeze ở Wave 0 |
| `dialogue/engine.py` interface · `asr/base.py` · `tts/base.py` · `llm/base.py` · `normalization/base.py` | **A** | Freeze ở Wave 0 |
| `pipeline.py` | **B** | A review |
| `requirements.txt` | **cả hai** | Append-only, union |
| `scenarios/*.json` | **B** input / **A** expected | Sửa phần khác nhau |
| `config.py` | **A** | Append-only |
| `README.md` · `docs/ARCHITECTURE.md` | **đồng tác giả** | Chia theo section (A: dialogue/exception/eval; B: ASR/TTS/normalization/pipeline) |

---

## 2. Wave 0 — TUẦN TỰ (ngoại lệ quan trọng nhất)

`TASK-001 scaffold → TASK-002 schemas → TASK-003 interfaces` — **KHÔNG song song**, vì cả ba đụng file dùng chung (`schemas.py` + các `base.py`).

**Việc TRƯỚC `TASK-001` (làm một lần):**
- Tạo repo chung + **cấp quyền collaborator cho Phương**.
- Bật **branch protection cho `main`** (không push thẳng, merge qua PR).
- Cả hai `git clone` về máy.

**Cơ chế chạy Wave 0:** một người *drive*, một người *review*, **một PR cho mỗi task**, **cả hai `pull` sau mỗi merge** rồi mới sang task kế:

```bash
# Ví dụ TASK-002 (schemas) — A drive
git checkout main && git pull --rebase origin main
git checkout -b w0/schemas
#   ... viết models/schemas.py ...
git add models/schemas.py && git commit -m "add pydantic schemas (5 categories + slot/nlu/final)"
git push -u origin w0/schemas
#   → mở PR, Phương review 2 phút → squash merge vào main
# SAU KHI MERGE: CẢ HAI cùng pull rồi mới làm task kế
git checkout main && git pull --rebase origin main
```

> **Chốt sau `TASK-003`:** `models/schemas.py` + tất cả `*/base.py` **ĐÓNG BĂNG**. Đây là điều kiện cho phép Wave 1+ chạy song song an toàn. Đổi sau khi freeze → §5.

---

## 3. Wave 1–2 — SONG SONG (vòng lặp chuẩn mỗi task)

Sau khi contract freeze, A và B chạy độc lập. Mỗi task lặp **5 bước**:

```bash
# 1) Chống conflict số 1: luôn đứng trên main mới nhất
git checkout main && git pull --rebase origin main

# 2) Tạo branch theo task  (A: a/<task>  ·  B: b/<task>)
git checkout -b a/slot-graph        # Hiệp ví dụ
#   hoặc: git checkout -b b/normalization   # Phương ví dụ

# 3) Code CHỈ trong file mình sở hữu (§1)

# 4) PR nhỏ → review chéo 2 phút → squash merge vào main
git add -A && git commit -m "implement slot-filling graph (happy path)"
git push -u origin a/slot-graph
#   → mở PR → người kia review → squash merge

# 5) Lặp lại cho task kế (quay về bước 1)
```

**Vì sao song song an toàn:** A đụng `dialogue/ llm/ eval/`, B đụng `audio/ asr/ tts/ normalization/` → **không bao giờ chạm cùng file** → merge thứ tự nào cũng được, không conflict.

> Phụ thuộc *thứ tự* (ai làm gì trước) xem [TASKGRAPH.md §1 (dependency graph) + §3 (lịch)](TASKGRAPH.md). Critical path: `002→A12→A13→A20→A21→A30→A32`. B không bị A block (điểm chờ duy nhất là interface, đã có từ Wave 0).

---

## 4. Điểm ráp `pipeline.py` (Wave 2)

`pipeline.py` là **file DUY NHẤT cả hai cùng cần** (nối `audio→ASR→engine→TTS`).

- **Luật:** **B sở hữu, A review.**
- **Thời điểm:** B **không** viết `pipeline.py` cho tới khi **`TASK-A13` (engine) đã merge `main`** → điểm ráp luôn xảy ra **SAU** khi cả hai phía đã ổn định (engine của A + ASR/VAD/TTS của B đều đã trên `main`).
- Seam để ráp (không đổi): `DialogueEngine.process(text) → TurnResult(reply, state, done)` ([BLUEPRINT.md §3](BLUEPRINT.md)).

---

## 5. Luật 4 file dùng chung

| File | Luật |
|---|---|
| `schemas.py` / `*/base.py` | **Freeze ở Wave 0.** Đổi signature/field → **nhắn nhau + CẢ HAI `pull` ngay**. Impl phía sau interface đổi tự do. |
| `pipeline.py` | **Chỉ B đẩy, A review.** Không ai khác commit. |
| `requirements.txt` | **Append-only, sắp alphabet.** Conflict → **lấy CẢ HAI dòng (union)**, KHÔNG xóa dòng người kia. |
| `scenarios/*.json` | **B viết `user input`, A viết `expected`** → hai người sửa phần khác nhau của file → conflict trivial (gộp tay 10 giây). |

Ví dụ resolve `requirements.txt` (union):

```bash
# Khi git báo conflict ở requirements.txt:
# <<<<<<< HEAD            (dòng của bạn)
# faster-whisper==1.0.3
# =======
# silero-vad==5.1         (dòng người kia)
# >>>>>>> origin/main
# → GIỮ CẢ HAI, xóa dấu <<< === >>>, sắp alphabet:
git add requirements.txt && git rebase --continue
```

---

## 6. Nhịp độ giữ conflict luôn nhỏ

- **Merge ≥ 1 lần/ngày mỗi người.** PR **không mở quá 1 ngày** — branch sống lâu = `main` trôi xa = conflict to.
- **Standup 10 phút mỗi sáng:** mỗi người nói *"hôm nay tôi đụng file nào"* → bắt trùng **trước khi** thành conflict.
- **Cuối ngày cả hai đứng trên `main` xanh** (đã pull, build/test pass).

---

## 7. Khi LỠ có conflict

| Tình huống | Xử lý |
|---|---|
| `requirements.txt` | **Union** — giữ cả hai dòng, sắp alphabet. Bình thường, không phải sự cố. |
| **File logic** (dialogue/audio/…) | **DỪNG.** Đây là tín hiệu 1 trong 3 lớp ở §0 đã bị phá. Xác định **ai sở hữu file** (§1) → người **không sở hữu** revert phần mình → nhắn nhau. **KHÔNG** tự ý overwrite. |
| Tie-break | **Chủ sở hữu file là người đúng.** |

---

## 8. `.gitignore` + an toàn secret

`.gitignore` (có từ `TASK-001`) phải chặn:

```gitignore
.venv/
__pycache__/
.env
*.onnx
scenarios/audio/*.wav      # file nặng → Git LFS hoặc để ngoài repo
```

> **KHÔNG commit `.env`** (key/token chỉ qua `.env`). Quét repo trước khi nộp (TASK-S31).

---

## Dán-lên-tường (TL;DR)

> **Wave 0 tuần tự** (1 PR/task, cùng `pull` sau merge) → **freeze contract** (`schemas.py` + `*/base.py`) → **Wave 1+ song song** (branch riêng `a/…` `b/…`, `git pull --rebase` TRƯỚC mỗi task, PR nhỏ merge mỗi ngày) → **`pipeline.py` ráp sau cùng, do B sở hữu (A review)**.
>
> Mỗi file một chủ · đụng file người kia thì nhắn trước · conflict file logic = dừng-soát, không merge tay.

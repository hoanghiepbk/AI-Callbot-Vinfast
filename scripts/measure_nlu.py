"""Throwaway spike (M2): measure Qwen NLU JSON/signal stability on dirty Vietnamese.

NOT product code — a measurement harness. Run after Ollama is up + model pulled:

    ollama serve            # (or the desktop app)
    ollama pull qwen3:8b
    OLLAMA_MODEL=qwen3:8b python scripts/measure_nlu.py

Reports, over RUNS attempts/case: % JSON-parsable, % schema-valid, % category-correct,
% signals-correct, emergency-recall, per-case category stability, and a list of wrong cases.
All test phone/plate values are FAKE.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import ollama
from pydantic import ValidationError

# Import the frozen contract just for validation (read-only use).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from callbot.models.schemas import NLUResult  # noqa: E402

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
RUNS = 3

SYSTEM = """Bạn là bộ NLU cho callbot chăm sóc khách hàng VinFast.
Với MỘT câu khách nói, trả về JSON đúng schema NLUResult. CHỈ trả JSON, không giải thích.

category (chọn 1, hoặc null nếu chưa đủ rõ):
  G_1 Cứu hộ ô tô (xe hỏng/tai nạn/kẹt đường cần cứu hộ, cẩu kéo)
  G_2 Bảo hành & sửa chữa ô tô
  G_3 Đơn hàng (trạng thái đơn, đặt cọc, đại lý)
  G_4 Xe máy điện - bảo hành
  G_5 Hỗ trợ kỹ thuật từ xa (lỗi phần mềm / app / màn hình)

signals:
  emergency=true nếu nguy hiểm tính mạng / kẹt giữa đường hoặc cao tốc / tai nạn / cháy
    (BẮT cả khi khách nói giọng bình tĩnh).
  out_of_scope=true nếu hỏi ngoài phạm vi CSKH xe (giờ mở cửa, thời tiết...).
  correction=true nếu khách sửa lại thông tin vừa nói.
  hangup=true nếu khách muốn dừng/cúp máy ("thôi", "để sau").

extracted_fields: chỉ field khách VỪA cung cấp trong câu này, tên field đúng brief
  (full_name, phone, license_plate_vin, current_location, vehicle_model, vehicle_line, ...)."""

FEWSHOT = [
    {
        "role": "user",
        "content": "xe em chết máy giữa cao tốc Hà Nội Hải Phòng không nổ được",
    },
    {
        "role": "assistant",
        "content": json.dumps(
            {
                "category": "G_1",
                "extracted_fields": {"current_location": "cao tốc Hà Nội Hải Phòng"},
                "corrected_fields": {},
                "signals": {
                    "emergency": True,
                    "out_of_scope": False,
                    "correction": False,
                    "hangup": False,
                },
            },
            ensure_ascii=False,
        ),
    },
]

# Each case: text + expected category (or None) + expected signals it MUST get right.
CASES: list[dict[str, object]] = [
    {
        "text": "số em là không chín ba tám hai một không năm bảy sáu",
        "cat": "G_3",
        "emergency": False,
    },
    {
        "text": "à nhầm, đuôi là bảy tám chứ không phải sáu tám",
        "cat": None,
        "emergency": False,
        "correction": True,
    },
    {"text": "xe chết máy giữa đường tối quá không thấy gì", "cat": "G_1", "emergency": True},
    {"text": "anh ơi xe em đỗ giữa cao tốc không nổ được", "cat": "G_1", "emergency": True},
    {"text": "cho hỏi về cái xe", "cat": None, "emergency": False},
    {"text": "mấy giờ shop đóng cửa vậy em", "cat": None, "emergency": False, "out_of_scope": True},
    {"text": "xe vừa tông vào dải phân cách trên quốc lộ một", "cat": "G_1", "emergency": True},
    {
        "text": "em muốn hỏi đơn đặt cọc vinfast vf ba của em tới đâu rồi",
        "cat": "G_3",
        "emergency": False,
    },
    {"text": "màn hình giải trí cứ tự khởi động lại hoài", "cat": "G_5", "emergency": False},
    {"text": "xe máy điện klara của em hết bảo hành chưa nhỉ", "cat": "G_4", "emergency": False},
    {"text": "ô tô em đến kỳ bảo dưỡng rồi muốn đặt lịch", "cat": "G_2", "emergency": False},
    {
        "text": "thôi để lúc khác em gọi lại sau nhé",
        "cat": None,
        "emergency": False,
        "hangup": True,
    },
    {"text": "biển số xe là ba mươi a năm sáu bảy chấm tám chín", "cat": None, "emergency": False},
    {"text": "xe bốc khói ở nắp ca pô em sợ quá", "cat": "G_1", "emergency": True},
    {"text": "app my vinfast của em đăng nhập không được", "cat": "G_5", "emergency": False},
    {
        "text": "em tên là nguyễn văn an số điện thoại không chín không",
        "cat": None,
        "emergency": False,
    },
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    client = ollama.Client(host=HOST)
    try:
        client.list()
    except Exception as exc:  # noqa: BLE001 - spike: any failure means "no server"
        print(f"[BLOCKED] Ollama not reachable at {HOST}: {exc}")
        print("Start Ollama and pull the model, then re-run. See README Setup.")
        return 1

    schema = NLUResult.model_json_schema()
    n_attempts = 0
    n_parse = n_schema = n_cat = n_sig = 0
    emg_total = emg_hit = 0
    wrong: list[str] = []
    stability: list[str] = []

    for case in CASES:
        text = str(case["text"])
        cats_seen: list[str] = []
        for run in range(RUNS):
            n_attempts += 1
            try:
                resp = client.chat(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        *FEWSHOT,
                        {"role": "user", "content": text},
                    ],
                    format=schema,
                    think=False,  # A10 fix: thinking OFF for structured (kills empty output)
                    options={"temperature": 0},
                    keep_alive="10m",
                )
                raw = resp["message"]["content"]
            except Exception as exc:  # noqa: BLE001
                wrong.append(f"[call-fail] {text!r}: {exc}")
                continue

            try:
                data = json.loads(raw)
                n_parse += 1
            except json.JSONDecodeError:
                wrong.append(f"[no-json] {text!r} -> {raw[:80]!r}")
                continue

            try:
                nlu = NLUResult.model_validate(data)
                n_schema += 1
            except ValidationError as exc:
                wrong.append(f"[bad-schema] {text!r}: {exc.error_count()} errors")
                continue

            cats_seen.append(str(nlu.category))
            if nlu.category == case["cat"]:
                n_cat += 1
            else:
                wrong.append(f"[cat] {text!r}: got {nlu.category} exp {case['cat']}")

            exp_sig = {
                k: case[k]
                for k in ("emergency", "out_of_scope", "correction", "hangup")
                if k in case
            }
            got_sig = nlu.signals.model_dump()
            if all(got_sig[k] == v for k, v in exp_sig.items()):
                n_sig += 1
            else:
                bad = {k: (got_sig[k], v) for k, v in exp_sig.items() if got_sig[k] != v}
                wrong.append(f"[sig] {text!r}: {bad}")

            if case.get("emergency") is True:
                emg_total += 1
                if got_sig["emergency"] is True:
                    emg_hit += 1

        if cats_seen:
            stability.append(
                f"{'STABLE' if len(set(cats_seen)) == 1 else 'FLAKY '} {cats_seen} | {text[:40]}"
            )

    def pct(n: int, d: int) -> str:
        return f"{100 * n / d:5.1f}%  ({n}/{d})" if d else "n/a"

    print(f"\n=== M2 NLU STABILITY · model={MODEL} · {RUNS} runs/case · {len(CASES)} cases ===")
    print(f"JSON parsable   : {pct(n_parse, n_attempts)}")
    print(f"Schema valid    : {pct(n_schema, n_attempts)}")
    print(f"Category correct: {pct(n_cat, n_schema)}")
    print(f"Signals correct : {pct(n_sig, n_schema)}")
    print(f"EMERGENCY recall: {pct(emg_hit, emg_total)}   <-- safety metric")
    print("\n--- category stability across runs ---")
    for line in stability:
        print(" ", line)
    print(f"\n--- wrong cases ({len(wrong)}) ---")
    for line in wrong:
        print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

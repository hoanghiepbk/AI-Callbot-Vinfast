"""NLU node: a single user utterance -> NLUResult (TASK-A12).

The node calls the LLM through the frozen `LLM` Protocol (OllamaClient). Because we
pass a json_schema, OllamaClient applies think=False automatically (the A10 fix that
killed empty structured output).

Few-shot lives INSIDE the system prompt, not as separate chat turns: the
`LLM.complete(system, user, json_schema)` contract only takes two strings. The shots
are balanced on purpose — M2 showed that a single G_1-emergency example made the model
over-fire `G_1 + emergency=true` on bare identifier utterances (phone/plate/name).
So we add identity-only, correction, out-of-scope and ambiguous examples that all
keep emergency=false / category=null. All numbers/plates in the examples are FAKE.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from callbot.llm.base import LLM
from callbot.models.schemas import Category, NLUResult

_SCHEMA = NLUResult.model_json_schema()

# Rules half of the prompt (role + category map + signal discipline). Kept separate
# from the few-shot, which is assembled from dicts below to keep source lines short.
_PROMPT_HEAD = """Bạn là bộ NLU cho callbot chăm sóc khách hàng VinFast.
Với MỘT câu khách nói, trả về JSON đúng schema NLUResult. CHỈ trả JSON, không giải thích.

category (chọn 1, hoặc null nếu chưa đủ rõ):
  G_1 Cứu hộ ô tô (xe hỏng/tai nạn/kẹt đường cần cứu hộ, cẩu kéo)
  G_2 Bảo hành & sửa chữa ô tô
  G_3 Đơn hàng (trạng thái đơn, đặt cọc, đại lý)
  G_4 Xe máy điện - bảo hành
  G_5 Hỗ trợ kỹ thuật từ xa (lỗi phần mềm / app / màn hình)

signals:
  emergency=true CHỈ khi có nguy hiểm thật: tai nạn / cháy / kẹt giữa đường hoặc cao tốc /
    xe chết máy không di chuyển được ở nơi nguy hiểm (BẮT cả khi khách giọng bình tĩnh).
    KHÔNG bật emergency cho câu chỉ đọc số điện thoại / biển số / tên / hỏi thông thường.
  out_of_scope=true nếu hỏi ngoài phạm vi CSKH xe (giờ mở cửa, thời tiết...).
  correction=true nếu khách sửa lại thông tin vừa nói.
  hangup=true nếu khách muốn dừng/cúp máy ("thôi", "để sau").

extracted_fields: chỉ field khách VỪA cung cấp trong câu này, tên field đúng brief
  (full_name, phone, license_plate_vin, current_location, vehicle_model, vehicle_line, ...).
KHÔNG đoán category khi câu mơ hồ -> để null."""


def _shot(
    text: str,
    category: str | None = None,
    extracted: dict[str, str] | None = None,
    corrected: dict[str, str] | None = None,
    emergency: bool = False,
    out_of_scope: bool = False,
    correction: bool = False,
    hangup: bool = False,
) -> str:
    """Render one labelled example as `Khách: "..." / JSON: {...}` text."""
    payload = {
        "category": category,
        "extracted_fields": extracted or {},
        "corrected_fields": corrected or {},
        "signals": {
            "emergency": emergency,
            "out_of_scope": out_of_scope,
            "correction": correction,
            "hangup": hangup,
        },
    }
    return f'Khách: "{text}"\nJSON: {json.dumps(payload, ensure_ascii=False)}'


# Balanced few-shot. FAKE numbers/plates only. Identity-only + ambiguous examples are
# the fix for the M2 over-firing bug; the lone emergency example keeps recall.
_FEWSHOT = "\n".join(
    [
        _shot(
            "số em là không chín không một hai ba bốn năm sáu bảy",
            extracted={"phone": "không chín không một hai ba bốn năm sáu bảy"},
        ),
        _shot(
            "biển số xe là ba mươi a chấm một hai ba bốn",
            extracted={"license_plate_vin": "ba mươi a chấm một hai ba bốn"},
        ),
        _shot("em tên là trần văn hùng", extracted={"full_name": "trần văn hùng"}),
        _shot(
            "xe em vừa tông vào đuôi xe tải trên cao tốc",
            category="G_1",
            extracted={"current_location": "cao tốc"},
            emergency=True,
        ),
        _shot(
            "à nhầm, đuôi số là bảy tám chứ không phải sáu tám",
            corrected={"phone": "bảy tám"},
            correction=True,
        ),
        _shot("mấy giờ shop đóng cửa vậy em", out_of_scope=True),
        _shot("cho hỏi về cái xe"),  # ambiguous -> null, no guess
        _shot(
            "em hỏi đơn đặt cọc vinfast vf ba của em tới đâu rồi",
            category="G_3",
            extracted={"vehicle_model": "vf ba"},
        ),
        _shot("màn hình giải trí cứ tự khởi động lại hoài", category="G_5"),
    ]
)

_BASE_SYSTEM = (
    f"{_PROMPT_HEAD}\n\nVÍ DỤ (học theo — emergency chỉ bật khi NGUY HIỂM thật):\n{_FEWSHOT}"
)


def build_system(current_category: Category | None = None) -> str:
    """System prompt for the NLU call; pins the active flow when a category is locked."""
    if current_category is None:
        return _BASE_SYSTEM
    # Once a category is locked, keep it unless the utterance is clearly a new intent.
    return (
        f"{_BASE_SYSTEM}\n\nNGỮ CẢNH: khách đang trong luồng {current_category}. "
        f"Giữ category {current_category} trừ khi câu rõ ràng là intent khác."
    )


def nlu_node(llm: LLM, user_text: str, current_category: Category | None = None) -> NLUResult:
    """Classify one utterance into NLUResult. Never raises — bad output -> safe empty."""
    result = llm.complete(build_system(current_category), user_text, _SCHEMA)
    return _parse(result.text)


def _parse(text: str) -> NLUResult:
    # A10 already retried empties; an empty/garbage string here -> safe default
    # (category=None, all signals False) so the FSM just asks a clarifying question.
    try:
        return NLUResult.model_validate_json(text)
    except ValidationError:
        return NLUResult()

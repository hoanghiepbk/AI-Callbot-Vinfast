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

extracted_fields: chỉ field khách VỪA cung cấp trong câu này. BẮT BUỘC dùng ĐÚNG tên field
dưới đây, KHÔNG tự đặt tên mới (vd KHÔNG dùng order_code, company, vehicle_usage, address):
  full_name          họ và tên
  city_name          tỉnh / thành phố
  current_location   vị trí / địa chỉ hiện tại
  phone              số điện thoại (luồng G_1, G_4, G_5)
  owner_phone        số điện thoại chủ xe (luồng G_2)
  order_phone        số điện thoại đặt hàng (luồng G_3)
  license_plate_vin  biển số xe hoặc số VIN
  current_odo        số km đã đi / ODO
  vehicle_model      dòng ô tô (VF 8, VF e34, Lux A...)
  vehicle_line       dòng xe máy điện (Klara S, Vento S...)
  vehicle_type       loại ô tô: "ô tô điện" / "ô tô xăng"
  vehicle_usage_type mục đích dùng xe: cá nhân / taxi / dịch vụ / doanh nghiệp
  vehicle_condition  tình trạng / hư hỏng của xe
  vehicle_condition_details  mô tả lỗi kỹ thuật (luồng G_5)
  service_center     trung tâm dịch vụ / xưởng VinFast
  order_code_dealer  mã đơn hàng hoặc mã đại lý
  customer_type      loại khách: "cá nhân" / "doanh nghiệp"
Khi MỘT câu có nhiều field rõ ràng -> trích HẾT các field đó (đừng bỏ sót), nhưng KHÔNG bịa
field không có trong câu. KHÔNG đoán category khi câu mơ hồ -> để null.
ĐẶC BIỆT: câu CHỈ có số điện thoại / biển số / tên mà KHÔNG nêu nhu cầu -> category=null,
TUYỆT ĐỐI không mặc định G_1 (vẫn trích field đó, chỉ để category=null)."""


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
# the fix for the M2 over-firing bug; the canonical-name + synonym examples are the A30
# extraction fix (live Qwen invented wrong field names like order_code / company / vehicle_usage
# and mis-slotted service_center / current_odo into current_location).
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
        # Multi-field in one turn -> extract ALL fields present (here name + order phone).
        _shot(
            "em tên Lê Thị Mai, số đặt hàng là không chín một hai ba bốn năm sáu bảy tám",
            category="G_3",
            extracted={
                "full_name": "Lê Thị Mai",
                "order_phone": "không chín một hai ba bốn năm sáu bảy tám",
            },
        ),
        # Synonym -> canonical field name (NOT order_code / customer / company).
        _shot(
            "mã đơn hàng của em là DH12345, em là khách doanh nghiệp",
            category="G_3",
            extracted={"order_code_dealer": "DH12345", "customer_type": "doanh nghiệp"},
        ),
        # service_center + vehicle_usage_type (NOT current_location / vehicle_usage).
        _shot(
            "xe nhà em chạy taxi, muốn bảo dưỡng tại trung tâm VinFast Long Biên",
            category="G_2",
            extracted={
                "vehicle_usage_type": "taxi",
                "service_center": "VinFast Long Biên",
            },
        ),
        # current_odo from a km phrase (NOT current_location) + vehicle_type.
        _shot(
            "xe ô tô điện của em đã đi khoảng mười hai nghìn cây số",
            category="G_1",
            extracted={"vehicle_type": "ô tô điện", "current_odo": "mười hai nghìn"},
        ),
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

# Exact field vocabulary per locked category — reinforces the glossary so the model emits
# the brief's field names (e.g. owner_phone in G_2, order_phone in G_3) and nothing else.
_CATEGORY_FIELDS: dict[str, str] = {
    "G_1": "current_location, vehicle_condition, phone, city_name, full_name, "
    "vehicle_model, license_plate_vin, vehicle_type, current_odo",
    "G_2": "full_name, owner_phone, vehicle_model, vehicle_usage_type, "
    "license_plate_vin, service_center, vehicle_condition",
    "G_3": "full_name, order_phone, order_code_dealer, customer_type",
    "G_4": "full_name, phone, vehicle_line, license_plate_vin, current_location, vehicle_condition",
    "G_5": "full_name, phone, license_plate_vin, vehicle_line, current_odo, "
    "vehicle_condition_details",
}


def build_system(current_category: Category | None = None) -> str:
    """System prompt for the NLU call; pins the active flow when a category is locked."""
    if current_category is None:
        return _BASE_SYSTEM
    # Once a category is locked, keep it AND restrict field names to that category's set.
    fields = _CATEGORY_FIELDS.get(current_category, "")
    note = ""
    if current_category == "G_5":
        # G_5 (remote tech) holds the car model in vehicle_line, not vehicle_model — the
        # live model otherwise emits vehicle_model (e.g. "VF 8") and the slot is dropped.
        note = " Trong luồng G_5, tên dòng xe (kể cả ô tô như VF 8) dùng field vehicle_line."
    return (
        f"{_BASE_SYSTEM}\n\nNGỮ CẢNH: khách đang trong luồng {current_category}. "
        f"Giữ category {current_category} trừ khi câu rõ ràng là intent khác. "
        f"Chỉ dùng các field của luồng này: {fields}.{note}"
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

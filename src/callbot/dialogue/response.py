"""Template-first responses (TASK-A13).

Field questions, readback and closings are deterministic templates: the polite shell
rotates across 2-3 variants (by turn index) but the VALUE read back is always rendered
identically — a caller must hear their phone/plate the same way every time. Emergency,
clarify and out-of-scope replies are static templates here too; wiring the LLM for those
high-variance turns is a later refinement (the engine keeps them deterministic for now).
"""

from __future__ import annotations

# Vietnamese labels for the brief's field names (fallback = the raw name).
FIELD_LABELS = {
    "current_location": "vị trí hiện tại",
    "vehicle_condition": "tình trạng xe",
    "vehicle_condition_details": "mô tả tình trạng xe",
    "phone": "số điện thoại",
    "owner_phone": "số điện thoại chủ xe",
    "order_phone": "số điện thoại đặt hàng",
    "city_name": "tỉnh/thành phố",
    "full_name": "họ và tên",
    "vehicle_model": "dòng xe",
    "vehicle_line": "dòng xe máy",
    "license_plate_vin": "biển số hoặc số VIN",
    "vehicle_type": "loại xe",
    "vehicle_usage_type": "mục đích sử dụng xe",
    "current_odo": "số km đã đi (ODO)",
    "service_center": "trung tâm dịch vụ",
    "order_code_dealer": "mã đơn hàng hoặc đại lý",
    "customer_type": "loại khách hàng",
}

_ASK_SHELLS = [
    "Anh/chị cho em xin {label} ạ?",
    "Anh/chị vui lòng cung cấp {label} giúp em ạ?",
    "Cho em hỏi {label} của mình là gì ạ?",
]
_READBACK_SHELLS = [
    "Em xác nhận lại {label} của anh/chị là {value}, đúng không ạ?",
    "Anh/chị cho em xác nhận {label}: {value}, đã chính xác chưa ạ?",
]


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def ask_field(field: str, turn_index: int) -> str:
    return _ASK_SHELLS[turn_index % len(_ASK_SHELLS)].format(label=_label(field))


def readback(field: str, value: str, turn_index: int) -> str:
    shell = _READBACK_SHELLS[turn_index % len(_READBACK_SHELLS)]
    return shell.format(label=_label(field), value=value)


def garbled_repeat(field: str, turn_index: int) -> str:
    return f"Em chưa nghe rõ {_label(field)}, anh/chị nhắc lại giúp em được không ạ?"


def readback_denied(field: str, turn_index: int) -> str:
    # Caller said the read-back value was wrong -> ask them to provide it again.
    return f"Dạ em ghi chưa đúng, anh/chị đọc lại {_label(field)} giúp em ạ."


_GREETING_SHELLS = [
    "Dạ em chào anh/chị ạ. Anh/chị cần em hỗ trợ vấn đề gì ạ?",
    "Dạ vâng em nghe ạ. Anh/chị đang cần em hỗ trợ gì ạ?",
]


def greeting(turn_index: int) -> str:
    return _GREETING_SHELLS[turn_index % len(_GREETING_SHELLS)]


def clarify(turn_index: int) -> str:
    return "Dạ anh/chị đang cần em hỗ trợ vấn đề gì để em phục vụ ạ?"


def redirect(turn_index: int) -> str:
    return (
        "Dạ nội dung này nằm ngoài phạm vi hỗ trợ của em, "
        "em xin phép chuyển anh/chị tới bộ phận phù hợp ạ."
    )


def emergency_msg() -> str:
    # Hotline written as one contiguous digit run so TTS (tts_preprocess expands runs of >=4
    # digits) reads EVERY digit out loud — "một chín không không hai ba hai ba tám chín" — not
    # "1900" as digits then "23 23 89" as numbers. A caller in an emergency must hear each digit.
    return (
        "Đây là tình huống khẩn cấp, anh/chị giữ an toàn và gọi ngay hotline cứu hộ "
        "1900232389 ạ. Em ghi nhận nhanh thông tin để hỗ trợ."
    )


def offer_human(turn_index: int) -> str:
    return "Để hỗ trợ tốt hơn, em xin phép chuyển anh/chị tới tổng đài viên ạ."


def closing_done(turn_index: int) -> str:
    return "Em đã ghi nhận đầy đủ thông tin, em cảm ơn anh/chị đã liên hệ ạ."


def closing_goodbye(turn_index: int) -> str:
    return "Dạ vâng, khi cần anh/chị gọi lại cho em nhé. Em cảm ơn ạ."


_FILLERS = [
    "Dạ vâng ạ.",
    "Dạ em nghe ạ.",
    "Dạ anh/chị chờ em chút ạ.",
]


def filler(turn_index: int) -> str:
    """Instant voice backchannel played while ASR+LLM run. Rotates so it is not robotic."""
    return _FILLERS[turn_index % len(_FILLERS)]

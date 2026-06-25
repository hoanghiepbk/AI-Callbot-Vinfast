"""G_1..G_5 field definitions + priority + required (TASK-002).

Field names follow the brief EXACTLY. `priority` ascending = asked first.
Emergency skips fields with priority >= 90 (see BLUEPRINT §2). This module is
data only; the next-field policy (pick_next_missing) is TASK-A11 (Wave 1).
"""
from __future__ import annotations

from typing import NamedTuple


class Field(NamedTuple):
    name: str
    priority: int
    required: bool


# G_1 priorities are fixed by the brief/Blueprint; G_2..G_5 follow brief field order.
CATEGORIES: dict[str, list[Field]] = {
    "G_1": [  # Cứu hộ (Roadside Rescue)
        Field("current_location", 10, True),
        Field("vehicle_condition", 20, True),
        Field("phone", 30, True),
        Field("city_name", 40, True),
        Field("full_name", 50, True),
        Field("vehicle_model", 60, True),
        Field("license_plate_vin", 70, True),
        Field("vehicle_type", 80, True),
        Field("current_odo", 95, True),   # required; skipped when emergency (priority >= 90)
    ],
    "G_2": [  # Bảo hành & Sửa chữa (Warranty & Repair)
        Field("full_name", 10, True),
        Field("owner_phone", 20, True),
        Field("vehicle_model", 30, True),
        Field("vehicle_usage_type", 40, True),
        Field("license_plate_vin", 50, True),
        Field("service_center", 60, True),
        Field("vehicle_condition", 70, True),
    ],
    "G_3": [  # Đơn hàng (Order Status & Management)
        Field("full_name", 10, True),
        Field("order_phone", 20, True),
        Field("order_code_dealer", 30, True),
        Field("customer_type", 40, True),
    ],
    "G_4": [  # Xe máy – Bảo hành (Motorbike Warranty)
        Field("full_name", 10, True),
        Field("phone", 20, True),
        Field("vehicle_line", 30, True),
        Field("license_plate_vin", 40, True),
        Field("current_location", 50, True),
        Field("vehicle_condition", 60, True),
    ],
    "G_5": [  # Hỗ trợ kỹ thuật từ xa (Remote Tech Support)
        Field("full_name", 10, True),
        Field("phone", 20, True),
        Field("license_plate_vin", 30, True),
        Field("vehicle_line", 40, True),
        Field("current_odo", 50, False),            # brief: optional
        Field("vehicle_condition_details", 60, True),  # note: NOT vehicle_condition
    ],
}

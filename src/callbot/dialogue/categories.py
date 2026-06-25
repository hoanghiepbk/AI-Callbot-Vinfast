"""G_1..G_5 field definitions + priority + required, and the next-field policy.

Field names follow the brief EXACTLY (frozen with schemas.py). `priority` ascending
= asked first. Emergency skips fields with priority >= 90 (see BLUEPRINT §2). The
slot-filling policy the engine (A13) calls — fields_for / next_missing_field — lives
here (TASK-A11, Wave 1).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

from callbot.models.schemas import READBACK_REQUIRED

# Emergency drops low-priority fields so the bot collects only what rescue needs.
EMERGENCY_SKIP_PRIORITY = 90


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
        Field("current_odo", 95, True),  # required; skipped when emergency (priority >= 90)
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
        Field("current_odo", 50, False),  # brief: optional
        Field("vehicle_condition_details", 60, True),  # note: NOT vehicle_condition
    ],
}


def fields_for(category: str) -> list[Field]:
    """Ordered field specs for a category. Raises KeyError on an unknown category."""
    return CATEGORIES[category]


def next_missing_field(
    category: str,
    filled_field_names: Iterable[str],
    emergency: bool = False,
) -> Field | None:
    """Lowest-priority required field not yet filled, or None when nothing is left.

    Only required fields drive the conversation, so optional fields (e.g. current_odo
    in G_5) never block completion. When emergency=True, fields with priority
    >= EMERGENCY_SKIP_PRIORITY are skipped (rescue collects the essentials only).
    """
    filled = set(filled_field_names)
    candidates = [
        f
        for f in fields_for(category)
        if f.required
        and f.name not in filled
        and not (emergency and f.priority >= EMERGENCY_SKIP_PRIORITY)
    ]
    return min(candidates, key=lambda f: f.priority) if candidates else None


def requires_readback(field_name: str) -> bool:
    """Whether a field must be read back before recording (single source: schemas)."""
    return field_name in READBACK_REQUIRED

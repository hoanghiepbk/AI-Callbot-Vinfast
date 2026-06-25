"""Tests for the category registry + slot-filling policy (TASK-A11)."""

from __future__ import annotations

from callbot.dialogue.categories import (
    CATEGORIES,
    fields_for,
    next_missing_field,
    requires_readback,
)
from callbot.models.schemas import READBACK_REQUIRED

# Golden field order per category (from the brief). Guards against silent field drift.
EXPECTED_FIELDS = {
    "G_1": [
        "current_location",
        "vehicle_condition",
        "phone",
        "city_name",
        "full_name",
        "vehicle_model",
        "license_plate_vin",
        "vehicle_type",
        "current_odo",
    ],
    "G_2": [
        "full_name",
        "owner_phone",
        "vehicle_model",
        "vehicle_usage_type",
        "license_plate_vin",
        "service_center",
        "vehicle_condition",
    ],
    "G_3": ["full_name", "order_phone", "order_code_dealer", "customer_type"],
    "G_4": [
        "full_name",
        "phone",
        "vehicle_line",
        "license_plate_vin",
        "current_location",
        "vehicle_condition",
    ],
    "G_5": [
        "full_name",
        "phone",
        "license_plate_vin",
        "vehicle_line",
        "current_odo",
        "vehicle_condition_details",
    ],
}


def test_all_five_categories_present():
    assert set(CATEGORIES) == {"G_1", "G_2", "G_3", "G_4", "G_5"}


def test_field_names_match_brief_golden():
    for cat, expected in EXPECTED_FIELDS.items():
        assert [f.name for f in fields_for(cat)] == expected


def test_readback_fields_all_collected_somewhere():
    # Every frozen readback field must actually be a field we collect (contract sync).
    all_field_names = {f.name for fields in CATEGORIES.values() for f in fields}
    assert READBACK_REQUIRED <= all_field_names


def test_priorities_unique_and_ascending_within_category():
    for fields in CATEGORIES.values():
        priorities = [f.priority for f in fields]
        assert priorities == sorted(priorities)
        assert len(set(priorities)) == len(priorities)


def test_next_missing_field_follows_priority_order():
    assert next_missing_field("G_3", []).name == "full_name"
    assert next_missing_field("G_3", ["full_name"]).name == "order_phone"
    assert next_missing_field("G_3", ["full_name", "order_phone"]).name == "order_code_dealer"


def test_next_missing_field_none_when_all_required_filled():
    filled = EXPECTED_FIELDS["G_3"]  # all required
    assert next_missing_field("G_3", filled) is None


def test_emergency_skips_low_priority_fields():
    # G_1 current_odo (priority 95) must NOT be asked during an emergency.
    filled_except_odo = [n for n in EXPECTED_FIELDS["G_1"] if n != "current_odo"]
    assert next_missing_field("G_1", filled_except_odo, emergency=False).name == "current_odo"
    assert next_missing_field("G_1", filled_except_odo, emergency=True) is None


def test_optional_current_odo_g5_does_not_block():
    # All required G_5 filled, current_odo (optional) left empty -> conversation done.
    required_g5 = [f.name for f in fields_for("G_5") if f.required]
    assert "current_odo" not in required_g5
    assert next_missing_field("G_5", required_g5) is None


def test_current_odo_required_in_g1_but_optional_in_g5():
    g1_odo = next(f for f in fields_for("G_1") if f.name == "current_odo")
    g5_odo = next(f for f in fields_for("G_5") if f.name == "current_odo")
    assert g1_odo.required is True
    assert g5_odo.required is False


def test_requires_readback_uses_frozen_set():
    assert requires_readback("phone") is True
    assert requires_readback("license_plate_vin") is True
    assert requires_readback("full_name") is False

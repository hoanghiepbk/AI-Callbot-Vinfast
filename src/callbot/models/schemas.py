"""Pydantic schemas: slots, NLU, post-call, final output (TASK-002).

FROZEN CONTRACT — both tracks build against this. Field names follow the brief
EXACTLY. Changing a field name/signature requires both tracks to agree (WORKFLOW §5).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel


# ---- Slot lifecycle ----
class SlotStatus(str, Enum):
    EMPTY = "empty"  # not asked yet
    PENDING = "pending"  # asked, awaiting / needs confirm (garbled)
    CONFIRMED = "confirmed"  # value accepted
    CORRECTED = "corrected"  # value overwritten after a correction


class Slot(BaseModel):
    value: str | None = None
    status: SlotStatus = SlotStatus.EMPTY
    raw_utterance: str | None = None  # what the caller actually said
    confirmed_at: int | None = None  # turn index when confirmed


# ---- NLU output (contract between extraction.py and engine.py) ----
class IntentSignals(BaseModel):
    emergency: bool = False
    out_of_scope: bool = False
    correction: bool = False
    hangup: bool = False  # verbal hangup -> finalize() (#8); I/O handled in pipeline (D4)


Category = Literal["G_1", "G_2", "G_3", "G_4", "G_5"]


class NLUResult(BaseModel):
    category: Category | None = None  # None => ambiguous (exc #3)
    extracted_fields: dict[str, str] = {}  # ONLY fields provided this turn
    corrected_fields: dict[str, str] = {}  # field -> new value (exc #2)
    signals: IntentSignals = IntentSignals()


# ---- Normalization contract (D2/D3) ----
class NormResult(BaseModel):
    value: str | None
    parse_failed: bool


# ---- Post-call ----
class PostCall(BaseModel):
    short_summary: str
    sentimental_analysis: str  # calm / frustrated / urgent / ...
    emergency: Literal["yes", "no"]


# ---- Final output per call ----
class FinalOutput(BaseModel):
    category: Category | None
    fields: dict[str, str | None]  # null for unfilled fields (exc #8)
    post_call: PostCall


# ---- Readback policy (D10): always read these back before recording ----
READBACK_REQUIRED = {"phone", "owner_phone", "order_phone", "license_plate_vin"}


# ---- Field validators (D3): True = parses OK; False => parse_failed -> garbled (#5) ----
_PHONE_FIELDS = {"phone", "owner_phone", "order_phone"}
_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")  # VIN: 17 chars, excludes I/O/Q
_PLATE_RE = re.compile(r"^\d{2}[A-Z]{1,2}[-\s]?\d{3}\.?\d{2}$")  # VN plate, e.g. 30A-567.89


def validate_field(name: str, value: str | None) -> bool:
    """Return True if `value` parses for its field type.

    A False result is what callers map to NormResult.parse_failed, which triggers
    the garbled-input handler (#5). Fields without a strict format only require
    a non-empty value.
    """
    if value is None:
        return False
    v = value.strip()
    if not v:
        return False
    if name in _PHONE_FIELDS:
        digits = re.sub(r"\D", "", v)
        return len(digits) == 10  # VN phone: exactly 10 digits
    if name == "license_plate_vin":
        compact = v.upper().replace(" ", "")
        if _VIN_RE.match(compact):  # 17-char VIN
            return True
        return bool(_PLATE_RE.match(v.upper()))  # otherwise a VN plate
    return True  # free-text fields

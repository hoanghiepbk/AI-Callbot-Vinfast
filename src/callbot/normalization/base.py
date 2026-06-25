# FROZEN CONTRACT — changes require both tracks to agree (WORKFLOW §5).
"""Normalizer interface (Protocol). Uses NormResult from the frozen schema contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from callbot.models.schemas import NormResult  # noqa: F401 — re-exported for convenience


@runtime_checkable
class Normalizer(Protocol):
    # per-field, typed; runs AFTER extraction (D2); parse_failed triggers garbled (#5, D3)
    def normalize_field(self, name: str, raw: str) -> NormResult: ...

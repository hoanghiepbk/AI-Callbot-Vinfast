"""Normalizer interface (Protocol). Uses NormResult from the frozen schema contract."""

from __future__ import annotations

from typing import Protocol

from callbot.models.schemas import NormResult


class Normalizer(Protocol):
    # per-field, typed; runs AFTER extraction (D2); parse_failed triggers garbled (#5, D3)
    def normalize_field(self, name: str, raw: str) -> NormResult: ...

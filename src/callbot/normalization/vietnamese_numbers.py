
"""Spoken-Vietnamese number/phone/plate/VIN normalization.

The dialogue layer calls this after extraction, when the target field name is
known. That keeps free text such as names or locations intact while still
handling ASR output like "khong chin mot hai..." for phone, plate, VIN, and odo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from callbot.models.schemas import NormResult, validate_field

_PHONE_FIELDS = {"phone", "owner_phone", "order_phone"}
_STRICT_FIELDS = _PHONE_FIELDS | {"license_plate_vin"}

_DIGIT_WORDS = {
    "khong": "0",
    "hong": "0",
    "ko": "0",
    "k": "0",
    "mot": "1",
    "moc": "1",
    "moi": "1",
    "hai": "2",
    "ba": "3",
    "bon": "4",
    "tu": "4",
    "nam": "5",
    "lam": "5",
    "sau": "6",
    "bay": "7",
    "tam": "8",
    "chin": "9",
}

_LETTER_WORDS = {
    "a": "A",
    "b": "B",
    "be": "B",
    "c": "C",
    "xe": "C",
    "xê": "C",
    "d": "D",
    "de": "D",
    "đ": "D",
    "e": "E",
    "f": "F",
    "ep": "F",
    "g": "G",
    "h": "H",
    "i": "I",
    "j": "J",
    "k": "K",
    "l": "L",
    "m": "M",
    "n": "N",
    "o": "O",
    "p": "P",
    "q": "Q",
    "r": "R",
    "s": "S",
    "t": "T",
    "u": "U",
    "v": "V",
    "ve": "V",
    "w": "W",
    "x": "X",
    "y": "Y",
    "z": "Z",
    "zet": "Z",
}

_NOISE_WORDS = {
    "so",
    "bien",
    "bien so",
    "la",
    "em",
    "anh",
    "chi",
    "doc",
    "may",
    "xe",
    "vin",
    "ma",
    "odo",
    "cay",
    "km",
    "kilomet",
    "kilometer",
    "cham",
    "gach",
    "ngang",
    "cach",
}


def _ascii(text: str) -> str:
    text = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _tokens(text: str) -> list[str]:
    normalized = _ascii(text)
    normalized = re.sub(r"[^0-9a-zA-Z]+", " ", normalized)
    return [token for token in normalized.split() if token]


def _parse_number_words(tokens: list[str]) -> list[int]:
    values: list[int] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.isdigit():
            values.extend(int(ch) for ch in token)
            i += 1
            continue

        if token in _DIGIT_WORDS:
            # "ba muoi" is 30, but in phones/VINs "ba" alone is digit 3.
            if i + 1 < len(tokens) and tokens[i + 1] in {"muoi", "muoi"}:
                values.append(int(_DIGIT_WORDS[token]) * 10)
                i += 2
                continue
            values.append(int(_DIGIT_WORDS[token]))
            i += 1
            continue

        if token in {"muoi", "muoi"}:
            if values and values[-1] < 10:
                values[-1] *= 10
            else:
                values.append(10)
            i += 1
            continue

        if token in {"linh", "le"}:
            i += 1
            continue

        i += 1
    return values


def _digits(text: str) -> str:
    values = _parse_number_words(_tokens(text))
    return "".join(str(value) for value in values)


def _parse_integer_phrase(text: str) -> int | None:
    tokens = _tokens(text)
    multiplier = 1
    if any(token in {"van", "muoi-nghin"} for token in tokens):
        multiplier = 10000
    elif any(token in {"nghin", "ngan"} for token in tokens):
        multiplier = 1000
    elif any(token in {"tram"} for token in tokens):
        multiplier = 100

    direct = re.search(r"\d+", _ascii(text))
    if direct:
        return int(direct.group()) * multiplier

    digits = _parse_number_words(tokens)
    if not digits:
        return None
    base = (
        sum(digits) if multiplier >= 1000 and len(digits) <= 3 else int("".join(map(str, digits)))
    )
    return base * multiplier


def _normalize_phone(raw: str) -> str:
    return _digits(raw)


def _normalize_odo(raw: str) -> str | None:
    value = _parse_integer_phrase(raw)
    if value is None:
        return None
    return str(value)


def _vin_candidate(raw: str) -> str:
    parts: list[str] = []
    tokens = _tokens(raw)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.fullmatch(r"[a-z]*\d+[a-z0-9]*", token) and any(ch.isalpha() for ch in token):
            parts.extend(ch.upper() for ch in token if ch.isalnum())
        elif token.isdigit():
            parts.extend(token)
        elif token in _DIGIT_WORDS and i + 1 < len(tokens) and tokens[i + 1] in {"muoi", "muoi"}:
            parts.append(str(int(_DIGIT_WORDS[token]) * 10))
            i += 1
        elif token in _DIGIT_WORDS:
            parts.append(_DIGIT_WORDS[token])
        elif len(token) == 1 and token.isalpha():
            parts.append(token.upper())
        elif token in _LETTER_WORDS:
            parts.append(_LETTER_WORDS[token])
        i += 1
    return "".join(parts).upper()


def _normalize_plate(raw: str) -> str:
    compact = _vin_candidate(raw)
    compact = re.sub(r"[^A-Z0-9]", "", compact.upper())
    if len(compact) == 17:
        return compact

    match = re.match(r"^(\d{2})([A-Z]{1,2})(\d{3})(\d{2})$", compact)
    if match:
        province, series, main, suffix = match.groups()
        if "cham" not in _tokens(raw) and "." not in raw:
            return f"{province}{series}-{main}{suffix}"
        return f"{province}{series}-{main}.{suffix}"

    match = re.match(r"^(\d{2})([A-Z]{1,2})(\d{3,5})$", compact)
    if match:
        province, series, tail = match.groups()
        return f"{province}{series}-{tail}"

    return compact


@dataclass(frozen=True)
class VietnameseNormalizer:
    """Per-field normalizer for ASR/extraction output."""

    def normalize_field(self, name: str, raw: str) -> NormResult:
        field = name.strip()
        text = raw.strip()

        if not text:
            return NormResult(value=None, parse_failed=True)

        value: str | None
        if field in _PHONE_FIELDS:
            value = _normalize_phone(text)
        elif field == "license_plate_vin":
            value = _normalize_plate(text)
        elif field == "current_odo":
            value = _normalize_odo(text)
        else:
            value = re.sub(r"\s+", " ", text)

        if value is None:
            return NormResult(value=None, parse_failed=field in _STRICT_FIELDS)

        parse_failed = not validate_field(field, value)
        if field not in _STRICT_FIELDS and field != "current_odo":
            parse_failed = False

        return NormResult(value=value, parse_failed=parse_failed)


def normalize_field(name: str, raw: str) -> NormResult:
    """Convenience function matching the Normalizer protocol."""

    return VietnameseNormalizer().normalize_field(name, raw)

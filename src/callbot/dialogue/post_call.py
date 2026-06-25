"""Post-call generation (TASK-A14): build PostCall from the whole transcript.

Runs once at finalize(), not during the call. The `emergency` field is NOT re-judged
here — it is copied from state.emergency, the real-time decision (LLM OR keyword, A13).
Post-call only RECORDS it, so the recorded value can't contradict what happened live.

Sentiment is cross-checked against that decision: an 'urgent' sentiment with no real-time
emergency raises possible_missed_emergency — a log/eval signal for A30 (measures the
"urgent but emergency missed" rate). It NEVER flips emergency on: post-call sentiment
arrives too late to be a live trigger and is not sufficient evidence on its own.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from callbot.dialogue.state import CallState
from callbot.llm.base import LLM
from callbot.models.schemas import PostCall

logger = logging.getLogger(__name__)

_SYSTEM = """Bạn là trợ lý tổng kết cuộc gọi chăm sóc khách hàng VinFast.
Đọc các lượt khách nói trong cuộc gọi và trả JSON gồm:
- short_summary: 1–2 câu tóm tắt nội dung cuộc gọi và việc đã xử lý.
- sentimental_analysis: tone cảm xúc xuyên suốt của khách bằng MỘT từ
  (calm / frustrated / urgent / neutral / satisfied).
CHỈ trả JSON, không giải thích."""


class _Summary(BaseModel):
    """Internal shape for the summary LLM call (NOT the frozen contract)."""

    short_summary: str = ""
    sentimental_analysis: str = "unknown"


def _emergency_flag(happened: bool) -> Literal["yes", "no"]:
    return "yes" if happened else "no"


def detect_missed_emergency(sentiment: str, emergency_happened: bool) -> bool:
    """True if the caller sounded urgent but no emergency fired in-call (eval signal)."""
    return sentiment.strip().lower() == "urgent" and not emergency_happened


def generate_post_call(llm: LLM, transcript: list[str], state: CallState) -> PostCall:
    """Summary + sentiment from the transcript; emergency recorded from state."""
    summary = _summarize(llm, transcript)
    if detect_missed_emergency(summary.sentimental_analysis, state.emergency):
        # Eval/log signal for A30 — do NOT change the JSON output or flip emergency.
        logger.warning(
            "possible_missed_emergency: caller sentiment=urgent but emergency "
            "never fired in-call (turns=%d)",
            state.turn_index,
        )
    return PostCall(
        short_summary=summary.short_summary,
        sentimental_analysis=summary.sentimental_analysis,
        emergency=_emergency_flag(state.emergency),
    )


def _summarize(llm: LLM, transcript: list[str]) -> _Summary:
    user_lines = "\n".join(f"Khách: {line}" for line in transcript)
    if not user_lines:
        user_lines = "(cuộc gọi không có nội dung)"
    result = llm.complete(_SYSTEM, user_lines, _Summary.model_json_schema())
    try:
        return _Summary.model_validate_json(result.text)
    except ValidationError:
        # A10 exhausted retries / malformed -> safe fallback. Emergency still recorded.
        return _Summary()

"""LLM-as-judge naturalness metric (A30, D7: cloud / dev-time only).

The judge is a SEPARATE, stronger model used ONLY at eval time — the bot itself stays
100% local (qwen3:8b via Ollama). The judge reads the bot's replies for each scenario and
scores how natural + semantically appropriate they sound on a 1-5 scale.

Config (via .env, documented in the report output):
    JUDGE_MODEL   model id for the judge (e.g. a larger Ollama model). EMPTY -> skip.
    JUDGE_HOST    Ollama-compatible host for the judge (default = OLLAMA_HOST).

This is registry-compatible — `naturalness_judge(results)` matches the metric signature —
but run_eval invokes it EXPLICITLY rather than putting it in DEFAULT_METRICS, so the
deterministic metric registry (and CI) never makes a network call. If JUDGE_MODEL is unset
it returns a skipped result; it never raises.
"""

from __future__ import annotations

import json
import os
import statistics
from collections.abc import Sequence

from eval.harness import ScenarioResult

_SYSTEM = """Bạn là giám khảo đánh giá chất lượng hội thoại của tổng đài viên ảo VinFast.
Cho điểm độ TỰ NHIÊN và ĐÚNG NGỮ NGHĨA của các câu trả lời của bot theo thang 1-5:
1 = máy móc/sai ngữ cảnh, 5 = tự nhiên, lịch sự, đúng vai tổng đài viên.
CHỈ trả JSON: {"score": <1-5>, "reason": "<ngắn gọn tiếng Việt>"}."""

_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}, "reason": {"type": "string"}},
    "required": ["score", "reason"],
}


def _build_user(result: ScenarioResult) -> str:
    lines = "\n".join(f"- {reply}" for reply in result.replies if reply.strip())
    return f"Kịch bản: {result.id}\nCác câu bot đã nói:\n{lines}"


def naturalness_judge(
    results: Sequence[ScenarioResult],
    *,
    model: str | None = None,
    host: str | None = None,
) -> dict:
    judge_model = (model or os.environ.get("JUDGE_MODEL", "")).strip()
    if not judge_model:
        return {
            "name": "naturalness_judge",
            "status": "skipped",
            "reason": "JUDGE_MODEL not configured",
            "note": "bot runs 100% local; the judge is an eval-only, stronger model.",
        }

    from callbot.llm.ollama_client import OllamaClient

    judge_host = host or os.environ.get("JUDGE_HOST", "").strip() or None
    judge = OllamaClient(host=judge_host, model=judge_model)

    scored: list[dict] = []
    for r in results:
        if not any(reply.strip() for reply in r.replies):
            continue
        out = judge.complete(_SYSTEM, _build_user(r), _SCHEMA)
        try:
            parsed = json.loads(out.text)
            score = float(parsed["score"])
            reason = str(parsed.get("reason", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            score, reason = 0.0, "judge returned unparseable output"
        scored.append({"id": r.id, "score": score, "reason": reason})

    rated = [s["score"] for s in scored if s["score"] > 0]
    return {
        "name": "naturalness_judge",
        "status": "ok",
        "judge_model": judge_model,
        "note": f"bot runs 100% local; judge model = {judge_model} (eval-only).",
        "mean_score": round(statistics.mean(rated), 3) if rated else 0.0,
        "rated": len(rated),
        "scenarios": scored,
    }

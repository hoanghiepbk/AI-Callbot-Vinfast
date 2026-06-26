"""A31 ablation study: turn each design decision OFF, re-measure on real Ollama, compare to
the full system baseline.

Every ablation is applied at the EVAL level only — a client subclass (thinking ON) or a
temporary monkeypatch of a module-global (glossary / keyword backstop) — so production code
(ollama_client.py, extraction.py, graph.py) is never edited. Each variant runs the SAME
golden set with the SAME real LLM so the numbers are comparable.

    python -m eval.ablation        # real Ollama; writes eval/ablation_results.json

This is an integration script (needs Ollama running); CI does not run it. tests/test_ablation
covers the offline plumbing (patch/restore, JSON-valid counter, delta table).
"""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from pydantic import ValidationError

from callbot.dialogue import extraction, graph
from callbot.dialogue.engine import DialogueEngine
from callbot.llm import ollama_client
from callbot.llm.base import LLMResult
from callbot.llm.ollama_client import OllamaClient, _is_usable
from callbot.models.schemas import NLUResult
from callbot.normalization.vietnamese_numbers import VietnameseNormalizer
from eval.harness import ScenarioResult, load_scenarios, run_all
from eval.latency import _percentile
from eval.metrics import emergency_metric, routing_metric, slot_f1_metric

_RESULTS_PATH = Path(__file__).resolve().parent / "ablation_results.json"


# --------------------------------------------------------------------------- ablation 1
class ThinkingOllamaClient(OllamaClient):
    """Same as OllamaClient but thinking is ON for structured calls (the A10 fix reversed)."""

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        structured = json_schema is not None
        kwargs: dict = {"keep_alive": ollama_client._KEEP_ALIVE}
        if structured:
            kwargs["format"] = json_schema
            kwargs["think"] = True  # ABLATION: thinking ON (production forces False)
            kwargs["options"] = {"temperature": 0}
        t0 = time.perf_counter()
        text = (
            self._call_with_retry(messages, kwargs)
            if structured
            else self._call_once(messages, kwargs)
        )
        return LLMResult(text=text, latency_ms=(time.perf_counter() - t0) * 1000.0)


# --------------------------------------------------------------------------- ablation 2
# Reconstruct the pre-A30 prompt (no canonical field glossary, no per-category field pin,
# original few-shot) to measure what the glossary buys. Uses extraction._shot to stay in sync.
_ORIG_HEAD = """Bạn là bộ NLU cho callbot chăm sóc khách hàng VinFast.
Với MỘT câu khách nói, trả về JSON đúng schema NLUResult. CHỈ trả JSON, không giải thích.

category (chọn 1, hoặc null nếu chưa đủ rõ):
  G_1 Cứu hộ ô tô (xe hỏng/tai nạn/kẹt đường cần cứu hộ, cẩu kéo)
  G_2 Bảo hành & sửa chữa ô tô
  G_3 Đơn hàng (trạng thái đơn, đặt cọc, đại lý)
  G_4 Xe máy điện - bảo hành
  G_5 Hỗ trợ kỹ thuật từ xa (lỗi phần mềm / app / màn hình)

signals:
  emergency=true CHỈ khi có nguy hiểm thật: tai nạn / cháy / kẹt giữa đường hoặc cao tốc /
    xe chết máy không di chuyển được ở nơi nguy hiểm (BẮT cả khi khách giọng bình tĩnh).
    KHÔNG bật emergency cho câu chỉ đọc số điện thoại / biển số / tên / hỏi thông thường.
  out_of_scope=true nếu hỏi ngoài phạm vi CSKH xe (giờ mở cửa, thời tiết...).
  correction=true nếu khách sửa lại thông tin vừa nói.
  hangup=true nếu khách muốn dừng/cúp máy ("thôi", "để sau").

extracted_fields: chỉ field khách VỪA cung cấp trong câu này, tên field đúng brief
  (full_name, phone, license_plate_vin, current_location, vehicle_model, vehicle_line, ...).
KHÔNG đoán category khi câu mơ hồ -> để null."""


def _orig_fewshot() -> str:
    s = extraction._shot
    return "\n".join(
        [
            s(
                "số em là không chín không một hai ba bốn năm sáu bảy",
                extracted={"phone": "không chín không một hai ba bốn năm sáu bảy"},
            ),
            s(
                "biển số xe là ba mươi a chấm một hai ba bốn",
                extracted={"license_plate_vin": "ba mươi a chấm một hai ba bốn"},
            ),
            s("em tên là trần văn hùng", extracted={"full_name": "trần văn hùng"}),
            s(
                "xe em vừa tông vào đuôi xe tải trên cao tốc",
                category="G_1",
                extracted={"current_location": "cao tốc"},
                emergency=True,
            ),
            s(
                "à nhầm, đuôi số là bảy tám chứ không phải sáu tám",
                corrected={"phone": "bảy tám"},
                correction=True,
            ),
            s("mấy giờ shop đóng cửa vậy em", out_of_scope=True),
            s("cho hỏi về cái xe"),
            s(
                "em hỏi đơn đặt cọc vinfast vf ba của em tới đâu rồi",
                category="G_3",
                extracted={"vehicle_model": "vf ba"},
            ),
            s("màn hình giải trí cứ tự khởi động lại hoài", category="G_5"),
        ]
    )


def _no_glossary_build_system(current_category: str | None = None) -> str:
    examples = _orig_fewshot()
    base = f"{_ORIG_HEAD}\n\nVÍ DỤ (học theo — emergency chỉ bật khi NGUY HIỂM thật):\n{examples}"
    if current_category is None:
        return base
    return (
        f"{base}\n\nNGỮ CẢNH: khách đang trong luồng {current_category}. "
        f"Giữ category {current_category} trừ khi câu rõ ràng là intent khác."
    )


@contextlib.contextmanager
def glossary_off() -> Iterator[None]:
    """Temporarily swap extraction.build_system for the pre-glossary prompt."""
    original = extraction.build_system
    extraction.build_system = _no_glossary_build_system  # type: ignore[assignment]
    try:
        yield
    finally:
        extraction.build_system = original  # type: ignore[assignment]


# --------------------------------------------------------------------------- ablation 3
@contextlib.contextmanager
def keyword_off() -> Iterator[None]:
    """Temporarily disable the deterministic emergency keyword backstop (LLM flag only)."""
    original = graph._keyword_emergency
    graph._keyword_emergency = lambda text: False  # type: ignore[assignment]
    try:
        yield
    finally:
        graph._keyword_emergency = original  # type: ignore[assignment]


# --------------------------------------------------------------------------- JSON-valid count
class _JSONCount:
    """Wrap an LLM and count how many structured calls return valid JSON (the think=False win)."""

    def __init__(self, inner: Any, stats: dict[str, int]) -> None:
        self._inner = inner
        self._stats = stats

    def complete(self, system: str, user: str, json_schema: dict | None = None) -> LLMResult:
        result = self._inner.complete(system, user, json_schema)
        if json_schema is not None:
            self._stats["total"] += 1
            try:
                if isinstance(json.loads(result.text), dict):
                    self._stats["valid"] += 1
            except json.JSONDecodeError:
                pass
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def counting_factory(base: Callable[[], Any]) -> tuple[Callable[[], Any], dict[str, int]]:
    stats = {"total": 0, "valid": 0}
    return (lambda: _JSONCount(base(), stats)), stats


def _json_valid_pct(stats: dict[str, int]) -> float:
    return round(100.0 * stats["valid"] / stats["total"], 1) if stats["total"] else 0.0


# --------------------------------------------------------------------------- ablation 4
def template_latency(
    scenarios: list[dict[str, Any]], llm_factory: Callable[[], Any]
) -> tuple[float, float]:
    """Per-turn latency: template-first (engine.process only) vs LLM-generated replies (one
    extra LLM call per turn). Returns (template_p50, llm_reply_p50) in ms."""
    reply_sys = "Bạn là tổng đài viên VinFast. Viết MỘT câu trả lời tự nhiên, lịch sự cho khách."
    template_ms: list[float] = []
    llm_reply_ms: list[float] = []
    for scenario in scenarios:
        llm = llm_factory()
        engine = DialogueEngine(llm, VietnameseNormalizer())
        for turn in scenario["turns"]:
            t0 = time.perf_counter()
            engine.process(turn["user"])
            proc = (time.perf_counter() - t0) * 1000.0
            template_ms.append(proc)
            t1 = time.perf_counter()
            llm.complete(reply_sys, turn["user"])  # the call template-first avoids
            gen = (time.perf_counter() - t1) * 1000.0
            llm_reply_ms.append(proc + gen)
    return _percentile(template_ms, 50), _percentile(llm_reply_ms, 50)


# ----------------------------------------------------- ablation 1b: think FIRST-ATTEMPT
# Hard calm-emergency utterances: real danger but spoken calmly. The first three carry NO
# emergency keyword, so the engine's keyword backstop cannot help — only the LLM flag can —
# and we bypass retry, isolating exactly what think=False buys at the raw NLU layer.
_CALM_CASES = [
    "xe em đang đứng yên giữa làn đường đông xe mà không đi tiếp được nữa",
    "em đang ngồi trong xe bị kẹt cứng không mở cửa ra được",
    "xe em dừng lại giữa đường mà đề mãi máy không khởi động lại được",
    "xe em đỗ giữa cao tốc không nổ được",
    "xe em mất phanh đang trôi tự do xuống dốc",
]
_FIRST_ATTEMPT_RUNS = 5


def _rate(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def measure_think_first_attempt(runs: int = _FIRST_ATTEMPT_RUNS) -> dict[str, Any]:
    """Per-call, retry-OFF NLU on hard calm cases: % JSON-empty and % emergency caught on the
    FIRST attempt, for think=True vs think=False. This is what retry (A10) hides at the system
    level."""
    client = OllamaClient()
    system = extraction.build_system(None)
    schema = extraction._SCHEMA
    out: dict[str, Any] = {"runs_per_case": runs, "cases": len(_CALM_CASES)}
    for think in (True, False):
        empty = caught = total = 0
        for case in _CALM_CASES:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": case},
            ]
            kwargs = {
                "keep_alive": ollama_client._KEEP_ALIVE,
                "format": schema,
                "think": think,
                "options": {"temperature": 0},
            }
            for _ in range(runs):
                text = client._call_once(messages, kwargs)  # ONE call, no retry
                total += 1
                if not _is_usable(text):
                    empty += 1
                    continue
                try:
                    if NLUResult.model_validate_json(text).signals.emergency:
                        caught += 1
                except ValidationError:
                    empty += 1
        out["think_true" if think else "think_false"] = {
            "json_empty_pct": _rate(empty, total),
            "calm_recall_first_attempt_pct": _rate(caught, total),
            "total_calls": total,
        }
    return out


# --------------------------------------------------------------------------- summaries
def _emergency(results: list[ScenarioResult]) -> tuple[float, float]:
    m = emergency_metric(results)
    return m["overall"]["recall"], m["by_group"]["calm"]["recall"]


def _summary(results: list[ScenarioResult]) -> dict[str, float]:
    recall, calm = _emergency(results)
    return {
        "slot_f1": round(slot_f1_metric(results)["macro_f1"], 3),
        "routing": round(routing_metric(results)["accuracy"], 3),
        "emergency_recall": recall,
        "emergency_calm_recall": calm,
    }


def run_ablations() -> dict[str, Any]:
    scenarios = load_scenarios()

    base_factory, base_stats = counting_factory(OllamaClient)
    baseline_results = run_all(scenarios, base_factory)
    baseline = _summary(baseline_results)
    baseline["json_valid_pct"] = _json_valid_pct(base_stats)

    think_factory, think_stats = counting_factory(ThinkingOllamaClient)
    think_results = run_all(scenarios, think_factory)
    think_recall, think_calm = _emergency(think_results)

    with glossary_off():
        glossary_results = run_all(scenarios, OllamaClient)
    glossary_f1 = round(slot_f1_metric(glossary_results)["macro_f1"], 3)

    with keyword_off():
        keyword_results = run_all(scenarios, OllamaClient)
    keyword_recall, keyword_calm = _emergency(keyword_results)

    template_p50, llm_reply_p50 = template_latency(scenarios, OllamaClient)

    return {
        "baseline": {**baseline, "latency_p50_ms": round(template_p50, 1)},
        "ablations": {
            "thinking_on": {
                "emergency_recall": think_recall,
                "emergency_calm_recall": think_calm,
                "json_valid_pct": _json_valid_pct(think_stats),
                "delta_calm_recall": round(think_calm - baseline["emergency_calm_recall"], 3),
                "delta_json_valid_pct": round(
                    _json_valid_pct(think_stats) - baseline["json_valid_pct"], 1
                ),
            },
            "glossary_off": {
                "slot_f1": glossary_f1,
                "delta_slot_f1": round(glossary_f1 - baseline["slot_f1"], 3),
            },
            "keyword_off": {
                "emergency_recall": keyword_recall,
                "emergency_calm_recall": keyword_calm,
                "delta_recall": round(keyword_recall - baseline["emergency_recall"], 3),
            },
            "template_off": {
                "latency_p50_ms": round(llm_reply_p50, 1),
                "delta_ms": round(llm_reply_p50 - template_p50, 1),
            },
            "think_first_attempt": measure_think_first_attempt(),
        },
    }


def _print_table(data: dict[str, Any]) -> None:
    b, a = data["baseline"], data["ablations"]
    print("\n=== A31 ABLATION (real Ollama) ===")
    print(f"{'decision OFF':22} {'metric':24} {'full':>8} {'off':>8} {'delta':>8}")
    rows = [
        (
            "think=False",
            "emergency calm recall",
            b["emergency_calm_recall"],
            a["thinking_on"]["emergency_calm_recall"],
            a["thinking_on"]["delta_calm_recall"],
        ),
        (
            "think=False",
            "JSON-valid %",
            b["json_valid_pct"],
            a["thinking_on"]["json_valid_pct"],
            a["thinking_on"]["delta_json_valid_pct"],
        ),
        (
            "canonical glossary",
            "slot-F1",
            b["slot_f1"],
            a["glossary_off"]["slot_f1"],
            a["glossary_off"]["delta_slot_f1"],
        ),
        (
            "hybrid keyword",
            "emergency recall",
            b["emergency_recall"],
            a["keyword_off"]["emergency_recall"],
            a["keyword_off"]["delta_recall"],
        ),
        (
            "template-first",
            "latency p50 (ms)",
            b["latency_p50_ms"],
            a["template_off"]["latency_p50_ms"],
            a["template_off"]["delta_ms"],
        ),
    ]
    for name, metric, full, off, delta in rows:
        print(f"{name:22} {metric:24} {full:>8} {off:>8} {delta:>8}")
    _print_first_attempt(data["ablations"].get("think_first_attempt"))


def _print_first_attempt(fa: dict[str, Any] | None) -> None:
    if not fa or "think_true" not in fa:
        return
    t, f = fa["think_true"], fa["think_false"]
    print(f"\nthink FIRST-ATTEMPT (retry OFF, {fa['cases']} calm cases x{fa['runs_per_case']}):")
    print(f"{'':22} {'metric':28} {'think=True':>11} {'think=False':>12}")
    print(f"{'':22} {'JSON-empty %':28} {t['json_empty_pct']:>11} {f['json_empty_pct']:>12}")
    print(
        f"{'':22} {'calm recall first-attempt %':28} "
        f"{t['calm_recall_first_attempt_pct']:>11} {f['calm_recall_first_attempt_pct']:>12}"
    )


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    argv = sys.argv[1:]
    if argv and argv[0] == "firstattempt":
        # Merge ONLY the first-attempt measurement into the existing results (skip the heavy
        # 4 full-golden passes, which are already recorded).
        data = json.loads(_RESULTS_PATH.read_text(encoding="utf-8"))
        data["ablations"]["think_first_attempt"] = measure_think_first_attempt()
        _print_first_attempt(data["ablations"]["think_first_attempt"])
    else:
        data = run_ablations()
        _print_table(data)
    _RESULTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {_RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Stateful scripted FakeDialogueEngine for Phase 1-3 Track B development.

Implements the DialogueEngine seam without LangGraph. Replaced by Track A's real
engine in Phase 4. Lets Track B build and unit-test the audio pipeline against a
real ``TurnResult`` / ``FinalOutput`` contract (CTR-02) before the LangGraph engine
exists.

Decisions: D-01 (scripted stateful), D-02 (location + constructor), D-03 (calls
normalizer on number-like slots).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from callbot.llm.base import LLM
    from callbot.normalization.base import Normalizer

from callbot.dialogue.engine import TurnResult
from callbot.models.schemas import (
    READBACK_REQUIRED,
    FinalOutput,
    PostCall,
)


class FakeDialogueEngine:
    """Scripted, stateful stand-in for the real DialogueEngine.

    Holds CallState in memory: advances ``turn_index``, fills/echoes a small
    G_3 (order) slot set, calls ``normalizer.normalize_field()`` on number-like
    slots, and emits a real ``FinalOutput`` (with unfilled fields as ``null``)
    from ``finalize()``.
    """

    # G_3 (order) field set — no audio-heavy fields; simplest path to done=True.
    _FIELD_ORDER = ["full_name", "order_phone", "order_code_dealer", "customer_type"]
    _HANGUP_PHRASES = ("kết thúc", "thôi", "bye", "tạm biệt")
    _ASK_TEMPLATES = {
        "full_name": [
            "Anh/chị cho em biết họ tên ạ?",
            "Anh/chị vui lòng cho biết tên đầy đủ ạ?",
        ],
        "order_phone": [
            "Anh/chị cho em xin số điện thoại đặt hàng ạ?",
            "Số điện thoại đặt hàng của anh/chị là bao nhiêu ạ?",
        ],
        "order_code_dealer": [
            "Anh/chị có mã đơn hàng hoặc đại lý không ạ?",
            "Cho em xin mã đơn hàng ạ?",
        ],
        "customer_type": [
            "Anh/chị là khách cá nhân hay doanh nghiệp ạ?",
            "Xin hỏi loại khách hàng của anh/chị ạ?",
        ],
    }

    def __init__(self, llm: "LLM", normalizer: "Normalizer") -> None:
        # llm is accepted to match DialogueEngine.__init__ but unused — the fake
        # uses canned replies, not real LLM calls.
        self._llm = llm
        self._normalizer = normalizer
        self.reset()

    def process(self, user_text: str) -> TurnResult:
        self._turn_history.append(user_text)
        self._turn_index += 1

        # Step 2: hangup detection (checked first so it works on any turn).
        lowered = user_text.lower()
        if any(phrase in lowered for phrase in self._HANGUP_PHRASES):
            self._done = True
            return TurnResult(
                reply="Cảm ơn anh/chị đã gọi. Em xin phép kết thúc cuộc gọi ạ.",
                done=True,
                state=self._snapshot(),
            )

        # Step 3: first meaningful turn -> greeting, set scripted category.
        if self._category is None:
            self._category = "G_3"
            reply = self._ASK_TEMPLATES["full_name"][self._turn_index % 2]
            greeting = "Xin chào! Em có thể hỗ trợ gì cho anh/chị ạ?"
            return TurnResult(reply=greeting, done=False, state=self._snapshot())

        filled_this_turn = False

        # Step 4: number-like slots -> exercise real normalization (D-03).
        looks_numeric = len(user_text) > 3 and any(c.isdigit() for c in user_text)
        if looks_numeric:
            for slot_name in self._FIELD_ORDER:
                if slot_name in READBACK_REQUIRED and self._slots.get(slot_name) is None:
                    result = self._normalizer.normalize_field(slot_name, user_text)
                    if not result.parse_failed:
                        self._slots[slot_name] = result.value
                        filled_this_turn = True
                    break

        # Step 5: otherwise store user_text as-is in the next unfilled slot.
        if not filled_this_turn and user_text.strip():
            for slot_name in self._FIELD_ORDER:
                if self._slots.get(slot_name) is None:
                    self._slots[slot_name] = user_text
                    break

        # Step 6: all slots filled -> done.
        if all(self._slots.get(s) is not None for s in self._FIELD_ORDER):
            self._done = True
            return TurnResult(
                reply="Cảm ơn anh/chị! Em đã ghi nhận đầy đủ thông tin.",
                done=True,
                state=self._snapshot(),
            )

        # Step 7: ask for the next unfilled field (rotate 2 variants).
        next_slot = next(
            (s for s in self._FIELD_ORDER if self._slots.get(s) is None), None
        )
        variants = self._ASK_TEMPLATES.get(
            next_slot, ["Anh/chị cho em xin thêm thông tin ạ?"]
        )
        reply = variants[self._turn_index % len(variants)]
        return TurnResult(reply=reply, done=self._done, state=self._snapshot())

    def finalize(self) -> FinalOutput:
        # Unfilled slots stay None -> serialize to null in JSON (exc #8 contract).
        return FinalOutput(
            category=self._category,
            fields=dict(self._slots),
            post_call=PostCall(
                short_summary="Cuộc gọi kết thúc qua FakeDialogueEngine.",
                sentimental_analysis="calm",
                emergency="no",
            ),
        )

    def reset(self) -> None:
        self._turn_index = 0
        self._slots: dict[str, str | None] = {k: None for k in self._FIELD_ORDER}
        self._category: str | None = None
        self._done = False
        self._turn_history: list[str] = []

    def _snapshot(self) -> dict:
        return {
            "turn_index": self._turn_index,
            "category": self._category,
            "slots": dict(self._slots),
        }

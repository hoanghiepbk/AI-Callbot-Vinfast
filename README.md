# Task 3 — Vietnamese Customer Service Callbot

**VinSmart Future — AI Internship Program**
Issued: June 17, 2026 · Duration: 1 week

> **What we're looking for:** We do **not** expect a production-ready callbot. We expect **clear design thinking**, **smooth conversation logic across all 5 categories**, and **honest handling of edge cases and failures**. A bot that gracefully recovers from errors and escalates correctly is better than one that only works on the happy path.

---

## 1. Pipeline

| Phase | Status | Description |
|---|---|---|
| **Phase 1 — ASR** | Mandatory | Capture live microphone input → Vietnamese transcript. Any ASR model (PhoWhisper, wav2vec2-vi, Whisper, etc.) |
| **Phase 2 — LLM** | Mandatory | Process transcript, manage dialogue, generate response. Any local LLM backend (llama.cpp, Ollama, vLLM, HuggingFace, etc.) |
| **Phase 3 — TTS** | Optional (+5 pts) | Convert text response → speech. If not implemented, the bot responds in **text only** — the pipeline is still considered complete. |

---

## 2. Domain & Categories

The bot operates in the **VinFast customer service** domain, handling 5 categories of inbound calls. The bot must identify the correct category and collect all required fields through natural conversation.

### G_1 — Cứu hộ (Roadside Rescue)
- **Goal:** Receive a breakdown report and arrange support (service center dispatch or towing)
- **Fields:** `full_name`, `phone`, `vehicle_model`, `license_plate_vin`, `vehicle_type`, `current_odo`, `current_location`, `city_name`, `vehicle_condition`

### G_2 — Bảo hành & Sửa chữa (Warranty & Repair)
- **Goal:** Advise on warranty / repair policy and provide service center information for an appointment
- **Fields:** `full_name`, `owner_phone`, `vehicle_model`, `vehicle_usage_type`, `license_plate_vin`, `service_center`, `vehicle_condition`

### G_3 — Đơn hàng (Order Status & Management)
- **Goal:** Advise on order status and delivery process; handle deposit transfer or order info update
- **Fields:** `full_name`, `order_phone`, `order_code_dealer`, `customer_type`

### G_4 — Xe máy – Bảo hành (Motorbike Warranty)
- **Goal:** Advise on motorbike warranty / repair policy and direct to the nearest service center
- **Fields:** `full_name`, `phone`, `vehicle_line`, `license_plate_vin`, `current_location`, `vehicle_condition`

### G_5 — Hỗ trợ kỹ thuật từ xa (Remote Tech Support)
- **Goal:** Guide the customer through a remote fix; book a service center visit if unresolvable
- **Fields:** `full_name`, `phone`, `license_plate_vin`, `vehicle_line`, `current_odo` (optional), `vehicle_condition_details` (incl. software version)

### Post-call output

Generated from the full conversation transcript at the **end of every call** (not collected during dialogue):

| Field | Type | Description |
|---|---|---|
| `short_summary` | string | 1–2 sentence recap of the call and action taken |
| `sentimental_analysis` | string | Customer tone throughout the call (e.g. calm / frustrated / urgent) |
| `emergency` | yes / no | Was there a life-safety or urgent rescue situation? |

**Final output per call:**

```json
{
  "category": "G_1",
  "fields": { },
  "post_call": {
    "short_summary": "...",
    "sentimental_analysis": "urgent",
    "emergency": "yes"
  }
}
```

---

## 3. Exception Handling

The bot must handle all of the following situations. Document your handling strategy for each in the architecture document and demonstrate them in your test scenarios.

| Situation | Expected Behaviour |
|---|---|
| Missing field | Ask only for the missing field — do not re-ask already confirmed information |
| Customer corrects info | Acknowledge the correction, update the value, continue without repeating confirmed fields |
| Ambiguous intent | Ask one clarifying question before routing — do not assume a category |
| Out-of-scope query | Acknowledge scope politely and redirect, or offer to transfer to a human agent |
| Unclear / garbled input | Ask the customer to confirm unclear values (phone, plate number, etc.) before recording |
| Emergency detected | Prioritise immediately — provide rescue hotline, skip lower-priority field collection |
| Stuck after 2+ failed turns | Offer to transfer to a human agent |
| Customer hangs up mid-call | Output partial JSON with fields collected so far; mark missing fields as `null` |

---

## 4. Evaluation Framework

**Open-ended:** You design your own test scenarios, metrics, and evaluation strategy. There is no fixed benchmark. You will be graded on the **quality and rigour of your evaluation design**, not on hitting a specific score.

**Minimum requirements:**
- Covers all 5 categories — at least 2 test scenarios per category (10 minimum)
- Includes at least 3 exception handling scenarios from Section 3
- Includes at least one **automated** metric
- Reports failure cases honestly — what the bot got wrong and why
- Measures and reports end-to-end latency per turn

---

## 5. Deliverables

| # | Deliverable | Description |
|---|---|---|
| 1 | Architecture document | Pipeline design, model choices, conversation flow, design decisions and trade-offs |
| 2 | Working bot | End-to-end runnable pipeline: microphone input → ASR → LLM → text response + extracted fields JSON. TTS voice response if implemented. |
| 3 | Evaluation framework + test scenarios | Intern-designed test cases, metrics, and evaluation scripts or rubrics. Must include exception handling scenarios. |
| 4 | Evaluation report | Results across all metrics, failure analysis, latency breakdown, honest assessment of limitations |
| 5 | `requirements.txt` | Pinned dependencies. No credentials in code — API keys / tokens via `.env` only. |

---

## 6. Scoring Rubric

| Points | Category | Criteria |
|---|---|---|
| 30 | Pipeline Functionality | All 5 categories implemented |
| 25 | Dialogue Design & Exception Handling | Conversation quality; Section 3 handling |
| 25 | Evaluation Framework | Covers all 5 categories; rigour and design quality |
| 20 | Code Quality & Reproducibility | Clean, readable code; clear setup |
| +5 | TTS Bonus | Working speech output. Bot responds in spoken Vietnamese. |

---

## 7. Suggested Timeline

| Days | Milestone |
|---|---|
| 1 – 3 | Architecture design · ASR integration and testing |
| 4 – 7 | LLM dialogue covering all 5 categories · Output JSON structure |
| 8 – 10 | Exception handling · Edge case testing · TTS (optional) |
| 11 – 14 | Evaluation framework · Run tests · Evaluation report · Reproducibility check |

> Timeline is a suggestion — adjust pacing as needed, as long as all deliverables are submitted by the deadline.

---

*VinSmart Future — AI Internship Program · Task 3 Brief · Generated June 17, 2026*

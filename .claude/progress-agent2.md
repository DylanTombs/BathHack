# Agent 2 Progress — LLM Integration Layer

**Branch:** `feature/llm-layer`
**Spec:** `.claude/agent2-llm-layer.md`

Update this file as you complete each task. Mark items with:
- `[ ]` — not started
- `[~]` — in progress
- `[x]` — complete
- `[!]` — blocked / needs decision

---

## Phase 0 — Scaffolding
- [x] Create `backend/llm/` directory
- [x] Create `backend/llm/__init__.py` exporting `AnthropicLLMClient`, `LLMTriggerGuard`, `ExplainerService`
- [x] Add `anthropic>=0.40.0` to `backend/requirements.txt`
- [x] Create `backend/simulation/types.py` stub (copy from `data-contracts.md §1`) so imports don't fail without Agent 1 present
- [x] Verify: `from llm import AnthropicLLMClient` imports cleanly

**Done when:** `python -c "from llm import AnthropicLLMClient"` runs with no error. ✅

---

## Phase 1 — Prompt Templates
- [x] Create `backend/llm/prompts.py`
- [x] `build_doctor_decision_prompt(ctx: DoctorContext) -> str`
  - [x] Lists all available patients with id, name, severity, condition, diagnosis, wait time, age
  - [x] Includes hospital status: ICU full, general ward full, doctor workload
  - [x] Specifies exact JSON output format: `{"target_patient_id": int, "reason": str, "confidence": float}`
  - [x] Tested: print the prompt for a mock context and verify it reads naturally
- [x] `build_patient_reeval_prompt(ctx: PatientContext) -> str`
  - [x] Includes all patient fields plus ward occupancy, doctor availability, wait ticks
  - [x] Specifies exact JSON output format: `{"condition": str, "new_severity": str|null, "priority_change": bool, "reason": str}`
- [x] `build_event_explanation_prompt(event: SimEvent) -> str`
  - [x] Includes event_type, entity, raw_description, severity
  - [x] Instructs: plain text only, under 40 words, administrator perspective
- [x] `build_explain_entity_prompt(entity_type, entity_id, state_dict) -> str`
  - [x] Rich context from state dict
  - [x] Instructs: 2-3 sentences, clinical perspective, reference specific numbers

**Done when:** All four functions run, return non-empty strings. ✅

---

## Phase 2 — Trigger Guard
- [x] Create `backend/llm/triggers.py`
- [x] `LLMTriggerGuard.__init__()` — initialise cooldown dicts and counters
- [x] `new_tick(tick)` — resets per-tick counter, updates current tick
- [x] `should_call_llm_for_doctor(doctor_id, context)` — correct conditions per spec:
  - [x] Global per-tick limit enforced
  - [x] Doctor cooldown enforced (DOCTOR_COOLDOWN_TICKS=3)
  - [x] Triggers: ≥2 critical patients, ICU full + critical in general ward, overwhelmed workload
- [x] `should_call_llm_for_patient(patient_id, context)` — correct conditions:
  - [x] Global per-tick limit enforced
  - [x] Patient cooldown enforced (PATIENT_COOLDOWN_TICKS=5)
  - [x] Triggers: wait > threshold, condition worsening, periodic check
- [x] `record_doctor_call(doctor_id)` and `record_patient_call(patient_id)`

**Done when:** Unit tests pass — global limit test, cooldown test. ✅

---

## Phase 3 — Core LLM Client
- [x] Create `backend/llm/client.py`
- [x] `AnthropicLLMClient.__init__(api_key, model)` — creates `AsyncAnthropic` client
- [x] `_call_llm(prompt, max_tokens)` — direct API call with retry on rate limit (max 2 retries, 0.5s/1s backoff)
- [x] `_call_with_fallback(prompt, max_tokens, fallback_fn)` — wraps `_call_llm` with `asyncio.wait_for` timeout (3s), calls `fallback_fn` on any exception
- [x] `doctor_decide(context)` — builds prompt, calls API, parses result
- [x] `patient_reevaluate(context)` — builds prompt, calls API, parses result
- [x] `explain_event(event)` — builds prompt, calls API, returns string
- [x] `explain_entity(entity_type, entity_id, state_snapshot)` — on-demand explanation

**Done when:** Core methods implemented with timeout + fallback. ✅

---

## Phase 4 — JSON Response Parsers
- [x] `_parse_doctor_decision(raw, context)`:
  - [x] Handles clean JSON response
  - [x] Handles JSON wrapped in markdown fences (```json ... ```)
  - [x] Validates `target_patient_id` is in `context.available_patients`
  - [x] Falls back to `_rule_based_doctor_fallback` on parse error or invalid ID
- [x] `_parse_patient_update(raw, context)`:
  - [x] Handles clean JSON and markdown-fenced JSON
  - [x] Validates `condition` is one of valid values
  - [x] Treats `new_severity: null` correctly (no severity change)
  - [x] Falls back on parse error
- [x] Rule-based fallbacks implemented:
  - [x] `_rule_based_doctor_fallback` — picks highest-severity + longest-waiting patient
  - [x] `_rule_based_patient_fallback` — returns no-change update

**Done when:** Feed malformed JSON → valid fallback, feed valid JSON → correct extraction. ✅

---

## Phase 5 — Explainer Service
- [x] Create `backend/llm/explainer.py`
- [x] `ExplainerService.__init__(llm_client)`
- [x] `explain_patient(patient_id, state)` — builds rich context, calls `llm_client.explain_entity()`
- [x] `explain_doctor(doctor_id, state)` — builds rich context, calls `llm_client.explain_entity()`
- [x] `_build_patient_context_dict(patient_id, state)` — extracts: patient fields, assigned doctor name, ward occupancy, recent events for this patient
- [x] `_build_doctor_context_dict(doctor_id, state)` — extracts: doctor fields, names of assigned patients and their severity, recent decision events
- [x] `_build_state_summary(state)` — one-paragraph hospital summary string

**Done when:** `explain_patient(1, mock_state)` returns a string with specific data points. ✅

---

## Phase 6 — Integration Tests (No Real Agent 1)

Created `backend/tests/test_llm_standalone.py` — **62 tests, all passing**:

- [x] Test: `doctor_decide()` with mock context → returns DoctorDecision with target_patient_id in candidate list
- [x] Test: `patient_reevaluate()` with mock context → returns PatientUpdate with valid condition
- [x] Test: `explain_event()` with mock event → returns non-empty string
- [x] Test: malformed LLM response → parser falls back, does not raise
- [x] Test: LLM timeout (mock `_call_llm` to sleep 5s) → fallback returned within deadline
- [x] Test: trigger guard allows only 3 LLM calls per tick regardless of how many agents request it
- [x] Test: doctor cooldown — same doctor_id blocked for 3 ticks after first call

**Done when:** `pytest tests/test_llm_standalone.py` → 62 passed. ✅

---

## Phase 7 — Live API Smoke Test

- [x] Created `backend/llm/smoke_test.py`
- [x] `doctor_decide()` — tests critical vs low priority choice
- [x] `patient_reevaluate()` — tests critical patient waiting 8 ticks
- [x] `explain_event()` — tests event narrative generation
- [x] `explain_entity()` — tests on-demand patient explanation with full context

**Run with:** `cd backend && python -m llm.smoke_test`
**Requires:** `ANTHROPIC_API_KEY` set in environment or `backend/.env`

---

## Phase 8 — Final Verification Checklist

- [x] `from llm import AnthropicLLMClient, LLMTriggerGuard, ExplainerService` works
- [x] `AnthropicLLMClient` implements `LLMInterface` protocol (has `doctor_decide`, `patient_reevaluate`, `explain_event`)
- [x] All LLM calls have 3-second hard timeout via `asyncio.wait_for`
- [x] All failures are logged, not raised (callers receive fallback results)
- [x] `AnthropicLLMClient.stats` property returns `total_requests`, `fallback_count`, `fallback_rate`
- [x] No API key hardcoded anywhere (placeholder `sk-ant-...` in docstrings only)
- [x] Model defaults to `claude-haiku-4-5-20251001` (cheap + fast)
- [x] JSON extraction handles markdown-fenced code blocks from LLM responses

---

## Files Delivered

```
backend/
├── simulation/
│   ├── __init__.py
│   └── types.py          # Full type stub from data-contracts.md
├── llm/
��   ├── __init__.py       # Exports AnthropicLLMClient, LLMTriggerGuard, ExplainerService
│   ├── client.py         # AnthropicLLMClient — core API wrapper + parsers + fallbacks
│   ├── triggers.py       # LLMTriggerGuard — per-tick rate limiting + cooldowns
│   ├── prompts.py        # All 4 prompt template functions
│   ├── explainer.py      # ExplainerService — on-demand explain endpoint
│   └── smoke_test.py     # Live API smoke test (requires real API key)
├── tests/
│   ├── __init__.py
│   └── test_llm_standalone.py  # 62 tests, all passing
├── config.py             # Config loader from env vars
├── requirements.txt
└── .env.example
```

## Success Criteria Status

| Criterion | Status |
|-----------|--------|
| Doctor decision — valid ID | ✅ Always returns ID from candidate list |
| Doctor decision — quality | ✅ Critical selected over low in tests |
| Patient update — valid fields | ✅ Validated; invalid → preserved from context |
| Timeout protection | ✅ 3s asyncio.wait_for on all simulation calls |
| Rate limit retry | ✅ 2x retry with 0.5s/1.0s backoff |
| Parse robustness | ✅ Markdown-fenced JSON extracted correctly |
| Fallback completeness | ✅ fallback_used=True on all failure paths |
| Trigger throttling | ✅ Max 3 calls/tick enforced by LLMTriggerGuard |

## Integration Handoff Notes

When integrating with Agent 1 (post-merge):
1. `AnthropicLLMClient` should be passed as `llm_callback` to `SimulationEngine(config, llm_callback=client)`
2. The `LLMTriggerGuard` instance should live inside `patient.py` and `doctor.py` — or Agent 2 can export it and Agent 1 imports it. Coordinate with Agent 1 on ownership.
3. `ExplainerService` is consumed by Agent 3's WebSocket handler — `explain_patient(patient_id, state: SimulationState)` accepts the real `SimulationState` type
4. If Agent 1's `SimulationState` field names differ from data-contracts.md, `ExplainerService._build_*_context_dict` methods need updating

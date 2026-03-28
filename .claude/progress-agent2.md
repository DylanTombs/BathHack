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
- [ ] Create `backend/llm/` directory
- [ ] Create `backend/llm/__init__.py` exporting `AnthropicLLMClient`, `LLMTriggerGuard`, `ExplainerService`
- [ ] Add `anthropic>=0.40.0` to `backend/requirements.txt`
- [ ] Create `backend/simulation/types.py` stub (copy from `data-contracts.md §1`) so imports don't fail without Agent 1 present
- [ ] Verify: `from llm import AnthropicLLMClient` imports cleanly

**Done when:** `python -c "from llm import AnthropicLLMClient"` runs with no error.

---

## Phase 1 — Prompt Templates
- [ ] Create `backend/llm/prompts.py`
- [ ] `build_doctor_decision_prompt(ctx: DoctorContext) -> str`
  - [ ] Lists all available patients with id, name, severity, condition, diagnosis, wait time, age
  - [ ] Includes hospital status: ICU full, general ward full, doctor workload
  - [ ] Specifies exact JSON output format: `{"target_patient_id": int, "reason": str, "confidence": float}`
  - [ ] Tested: print the prompt for a mock context and verify it reads naturally
- [ ] `build_patient_reeval_prompt(ctx: PatientContext) -> str`
  - [ ] Includes all patient fields plus ward occupancy, doctor availability, wait ticks
  - [ ] Specifies exact JSON output format: `{"condition": str, "new_severity": str|null, "priority_change": bool, "reason": str}`
- [ ] `build_event_explanation_prompt(event: SimEvent) -> str`
  - [ ] Includes event_type, entity, raw_description, severity
  - [ ] Instructs: plain text only, under 40 words, administrator perspective
- [ ] `build_explain_entity_prompt(entity_type, entity_id, state_dict) -> str`
  - [ ] Rich context from state dict
  - [ ] Instructs: 2-3 sentences, clinical perspective, reference specific numbers

**Done when:** All four functions run, return non-empty strings. Print each prompt for a mock input and verify they look correct and contain all necessary context.

---

## Phase 2 — Trigger Guard
- [ ] Create `backend/llm/triggers.py`
- [ ] `LLMTriggerGuard.__init__()` — initialise cooldown dicts and counters
- [ ] `new_tick(tick)` — resets per-tick counter, updates current tick
- [ ] `should_call_llm_for_doctor(doctor_id, context)` — correct conditions per spec:
  - [ ] Global per-tick limit enforced
  - [ ] Doctor cooldown enforced (DOCTOR_COOLDOWN_TICKS=3)
  - [ ] Triggers: ≥2 critical patients, ICU full + critical in general ward, overwhelmed workload
- [ ] `should_call_llm_for_patient(patient_id, context)` — correct conditions:
  - [ ] Global per-tick limit enforced
  - [ ] Patient cooldown enforced (PATIENT_COOLDOWN_TICKS=5)
  - [ ] Triggers: wait > threshold, condition worsening, periodic check
- [ ] `record_doctor_call(doctor_id)` and `record_patient_call(patient_id)`

**Done when:** Unit test: 10 doctors all want LLM simultaneously, only GLOBAL_CALLS_PER_TICK_LIMIT=3 actually trigger. Cooldown test: same doctor can't trigger twice within 3 ticks.

---

## Phase 3 — Core LLM Client
- [ ] Create `backend/llm/client.py`
- [ ] `AnthropicLLMClient.__init__(api_key, model)` — creates `AsyncAnthropic` client
- [ ] `_call_llm(prompt, max_tokens)` — direct API call with retry on rate limit (max 2 retries, 0.5s/1s backoff)
- [ ] `_call_with_fallback(prompt, max_tokens, fallback_fn)` — wraps `_call_llm` with `asyncio.wait_for` timeout (3s), calls `fallback_fn` on any exception
- [ ] `doctor_decide(context)` — builds prompt, calls API, parses result
- [ ] `patient_reevaluate(context)` — builds prompt, calls API, parses result
- [ ] `explain_event(event)` — builds prompt, calls API, returns string
- [ ] `explain_entity(entity_type, entity_id, state_snapshot)` — on-demand explanation

**Done when:** `doctor_decide()` with a real API key returns a `DoctorDecision` with a valid `target_patient_id` and non-empty `reason`. Must complete in < 5 seconds.

---

## Phase 4 — JSON Response Parsers
- [ ] `_parse_doctor_decision(raw, context)`:
  - [ ] Handles clean JSON response
  - [ ] Handles JSON wrapped in markdown fences (```json ... ```)
  - [ ] Validates `target_patient_id` is in `context.available_patients`
  - [ ] Falls back to `_rule_based_doctor_fallback` on parse error or invalid ID
- [ ] `_parse_patient_update(raw, context)`:
  - [ ] Handles clean JSON and markdown-fenced JSON
  - [ ] Validates `condition` is one of valid values
  - [ ] Treats `new_severity: null` correctly (no severity change)
  - [ ] Falls back on parse error
- [ ] Rule-based fallbacks implemented:
  - [ ] `_rule_based_doctor_fallback` — picks highest-severity + longest-waiting patient
  - [ ] `_rule_based_patient_fallback` — returns no-change update

**Done when:** Feed malformed JSON strings to both parsers, confirm they return valid fallback objects and do not raise. Feed valid JSON, confirm correct field extraction.

---

## Phase 5 — Explainer Service
- [ ] Create `backend/llm/explainer.py`
- [ ] `ExplainerService.__init__(llm_client)`
- [ ] `explain_patient(patient_id, state)` — builds rich context, calls `llm_client.explain_entity()`
- [ ] `explain_doctor(doctor_id, state)` — builds rich context, calls `llm_client.explain_entity()`
- [ ] `_build_patient_context_dict(patient_id, state)` — extracts: patient fields, assigned doctor name, ward occupancy, recent events for this patient
- [ ] `_build_doctor_context_dict(doctor_id, state)` — extracts: doctor fields, names of assigned patients and their severity, recent decision events
- [ ] `_build_state_summary(state)` — one-paragraph hospital summary string

**Done when:** `explain_patient(1, mock_state)` returns a string of 2-4 sentences that mentions the patient ID and at least one specific data point from the state.

---

## Phase 6 — Integration Tests (No Real Agent 1)

Create `backend/tests/test_llm_standalone.py`:

- [ ] Test: `doctor_decide()` with mock context → returns DoctorDecision with target_patient_id in candidate list
- [ ] Test: `patient_reevaluate()` with mock context → returns PatientUpdate with valid condition
- [ ] Test: `explain_event()` with mock event → returns non-empty string
- [ ] Test: malformed LLM response → parser falls back, does not raise
- [ ] Test: LLM timeout (mock `_call_llm` to sleep 5s) → fallback returned within 3.5s
- [ ] Test: trigger guard allows only 3 LLM calls per tick regardless of how many agents request it
- [ ] Test: doctor cooldown — same doctor_id blocked for 3 ticks after first call

**Done when:** All tests pass with `pytest tests/test_llm_standalone.py`.

---

## Phase 7 — Live API Smoke Test

- [ ] Set `ANTHROPIC_API_KEY` in `.env`
- [ ] Run `python -m llm.smoke_test` (create this file):
  ```python
  # backend/llm/smoke_test.py
  import asyncio
  from llm.client import AnthropicLLMClient
  from config import load_config
  # Build mock contexts and call each method once
  # Print results
  ```
- [ ] `doctor_decide()` returns plausible JSON — correct patient chosen for critical case
- [ ] `patient_reevaluate()` returns `worsening` for a critical patient who has been waiting 8 ticks
- [ ] `explain_event()` returns a coherent sentence < 50 words
- [ ] `explain_entity()` returns 2-3 sentence paragraph with specific numbers

**Done when:** All four calls succeed with real API. Print and visually inspect outputs.

---

## Phase 8 — Final Verification Checklist

- [ ] `from llm import AnthropicLLMClient, LLMTriggerGuard, ExplainerService` works
- [ ] `AnthropicLLMClient` implements `LLMInterface` protocol (has `doctor_decide`, `patient_reevaluate`, `explain_event`)
- [ ] All LLM calls have 3-second hard timeout via `asyncio.wait_for`
- [ ] All failures are logged, not raised (callers receive fallback results)
- [ ] `AnthropicLLMClient.stats` property returns `total_requests`, `fallback_count`, `fallback_rate`
- [ ] No API key hardcoded anywhere
- [ ] Model defaults to `claude-haiku-4-5-20251001` (cheap + fast)
- [ ] JSON extraction handles markdown-fenced code blocks from LLM responses

---

## Success Criteria

| Criterion | Signal | Target |
|-----------|--------|--------|
| Doctor decision — valid ID | `doctor_decide()` always returns an ID present in candidates | Must pass |
| Doctor decision — quality | For a critical vs low severity choice, LLM picks critical | Must pass |
| Patient update — valid fields | `condition` is always one of `stable/worsening/improving` | Must pass |
| Timeout protection | Any LLM call > 3s triggers fallback, doesn't hang simulation | Must pass |
| Rate limit retry | On `RateLimitError`, backs off and retries up to 2× | Must pass |
| Parse robustness | Markdown-fenced JSON correctly extracted | Must pass |
| Fallback completeness | `fallback_used=True` on any failure path | Must pass |
| Trigger throttling | Never more than `GLOBAL_CALLS_PER_TICK_LIMIT` calls per tick | Must pass |
| Explanation quality | 2-3 sentences, references specific IDs and numbers | Nice to have |
| Cost per 30-min demo | < $1.00 total with haiku at surge rate | Nice to have |

---

## Integration Handoff Notes

When integrating with Agent 1 (post-merge):
1. `AnthropicLLMClient` should be passed as `llm_callback` to `SimulationEngine(config, llm_callback=client)`
2. The `LLMTriggerGuard` instance should live inside `patient.py` and `doctor.py` — or Agent 2 can export it and Agent 1 imports it. Coordinate with Agent 1 on ownership.
3. `ExplainerService` is consumed by Agent 3's WebSocket handler — ensure `explain_patient(patient_id, state: SimulationState)` accepts the real `SimulationState` type, not a dict.
4. If Agent 1's `SimulationState` field names differ from data-contracts.md, `ExplainerService._build_*_context_dict` methods need updating.

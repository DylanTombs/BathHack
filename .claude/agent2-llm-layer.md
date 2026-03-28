# Agent 2 — LLM Integration Layer

**Branch:** `feature/llm-layer`
**Owns:** `backend/llm/`
**Depends on:** Data contracts only. Agent 2 works against the `LLMInterface` protocol and `types.py` — mock the simulation engine.
**Progress file:** `.claude/progress-agent2.md`

---

## Mission

Build the LLM brain layer that gives agents intelligence. This module:
1. Wraps the Anthropic API with retry logic, cost controls, and fallbacks
2. Implements three core LLM capabilities: doctor decisions, patient reevaluation, and event explanation
3. Implements trigger logic so the LLM is called selectively (not every tick)
4. Generates natural-language explanations that appear in the UI event log

This module must be **injectable** into the simulation engine via the `LLMInterface` protocol — Agent 1's `SimulationEngine` accepts it as `llm_callback`. The integration happens at the Agent 3 level after merge.

---

## File Structure

```
backend/llm/
├── __init__.py       # exports AnthropicLLMClient, LLMTriggerGuard
├── client.py         # AnthropicLLMClient — core API wrapper
├── triggers.py       # LLMTriggerGuard — decides when to call LLM
├── prompts.py        # All prompt templates (no logic, just strings)
└── explainer.py      # ExplainerService — on-demand explanation endpoint
```

---

## `client.py` — Core LLM Wrapper

```python
import anthropic
import asyncio
import logging
import json
from typing import Optional

from simulation.types import (
    DoctorContext, DoctorDecision,
    PatientContext, PatientUpdate,
    SimEvent,
)
from llm.prompts import (
    build_doctor_decision_prompt,
    build_patient_reeval_prompt,
    build_event_explanation_prompt,
    build_explain_entity_prompt,
)

logger = logging.getLogger(__name__)

class AnthropicLLMClient:
    """
    Implements the LLMInterface protocol.
    Wraps anthropic.AsyncAnthropic with:
      - JSON response parsing + validation
      - Exponential backoff retry (max 2 retries for hackathon speed)
      - Hard timeout per call (3 seconds — don't block simulation)
      - Graceful fallback to rule-based on any failure
      - Request counting for cost awareness
    """

    MAX_TOKENS_DECISION = 256     # small structured JSON
    MAX_TOKENS_EXPLANATION = 512  # paragraph of natural language
    TIMEOUT_SECONDS = 3.0         # simulation ticks can't wait long
    MAX_RETRIES = 2

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._request_count = 0
        self._fallback_count = 0

    # ── Core LLM calls ────────────────────────────────────────────────────────

    async def doctor_decide(self, context: DoctorContext) -> DoctorDecision:
        """
        Ask the LLM which patient the doctor should treat next.
        Returns a DoctorDecision with structured JSON from LLM.
        Falls back to rule-based (highest severity FIFO) on any error.
        """
        prompt = build_doctor_decision_prompt(context)
        raw = await self._call_with_fallback(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS_DECISION,
            fallback_fn=lambda: self._rule_based_doctor_fallback(context),
        )
        if raw is None:
            return self._rule_based_doctor_fallback(context)
        return self._parse_doctor_decision(raw, context)

    async def patient_reevaluate(self, context: PatientContext) -> PatientUpdate:
        """
        Ask the LLM to reassess a patient's condition.
        Falls back to keeping current condition unchanged.
        """
        prompt = build_patient_reeval_prompt(context)
        raw = await self._call_with_fallback(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS_DECISION,
            fallback_fn=lambda: self._rule_based_patient_fallback(context),
        )
        if raw is None:
            return self._rule_based_patient_fallback(context)
        return self._parse_patient_update(raw, context)

    async def explain_event(self, event: SimEvent) -> str:
        """
        Generate a natural-language explanation for an event.
        Used to populate event.llm_explanation in the event log.
        """
        prompt = build_event_explanation_prompt(event)
        raw = await self._call_with_fallback(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS_EXPLANATION,
            fallback_fn=lambda: event.raw_description,
        )
        return raw if isinstance(raw, str) else event.raw_description

    async def explain_entity(self, entity_type: str, entity_id: int,
                              state_snapshot: dict) -> str:
        """
        On-demand explanation when user clicks 'Explain' on a patient/doctor.
        Returns a paragraph-length natural language explanation.
        """
        prompt = build_explain_entity_prompt(entity_type, entity_id, state_snapshot)
        result = await self._call_llm(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS_EXPLANATION,
        )
        return result or f"Unable to generate explanation for {entity_type} #{entity_id}."

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _call_with_fallback(self, prompt: str, max_tokens: int, fallback_fn):
        """
        Attempt LLM call. On timeout/error, call fallback_fn and return its result.
        Logs all failures with request count for debugging.
        """
        try:
            result = await asyncio.wait_for(
                self._call_llm(prompt, max_tokens),
                timeout=self.TIMEOUT_SECONDS,
            )
            self._request_count += 1
            return result
        except asyncio.TimeoutError:
            logger.warning(f"LLM timeout after {self.TIMEOUT_SECONDS}s — using fallback")
            self._fallback_count += 1
            return fallback_fn()
        except Exception as e:
            logger.error(f"LLM error: {e} — using fallback")
            self._fallback_count += 1
            return fallback_fn()

    async def _call_llm(self, prompt: str, max_tokens: int) -> Optional[str]:
        """Direct API call. Returns raw text content."""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    system=SYSTEM_PROMPT,
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    raise
            except anthropic.APIError as e:
                raise

    # ── JSON Parsers ──────────────────────────────────────────────────────────

    def _parse_doctor_decision(self, raw: str, context: DoctorContext) -> DoctorDecision:
        """
        Parse LLM JSON response into DoctorDecision.
        Expected shape: {"target_patient_id": 12, "reason": "..."}
        Validates patient_id is in context.available_patients.
        Falls back to rule-based if JSON malformed or patient_id invalid.
        """
        try:
            # Extract JSON even if LLM wraps it in markdown fences
            text = raw.strip()
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            data = json.loads(text)
            pid = int(data["target_patient_id"])
            valid_ids = {p.id for p in context.available_patients}
            if pid not in valid_ids:
                raise ValueError(f"patient_id {pid} not in candidates")
            return DoctorDecision(
                target_patient_id=pid,
                reason=data.get("reason", "LLM decision"),
                confidence=float(data.get("confidence", 0.8)),
                fallback_used=False,
            )
        except Exception as e:
            logger.warning(f"Failed to parse doctor decision: {e} | raw={raw[:200]}")
            return self._rule_based_doctor_fallback(context)

    def _parse_patient_update(self, raw: str, context: PatientContext) -> PatientUpdate:
        """
        Parse LLM JSON response into PatientUpdate.
        Expected shape: {"condition": "worsening", "priority_change": true, "reason": "..."}
        """
        VALID_CONDITIONS = {"stable", "worsening", "improving"}
        VALID_SEVERITIES = {"low", "medium", "critical", None}
        try:
            text = raw.strip()
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            data = json.loads(text)
            condition = data.get("condition", context.patient.condition)
            severity = data.get("new_severity", None)
            if condition not in VALID_CONDITIONS:
                condition = context.patient.condition
            if severity not in VALID_SEVERITIES:
                severity = None
            return PatientUpdate(
                patient_id=context.patient.id,
                new_condition=condition,
                new_severity=severity,
                priority_change=bool(data.get("priority_change", False)),
                reason=data.get("reason", "LLM reevaluation"),
                fallback_used=False,
            )
        except Exception as e:
            logger.warning(f"Failed to parse patient update: {e}")
            return self._rule_based_patient_fallback(context)

    # ── Rule-based fallbacks ──────────────────────────────────────────────────

    def _rule_based_doctor_fallback(self, context: DoctorContext) -> DoctorDecision:
        if not context.available_patients:
            return DoctorDecision(target_patient_id=-1, reason="No patients", confidence=1.0, fallback_used=True)
        PRIORITY = {"critical": 2, "medium": 1, "low": 0}
        best = max(context.available_patients, key=lambda p: (PRIORITY[p.severity], p.wait_time_ticks))
        return DoctorDecision(
            target_patient_id=best.id,
            reason=f"Rule-based: highest severity ({best.severity}) patient",
            confidence=1.0,
            fallback_used=True,
        )

    def _rule_based_patient_fallback(self, context: PatientContext) -> PatientUpdate:
        return PatientUpdate(
            patient_id=context.patient.id,
            new_condition=context.patient.condition,
            new_severity=None,
            priority_change=False,
            reason="Rule-based: no change",
            fallback_used=True,
        )

    @property
    def stats(self) -> dict:
        return {
            "total_requests": self._request_count,
            "fallback_count": self._fallback_count,
            "fallback_rate": self._fallback_count / max(1, self._request_count + self._fallback_count),
        }


SYSTEM_PROMPT = """You are the decision-making core of a hospital simulation system.
You make clinical triage decisions and assess patient conditions.
Always respond with valid JSON only — no markdown, no explanation outside the JSON.
Be concise. Prioritise patient safety and resource efficiency."""
```

---

## `prompts.py` — All Prompt Templates

```python
from simulation.types import DoctorContext, PatientContext, SimEvent


def build_doctor_decision_prompt(ctx: DoctorContext) -> str:
    patients_str = "\n".join([
        f"  - Patient #{p.id} | {p.name} | Severity: {p.severity} | "
        f"Condition: {p.condition} | Diagnosis: {p.diagnosis} | "
        f"Waiting: {p.wait_time_ticks} ticks | Age: {p.age}"
        for p in ctx.available_patients
    ])
    return f"""You are Dr. {ctx.doctor.name} ({ctx.doctor.specialty} specialist).
Hospital status at tick {ctx.current_tick}:
- ICU full: {ctx.icu_is_full}
- General ward full: {ctx.general_ward_is_full}
- Your current workload: {ctx.doctor.workload}
- Your current patients: {len(ctx.doctor.assigned_patient_ids)}

Patients waiting for assignment:
{patients_str}

Choose which patient to treat next. Respond with JSON only:
{{"target_patient_id": <id>, "reason": "<one sentence clinical rationale>", "confidence": <0.0-1.0>}}"""


def build_patient_reeval_prompt(ctx: PatientContext) -> str:
    return f"""You are assessing the current condition of a hospital patient.

Patient #{ctx.patient.id} — {ctx.patient.name}
- Age: {ctx.patient.age}
- Diagnosis: {ctx.patient.diagnosis}
- Severity: {ctx.patient.severity}
- Current condition: {ctx.patient.condition}
- Location: {ctx.patient.location}
- Ticks waiting (unattended): {ctx.ticks_waiting}
- Ward occupancy: {ctx.ward_occupancy_pct:.0f}%
- Doctor available: {ctx.doctor_available}
- Current tick: {ctx.current_tick}

Based on this context, assess whether the patient's condition has changed.
Consider: long wait times worsen outcomes; critical patients deteriorate faster without treatment.

Respond with JSON only:
{{"condition": "<stable|worsening|improving>", "new_severity": "<low|medium|critical|null>", "priority_change": <true|false>, "reason": "<one sentence>"}}

Use null for new_severity if severity is unchanged."""


def build_event_explanation_prompt(event: SimEvent) -> str:
    return f"""Generate a brief, natural-language explanation for this hospital simulation event.
Write as if explaining to a hospital administrator watching a live dashboard.
Be specific, factual, and under 40 words.

Event type: {event.event_type}
Entity: {event.entity_type} #{event.entity_id}
Raw description: {event.raw_description}
Severity: {event.severity}

Respond with plain text only — no JSON, no lists."""


def build_explain_entity_prompt(entity_type: str, entity_id: int, state: dict) -> str:
    entity_data = state.get(f"{entity_type}s_by_id", {}).get(str(entity_id), {})
    return f"""Explain the current situation of this hospital {entity_type} to a clinician.
Be analytical. Reference specific numbers. Write 2-3 sentences.

{entity_type.title()} #{entity_id} data:
{entity_data}

Simulation context: {state.get('summary', 'No summary available')}

Respond with plain text only."""
```

---

## `triggers.py` — LLM Trigger Guard

```python
class LLMTriggerGuard:
    """
    Stateful guard that decides when LLM calls are appropriate.
    Prevents calling LLM every tick (expensive + slow).
    Tracks per-agent cooldowns and global rate limits.
    """

    # These can be tuned during the hackathon
    DOCTOR_COOLDOWN_TICKS = 3
    PATIENT_COOLDOWN_TICKS = 5
    GLOBAL_CALLS_PER_TICK_LIMIT = 3   # max concurrent LLM calls per tick
    CRITICAL_WAIT_THRESHOLD = 4        # ticks before forced LLM check

    def __init__(self):
        self._doctor_last_llm: dict[int, int] = {}    # doctor_id → last tick called
        self._patient_last_llm: dict[int, int] = {}   # patient_id → last tick called
        self._calls_this_tick = 0
        self._current_tick = 0

    def new_tick(self, tick: int) -> None:
        """Call at start of each tick to reset per-tick counter."""
        self._current_tick = tick
        self._calls_this_tick = 0

    def should_call_llm_for_doctor(
        self, doctor_id: int, context: 'DoctorContext'
    ) -> bool:
        """
        True when ALL of:
        - Not over global call limit this tick
        - Doctor cooldown elapsed
        AND ANY of:
        - ≥2 critical patients waiting
        - ICU full AND critical patient in general ward
        - workload == 'overwhelmed'
        """
        if self._calls_this_tick >= self.GLOBAL_CALLS_PER_TICK_LIMIT:
            return False
        last = self._doctor_last_llm.get(doctor_id, -999)
        if self._current_tick - last < self.DOCTOR_COOLDOWN_TICKS:
            return False
        critical_count = sum(1 for p in context.available_patients if p.severity == "critical")
        if critical_count >= 2:
            return True
        if context.icu_is_full and any(
            p.severity == "critical" and p.location == "general_ward"
            for p in context.available_patients
        ):
            return True
        if context.doctor.workload == "overwhelmed":
            return True
        return False

    def should_call_llm_for_patient(
        self, patient_id: int, context: 'PatientContext'
    ) -> bool:
        """
        True when ALL of:
        - Not over global call limit this tick
        - Patient cooldown elapsed
        AND ANY of:
        - Patient has been waiting > CRITICAL_WAIT_THRESHOLD ticks
        - Patient's condition is 'worsening'
        - Tick is a multiple of PATIENT_COOLDOWN_TICKS (periodic check)
        """
        if self._calls_this_tick >= self.GLOBAL_CALLS_PER_TICK_LIMIT:
            return False
        last = self._patient_last_llm.get(patient_id, -999)
        if self._current_tick - last < self.PATIENT_COOLDOWN_TICKS:
            return False
        if context.ticks_waiting > self.CRITICAL_WAIT_THRESHOLD:
            return True
        if context.patient.condition == "worsening":
            return True
        if self._current_tick % self.PATIENT_COOLDOWN_TICKS == 0:
            return True
        return False

    def record_doctor_call(self, doctor_id: int) -> None:
        self._doctor_last_llm[doctor_id] = self._current_tick
        self._calls_this_tick += 1

    def record_patient_call(self, patient_id: int) -> None:
        self._patient_last_llm[patient_id] = self._current_tick
        self._calls_this_tick += 1
```

---

## `explainer.py` — On-Demand Explanation Service

```python
class ExplainerService:
    """
    Handles on-demand 'Explain' requests from the frontend.
    Called by Agent 3's WebSocket handler when it receives an
    explain_patient or explain_doctor command.
    """

    def __init__(self, llm_client: AnthropicLLMClient): ...

    async def explain_patient(self, patient_id: int, state: SimulationState) -> str:
        """
        Build rich context dict from state, call llm_client.explain_entity().
        Includes: patient history, ward status, assigned doctor, recent events.
        """

    async def explain_doctor(self, doctor_id: int, state: SimulationState) -> str:
        """
        Build context: doctor's current patients, workload, recent decisions.
        """

    def _build_patient_context_dict(self, patient_id: int, state: SimulationState) -> dict:
        """Extract and flatten all relevant patient info into a dict for the prompt."""

    def _build_doctor_context_dict(self, doctor_id: int, state: SimulationState) -> dict:
        """Extract and flatten all relevant doctor info."""

    def _build_state_summary(self, state: SimulationState) -> str:
        """
        One-paragraph summary of hospital status for context:
        'Tick 42: Hospital under surge. ICU at 100%, general ward 90%.
         12 patients in queue, 2 critical unattended. 4 doctors active.'
        """
```

---

## `__init__.py`

```python
from llm.client import AnthropicLLMClient
from llm.triggers import LLMTriggerGuard
from llm.explainer import ExplainerService

__all__ = ["AnthropicLLMClient", "LLMTriggerGuard", "ExplainerService"]
```

---

## LLM Call Budget

For a hackathon demo running at 1 tick/second:

| Call type | Frequency | Tokens/call | Cost est. (haiku) |
|-----------|-----------|-------------|-------------------|
| Doctor decision | ~2/tick during surge | ~300 in + 50 out | ~$0.0001 |
| Patient reeval | ~2/tick (throttled) | ~200 in + 80 out | ~$0.0001 |
| Event explanation | ~3/tick | ~100 in + 50 out | ~$0.00005 |
| On-demand explain | User-triggered | ~400 in + 150 out | ~$0.0002 |

**Total for 30-min demo at surge rate: ~$0.50 max.** Use `claude-haiku-4-5-20251001` throughout.

---

## Testing Without Agent 1

Create a `tests/test_llm.py` that builds mock contexts directly:

```python
from simulation.types import DoctorContext, Doctor, Patient
from llm.client import AnthropicLLMClient

async def test_doctor_decide():
    client = AnthropicLLMClient(api_key="test", model="claude-haiku-4-5-20251001")
    context = DoctorContext(
        doctor=Doctor(id=1, name="Dr. Test", assigned_patient_ids=[], capacity=3,
                      workload="heavy", specialty="General", grid_x=0, grid_y=0,
                      is_available=True, decisions_made=5),
        available_patients=[
            Patient(id=10, name="Patient #10", severity="critical", condition="worsening",
                    location="waiting", assigned_doctor_id=None, arrived_at_tick=1,
                    treatment_started_tick=None, treatment_duration_ticks=8,
                    wait_time_ticks=5, age=72, diagnosis="Cardiac arrest",
                    grid_x=1, grid_y=1),
        ],
        icu_is_full=True,
        general_ward_is_full=False,
        current_tick=42,
    )
    decision = await client.doctor_decide(context)
    assert decision.target_patient_id == 10
    assert len(decision.reason) > 10
```

---

## Integration Handoff to Agent 3

After merge, Agent 3 instantiates:

```python
from llm import AnthropicLLMClient, LLMTriggerGuard, ExplainerService
from config import load_config

config = load_config()
llm_client = AnthropicLLMClient(config.anthropic_api_key, config.llm_model)
explainer = ExplainerService(llm_client)

# Inject into engine
engine = SimulationEngine(config, llm_callback=llm_client)
```

The `LLMTriggerGuard` is used inside `patient.py` and `doctor.py` — Agent 2 should export it cleanly so Agent 1 can import it post-merge without changes.

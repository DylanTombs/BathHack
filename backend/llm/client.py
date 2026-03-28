"""
AnthropicLLMClient — Core LLM wrapper implementing the LLMInterface protocol.

Responsibilities:
  - Wraps anthropic.AsyncAnthropic with retry, timeout, and fallback logic
  - Parses structured JSON responses for doctor/patient decisions
  - Falls back gracefully to rule-based logic on any failure
  - Tracks request / fallback counts for cost monitoring

This class is injected into SimulationEngine as `llm_callback`.

Usage:
    client = AnthropicLLMClient(api_key="sk-ant-...", model="claude-haiku-4-5-20251001")
    decision = await client.doctor_decide(context)
    update   = await client.patient_reevaluate(context)
    text     = await client.explain_event(event)
    text     = await client.explain_entity("patient", 12, state_snapshot)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Optional

import anthropic

from simulation.types import (
    DoctorContext,
    DoctorDecision,
    PatientContext,
    PatientUpdate,
    SimEvent,
)
from llm.prompts import (
    build_doctor_decision_prompt,
    build_event_explanation_prompt,
    build_explain_entity_prompt,
    build_patient_reeval_prompt,
)

logger = logging.getLogger(__name__)

# ── System prompt (shared by all calls) ───────────────────────────────────────
SYSTEM_PROMPT = (
    "You are the decision-making core of a hospital simulation system. "
    "You make clinical triage decisions and assess patient conditions. "
    "Always respond with the exact format requested — valid JSON for structured outputs, "
    "plain text for explanations. Never add markdown formatting, extra commentary, "
    "or text outside the requested format. Prioritise patient safety and resource efficiency."
)

# ── Valid constant sets for validation ────────────────────────────────────────
_VALID_CONDITIONS = frozenset({"stable", "worsening", "improving"})
_VALID_SEVERITIES = frozenset({"low", "medium", "critical"})


class AnthropicLLMClient:
    """
    Implements the LLMInterface protocol for use with SimulationEngine.

    All public async methods are safe to call and will NEVER raise — they
    return fallback results instead, logging the error. This keeps the
    simulation running even when the LLM is unavailable.
    """

    MAX_TOKENS_DECISION = 256      # small structured JSON response
    MAX_TOKENS_EXPLANATION = 512   # paragraph of natural language
    TIMEOUT_SECONDS = 3.0          # simulation ticks can't wait long
    MAX_RETRIES = 2                # retries only on RateLimitError

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._request_count = 0
        self._fallback_count = 0

    # ── Public LLM interface (safe — never raises) ────────────────────────────

    async def doctor_decide(self, context: DoctorContext) -> DoctorDecision:
        """
        Ask the LLM which patient the doctor should treat next.

        Returns a DoctorDecision with a patient id drawn from
        context.available_patients. Falls back to highest-severity FIFO
        on any LLM failure, timeout, or parse error.
        """
        if not context.available_patients:
            return DoctorDecision(
                target_patient_id=-1,
                reason="No patients waiting for assignment",
                confidence=1.0,
                fallback_used=True,
            )

        prompt = build_doctor_decision_prompt(context)
        raw = await self._call_with_fallback(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS_DECISION,
            fallback_fn=lambda: None,
        )
        if raw is None:
            return self._rule_based_doctor_fallback(context)
        return self._parse_doctor_decision(raw, context)

    async def patient_reevaluate(self, context: PatientContext) -> PatientUpdate:
        """
        Ask the LLM to reassess a patient's condition.

        Returns a PatientUpdate. Falls back to a no-change update on
        any LLM failure, timeout, or parse error.
        """
        prompt = build_patient_reeval_prompt(context)
        raw = await self._call_with_fallback(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS_DECISION,
            fallback_fn=lambda: None,
        )
        if raw is None:
            return self._rule_based_patient_fallback(context)
        return self._parse_patient_update(raw, context)

    async def explain_event(self, event: SimEvent) -> str:
        """
        Generate a natural-language explanation for a simulation event.

        Used to populate SimEvent.llm_explanation in the event log.
        Returns the raw_description fallback on any failure.
        """
        prompt = build_event_explanation_prompt(event)
        raw = await self._call_with_fallback(
            prompt=prompt,
            max_tokens=self.MAX_TOKENS_EXPLANATION,
            fallback_fn=lambda: event.raw_description,
        )
        # Ensure we always return a string
        return raw if isinstance(raw, str) and raw.strip() else event.raw_description

    async def explain_entity(
        self,
        entity_type: str,
        entity_id: int,
        state_snapshot: dict,
    ) -> str:
        """
        On-demand explanation when a user clicks 'Explain' on a patient/doctor.

        Returns a paragraph-length natural language explanation.
        Does not use _call_with_fallback — this is user-triggered and
        we let it fail visibly with a friendly message instead.
        """
        prompt = build_explain_entity_prompt(entity_type, entity_id, state_snapshot)
        try:
            result = await asyncio.wait_for(
                self._call_llm(prompt, self.MAX_TOKENS_EXPLANATION),
                timeout=self.TIMEOUT_SECONDS * 2,  # user-triggered: slightly more patience
            )
            self._request_count += 1
            return result or f"Unable to generate explanation for {entity_type} #{entity_id}."
        except asyncio.TimeoutError:
            logger.warning(
                "explain_entity timeout for %s #%d", entity_type, entity_id
            )
            self._fallback_count += 1
            return f"Explanation for {entity_type} #{entity_id} timed out. Please try again."
        except Exception as exc:
            logger.error(
                "explain_entity error for %s #%d: %s", entity_type, entity_id, exc
            )
            self._fallback_count += 1
            return f"Unable to generate explanation for {entity_type} #{entity_id}."

    # ── Internal: API call layer ──────────────────────────────────────────────

    async def _call_with_fallback(
        self,
        prompt: str,
        max_tokens: int,
        fallback_fn: Callable[[], Any],
    ) -> Any:
        """
        Attempt an LLM call with timeout protection.

        On any exception (timeout, API error, etc.) the fallback_fn is called
        and its result returned instead. All failures are logged.
        """
        try:
            result = await asyncio.wait_for(
                self._call_llm(prompt, max_tokens),
                timeout=self.TIMEOUT_SECONDS,
            )
            self._request_count += 1
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "LLM call timed out after %.1fs — using fallback",
                self.TIMEOUT_SECONDS,
            )
            self._fallback_count += 1
            return fallback_fn()
        except Exception as exc:
            logger.error("LLM call failed: %s — using fallback", exc)
            self._fallback_count += 1
            return fallback_fn()

    async def _call_llm(self, prompt: str, max_tokens: int) -> Optional[str]:
        """
        Direct API call with exponential backoff retry on RateLimitError.

        Retries up to MAX_RETRIES times with 0.5s / 1.0s delays.
        Other API errors are raised immediately.
        """
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                if attempt < self.MAX_RETRIES:
                    backoff = 0.5 * (2 ** attempt)  # 0.5s, 1.0s
                    logger.warning(
                        "Rate limit hit (attempt %d/%d), backing off %.1fs",
                        attempt + 1, self.MAX_RETRIES + 1, backoff,
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise
            except anthropic.APIStatusError as exc:
                # Re-raise all non-rate-limit API errors immediately
                raise exc
        return None  # unreachable but satisfies type checker

    # ── JSON Parsers ──────────────────────────────────────────────────────────

    def _parse_doctor_decision(
        self, raw: str, context: DoctorContext
    ) -> DoctorDecision:
        """
        Parse the LLM JSON response into a DoctorDecision.

        Expected JSON shape:
            {"target_patient_id": 12, "reason": "...", "confidence": 0.9}

        Handles:
          - Clean JSON
          - JSON wrapped in markdown fences (```json ... ```)
          - Missing optional fields (confidence defaults to 0.8)
          - Invalid patient_id (not in available_patients) → fallback
          - Malformed JSON → fallback
        """
        try:
            data = _extract_json(raw)
            pid = int(data["target_patient_id"])

            valid_ids = {p.id for p in context.available_patients}
            if pid not in valid_ids:
                logger.warning(
                    "LLM returned patient_id %d not in candidates %s — falling back",
                    pid, sorted(valid_ids),
                )
                return self._rule_based_doctor_fallback(context)

            return DoctorDecision(
                target_patient_id=pid,
                reason=str(data.get("reason", "LLM triage decision")),
                confidence=_safe_float(data.get("confidence", 0.8), 0.0, 1.0),
                fallback_used=False,
            )
        except Exception as exc:
            logger.warning(
                "Failed to parse doctor decision: %s | raw=%r",
                exc, raw[:200],
            )
            return self._rule_based_doctor_fallback(context)

    def _parse_patient_update(
        self, raw: str, context: PatientContext
    ) -> PatientUpdate:
        """
        Parse the LLM JSON response into a PatientUpdate.

        Expected JSON shape:
            {
                "condition": "worsening",
                "new_severity": "critical",   # or null
                "priority_change": true,
                "reason": "..."
            }

        Handles:
          - Clean JSON and markdown-fenced JSON
          - Invalid condition value → preserved from context
          - Invalid severity value or null → no severity change
          - Malformed JSON → fallback
        """
        try:
            data = _extract_json(raw)

            raw_condition = data.get("condition", context.patient.condition)
            condition = (
                raw_condition
                if raw_condition in _VALID_CONDITIONS
                else context.patient.condition
            )

            raw_severity = data.get("new_severity")
            if raw_severity == "null" or raw_severity is None:
                new_severity = None
            elif raw_severity in _VALID_SEVERITIES:
                new_severity = raw_severity
            else:
                logger.debug(
                    "Invalid new_severity %r from LLM — treating as no change",
                    raw_severity,
                )
                new_severity = None

            return PatientUpdate(
                patient_id=context.patient.id,
                new_condition=condition,
                new_severity=new_severity,
                priority_change=bool(data.get("priority_change", False)),
                reason=str(data.get("reason", "LLM reevaluation")),
                fallback_used=False,
            )
        except Exception as exc:
            logger.warning(
                "Failed to parse patient update: %s | raw=%r",
                exc, raw[:200],
            )
            return self._rule_based_patient_fallback(context)

    # ── Rule-based fallbacks ──────────────────────────────────────────────────

    def _rule_based_doctor_fallback(self, context: DoctorContext) -> DoctorDecision:
        """
        Select patient by highest severity then longest wait time.
        Deterministic and always returns a valid patient from the list.
        """
        if not context.available_patients:
            return DoctorDecision(
                target_patient_id=-1,
                reason="No patients available",
                confidence=1.0,
                fallback_used=True,
            )

        _severity_rank = {"critical": 2, "medium": 1, "low": 0}
        best = max(
            context.available_patients,
            key=lambda p: (_severity_rank.get(p.severity, 0), p.wait_time_ticks),
        )
        return DoctorDecision(
            target_patient_id=best.id,
            reason=(
                f"Rule-based triage: highest severity ({best.severity}), "
                f"waiting {best.wait_time_ticks} ticks"
            ),
            confidence=1.0,
            fallback_used=True,
        )

    def _rule_based_patient_fallback(self, context: PatientContext) -> PatientUpdate:
        """Return a no-change update — preserve current condition."""
        return PatientUpdate(
            patient_id=context.patient.id,
            new_condition=context.patient.condition,
            new_severity=None,
            priority_change=False,
            reason="Rule-based: condition unchanged (LLM unavailable)",
            fallback_used=True,
        )

    # ── Stats / observability ─────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """
        Return counters for cost monitoring and debugging.
        Exposed on the /api/llm/stats endpoint by Agent 3.
        """
        total = self._request_count + self._fallback_count
        return {
            "total_requests": self._request_count,
            "fallback_count": self._fallback_count,
            "fallback_rate": self._fallback_count / max(1, total),
            "model": self._model,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """
    Extract and parse JSON from an LLM response, handling:
      - Clean JSON strings
      - JSON wrapped in ```json ... ``` or ``` ... ``` markdown fences
      - Leading/trailing whitespace

    Raises json.JSONDecodeError on truly unparseable content.
    """
    text = raw.strip()

    # Strip markdown code fences if present (```json\n{...}\n``` or ```\n{...}\n```)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    return json.loads(text)


def _safe_float(value: Any, lo: float, hi: float) -> float:
    """
    Convert value to float clamped to [lo, hi].
    Returns the midpoint on conversion failure.
    """
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return (lo + hi) / 2

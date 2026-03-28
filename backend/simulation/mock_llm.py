"""
MockLLMInterface — stub that returns plausible-looking decisions without any API call.

Used for:
  - Standalone testing of the simulation engine (python -m simulation.engine)
  - Unit tests in CI
  - Development without an Anthropic API key
"""
from __future__ import annotations

import random

from simulation.types import (
    DoctorContext,
    DoctorDecision,
    PatientContext,
    PatientUpdate,
    SimEvent,
    ArrivalContext,
    PatientSpec,
)


class MockLLMInterface:
    """
    Implements the LLMInterface Protocol without calling any external API.
    All methods are async to match the real interface.

    Behaviour:
      doctor_decide  — picks the highest-severity patient (same as rule-based),
                       but returns a structured DoctorDecision with a mock reason.
      patient_reevaluate — returns the patient's current state unchanged.
      explain_event  — returns a simple prefix + raw_description.
    """

    async def doctor_decide(self, context: DoctorContext) -> DoctorDecision:
        """
        Pick highest severity patient (mirroring rule-based logic).
        Returns a DoctorDecision with fallback_used=True to indicate mock.
        """
        _rank = {"critical": 2, "medium": 1, "low": 0}
        patients = context.available_patients
        if not patients:
            # Shouldn't happen, but guard anyway
            raise ValueError("doctor_decide called with no available patients")

        best = max(patients, key=lambda p: (_rank[p.severity], -p.arrived_at_tick))

        icu_note = " (ICU is full)" if context.icu_is_full else ""
        return DoctorDecision(
            target_patient_id=best.id,
            reason=(
                f"[MOCK] {best.name} has {best.severity} severity{icu_note}; "
                f"treating immediately. Waited {best.wait_time_ticks} tick(s)."
            ),
            confidence=0.9,
            fallback_used=True,
        )

    async def patient_reevaluate(self, context: PatientContext) -> PatientUpdate:
        """
        Return current state unchanged — no mock condition adjustments.
        """
        p = context.patient
        return PatientUpdate(
            patient_id=p.id,
            new_condition=p.condition,
            new_severity=None,          # no change
            priority_change=False,
            reason=(
                f"[MOCK] {p.name} at tick {context.current_tick}: "
                f"condition={p.condition}, severity={p.severity}, "
                f"waited={context.ticks_waiting} tick(s)."
            ),
            fallback_used=True,
        )

    async def explain_event(self, event: SimEvent) -> str:
        """
        Return a simple explanation string prefixed with [MOCK].
        """
        return f"[MOCK] {event.raw_description}"

    async def generate_patient_batch(
        self,
        context: ArrivalContext,
        fallback_fn,
    ) -> list[PatientSpec]:
        """
        Time-of-day heuristic patient generation — no external API call.
        Used for tests and development without an API key.
        """
        from simulation.patient import _make_random_spec

        hour = context.hour_of_day
        if 0 <= hour < 5:
            count = random.randint(0, 1)
        elif 5 <= hour < 9:
            count = random.randint(1, 2)
        elif 9 <= hour < 17:
            count = random.randint(1, 3)
        elif 17 <= hour < 22:
            count = random.randint(2, 4)
        else:
            count = random.randint(1, 3)

        if context.surge_active:
            count = max(count, random.randint(3, 6))

        if context.surge_active:
            sev_pool = ["critical", "critical", "medium", "medium", "low"]
        elif 17 <= hour < 22 or (hour >= 22 or hour < 5):
            sev_pool = ["medium", "medium", "critical", "low"]
        else:
            sev_pool = ["low", "low", "low", "medium", "medium", "critical"]

        return [_make_random_spec(random.choice(sev_pool)) for _ in range(count)]

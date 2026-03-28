"""
Live API smoke test for the LLM integration layer.

Requires: ANTHROPIC_API_KEY set in environment (or .env file).
Run with: cd backend && python -m llm.smoke_test

Tests each LLM method once with realistic inputs and prints results.
Use this to validate the integration works end-to-end before the demo.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional for smoke test

from simulation.types import (
    Doctor,
    DoctorContext,
    Patient,
    PatientContext,
    SimEvent,
)
from llm.client import AnthropicLLMClient

# ── Test data ─────────────────────────────────────────────────────────────────

DOCTOR = Doctor(
    id=1,
    name="Dr. Patel",
    assigned_patient_ids=[],
    capacity=3,
    workload="heavy",
    specialty="ICU",
    grid_x=4.0,
    grid_y=2.5,
    is_available=True,
    decisions_made=14,
)

CRITICAL_PATIENT = Patient(
    id=10,
    name="Patient #10",
    severity="critical",
    condition="worsening",
    location="waiting",
    assigned_doctor_id=None,
    arrived_at_tick=1,
    treatment_started_tick=None,
    treatment_duration_ticks=8,
    wait_time_ticks=6,
    age=72,
    diagnosis="Cardiac arrest",
    grid_x=1.0,
    grid_y=1.0,
)

LOW_PATIENT = Patient(
    id=11,
    name="Patient #11",
    severity="low",
    condition="stable",
    location="waiting",
    assigned_doctor_id=None,
    arrived_at_tick=3,
    treatment_started_tick=None,
    treatment_duration_ticks=4,
    wait_time_ticks=2,
    age=32,
    diagnosis="Sprained ankle",
    grid_x=2.0,
    grid_y=1.0,
)

MEDIUM_PATIENT = Patient(
    id=12,
    name="Patient #12",
    severity="medium",
    condition="stable",
    location="general_ward",
    assigned_doctor_id=1,
    arrived_at_tick=5,
    treatment_started_tick=7,
    treatment_duration_ticks=6,
    wait_time_ticks=0,
    age=55,
    diagnosis="Appendicitis",
    grid_x=3.0,
    grid_y=5.0,
)

CRITICAL_WAITING_PATIENT = Patient(
    id=13,
    name="Patient #13",
    severity="critical",
    condition="worsening",
    location="waiting",
    assigned_doctor_id=None,
    arrived_at_tick=8,
    treatment_started_tick=None,
    treatment_duration_ticks=10,
    wait_time_ticks=8,
    age=67,
    diagnosis="Stroke",
    grid_x=1.5,
    grid_y=2.0,
)


# ── Smoke test runner ─────────────────────────────────────────────────────────

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
INFO = "\033[94mℹ\033[0m"


def _check(condition: bool, message: str) -> bool:
    status = PASS if condition else FAIL
    print(f"    {status} {message}")
    return condition


async def smoke_test_doctor_decide(client: AnthropicLLMClient) -> bool:
    print("\n─── Test 1: doctor_decide (critical vs low) ───")
    context = DoctorContext(
        doctor=DOCTOR,
        available_patients=[CRITICAL_PATIENT, LOW_PATIENT],
        icu_is_full=True,
        general_ward_is_full=False,
        current_tick=42,
    )

    t0 = time.time()
    decision = await client.doctor_decide(context)
    elapsed = time.time() - t0

    print(f"  {INFO} Result: patient_id={decision.target_patient_id}, "
          f"fallback={decision.fallback_used}, confidence={decision.confidence:.2f}")
    print(f"  {INFO} Reason: {decision.reason}")
    print(f"  {INFO} Elapsed: {elapsed:.2f}s")

    passed = all([
        _check(
            decision.target_patient_id in (10, 11),
            "target_patient_id is in candidate list",
        ),
        _check(
            decision.target_patient_id == 10 or decision.fallback_used,
            "critical patient selected (or fallback used)",
        ),
        _check(len(decision.reason) > 10, "reason is non-empty"),
        _check(0.0 <= decision.confidence <= 1.0, "confidence in [0, 1]"),
        _check(elapsed < 5.0, f"completed in < 5s (was {elapsed:.2f}s)"),
    ])
    return passed


async def smoke_test_patient_reevaluate(client: AnthropicLLMClient) -> bool:
    print("\n─── Test 2: patient_reevaluate (critical patient waiting 8 ticks) ───")
    context = PatientContext(
        patient=CRITICAL_WAITING_PATIENT,
        ticks_waiting=8,
        ward_occupancy_pct=90.0,
        doctor_available=False,
        current_tick=42,
    )

    t0 = time.time()
    update = await client.patient_reevaluate(context)
    elapsed = time.time() - t0

    print(f"  {INFO} Result: condition={update.new_condition}, severity={update.new_severity}, "
          f"priority_change={update.priority_change}, fallback={update.fallback_used}")
    print(f"  {INFO} Reason: {update.reason}")
    print(f"  {INFO} Elapsed: {elapsed:.2f}s")

    passed = all([
        _check(update.patient_id == 13, "patient_id correct"),
        _check(
            update.new_condition in ("stable", "worsening", "improving"),
            f"condition is valid (got {update.new_condition!r})",
        ),
        _check(
            update.new_severity in (None, "low", "medium", "critical"),
            f"new_severity is valid (got {update.new_severity!r})",
        ),
        _check(len(update.reason) > 5, "reason is non-empty"),
        _check(elapsed < 5.0, f"completed in < 5s (was {elapsed:.2f}s)"),
        # Clinical quality check: critical patient waiting 8 ticks should worsen
        _check(
            update.new_condition == "worsening" or update.fallback_used,
            "critical patient waiting 8 ticks assessed as worsening (or fallback)",
        ),
    ])
    return passed


async def smoke_test_explain_event(client: AnthropicLLMClient) -> bool:
    print("\n─── Test 3: explain_event ───")
    event = SimEvent(
        tick=42,
        event_type="doctor_decision",
        entity_id=1,
        entity_type="doctor",
        raw_description="Dr. Patel assigned to Patient #10 (cardiac arrest, critical)",
        llm_explanation=None,
        severity="critical",
    )

    t0 = time.time()
    explanation = await client.explain_event(event)
    elapsed = time.time() - t0

    word_count = len(explanation.split())
    print(f"  {INFO} Explanation ({word_count} words): {explanation}")
    print(f"  {INFO} Elapsed: {elapsed:.2f}s")

    passed = all([
        _check(len(explanation) > 20, "explanation is non-trivial"),
        _check(word_count <= 60, f"under 60 words (was {word_count})"),
        _check(elapsed < 5.0, f"completed in < 5s (was {elapsed:.2f}s)"),
    ])
    return passed


async def smoke_test_explain_entity(client: AnthropicLLMClient) -> bool:
    print("\n─── Test 4: explain_entity (patient) ───")
    state_snapshot = {
        "patients_by_id": {
            "10": {
                "id": 10,
                "name": "Patient #10",
                "age": 72,
                "diagnosis": "Cardiac arrest",
                "severity": "critical",
                "condition": "worsening",
                "location": "waiting",
                "assigned_doctor_id": None,
                "wait_time_ticks": 6,
                "treatment_started_tick": None,
            }
        },
        "summary": (
            "Tick 42: Scenario 'surge'. ICU at 100%, general ward at 90%. "
            "12 patients in queue, 3 critical unattended. "
            "4 doctors active, 1 overwhelmed. Throughput: 6 discharges in last 10 ticks."
        ),
    }

    t0 = time.time()
    explanation = await client.explain_entity("patient", 10, state_snapshot)
    elapsed = time.time() - t0

    sentence_count = len([s for s in explanation.split(".") if len(s.strip()) > 10])
    print(f"  {INFO} Explanation ({sentence_count} sentences): {explanation}")
    print(f"  {INFO} Elapsed: {elapsed:.2f}s")

    passed = all([
        _check(len(explanation) > 50, "explanation is substantive"),
        _check("10" in explanation, "references patient ID 10"),
        _check(elapsed < 8.0, f"completed in < 8s (was {elapsed:.2f}s)"),
    ])
    return passed


async def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"{FAIL} ANTHROPIC_API_KEY is not set. Copy backend/.env.example to backend/.env")
        sys.exit(1)

    model = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
    print(f"\n{'='*60}")
    print(f"  LLM Layer Smoke Test  |  Model: {model}")
    print(f"{'='*60}")

    client = AnthropicLLMClient(api_key=api_key, model=model)

    results = []
    for test_fn in [
        smoke_test_doctor_decide,
        smoke_test_patient_reevaluate,
        smoke_test_explain_event,
        smoke_test_explain_entity,
    ]:
        try:
            passed = await test_fn(client)
            results.append(passed)
        except Exception as exc:
            print(f"\n{FAIL} Test crashed with exception: {exc}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print(f"\n{'='*60}")
    print(f"  Stats: {client.stats}")
    print(f"\n  Results: {sum(results)}/{len(results)} tests passed")
    print(f"{'='*60}\n")

    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

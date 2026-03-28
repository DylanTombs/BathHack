"""
Standalone tests for the LLM integration layer (Agent 2).

These tests run WITHOUT Agent 1 (simulation engine) or a real Anthropic API key.
All LLM calls are mocked at the _call_llm level so tests are fast and deterministic.

Run with: pytest tests/test_llm_standalone.py -v

Coverage targets:
  - AnthropicLLMClient: doctor_decide, patient_reevaluate, explain_event, explain_entity
  - JSON parsers: clean JSON, markdown-fenced JSON, malformed JSON, invalid IDs
  - Rule-based fallbacks: correct priority ordering
  - Timeout protection: falls back within 3.5s when LLM sleeps
  - LLMTriggerGuard: per-tick limit, doctor cooldown, patient cooldown, trigger conditions
  - ExplainerService: context dict building, state summary generation
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from simulation.types import (
    Doctor,
    DoctorContext,
    Patient,
    PatientContext,
    SimEvent,
    SimulationState,
    MetricsSnapshot,
    Ward,
)
from llm.client import AnthropicLLMClient, _extract_json, _safe_float
from llm.triggers import LLMTriggerGuard
from llm.explainer import ExplainerService


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_patient(
    id: int = 1,
    name: Optional[str] = None,
    severity: str = "medium",
    condition: str = "stable",
    location: str = "waiting",
    wait_time_ticks: int = 2,
    age: int = 45,
    diagnosis: str = "Chest pain",
    assigned_doctor_id: Optional[int] = None,
    treatment_started_tick: Optional[int] = None,
) -> Patient:
    return Patient(
        id=id,
        name=name or f"Patient #{id}",
        severity=severity,
        condition=condition,
        location=location,
        assigned_doctor_id=assigned_doctor_id,
        arrived_at_tick=1,
        treatment_started_tick=treatment_started_tick,
        treatment_duration_ticks=6,
        wait_time_ticks=wait_time_ticks,
        age=age,
        diagnosis=diagnosis,
        grid_x=1.0,
        grid_y=1.0,
    )


def make_doctor(
    id: int = 1,
    name: Optional[str] = None,
    workload: str = "moderate",
    capacity: int = 3,
    assigned_patient_ids: Optional[list] = None,
    decisions_made: int = 5,
) -> Doctor:
    return Doctor(
        id=id,
        name=name or f"Dr. #{id}",
        assigned_patient_ids=assigned_patient_ids or [],
        capacity=capacity,
        workload=workload,
        specialty="General",
        grid_x=5.0,
        grid_y=5.0,
        is_available=True,
        decisions_made=decisions_made,
    )


def make_doctor_context(
    doctor: Optional[Doctor] = None,
    patients: Optional[list] = None,
    icu_is_full: bool = False,
    general_ward_is_full: bool = False,
    current_tick: int = 10,
) -> DoctorContext:
    return DoctorContext(
        doctor=doctor or make_doctor(),
        available_patients=patients if patients is not None else [make_patient()],
        icu_is_full=icu_is_full,
        general_ward_is_full=general_ward_is_full,
        current_tick=current_tick,
    )


def make_patient_context(
    patient: Optional[Patient] = None,
    ticks_waiting: int = 3,
    ward_occupancy_pct: float = 60.0,
    doctor_available: bool = True,
    current_tick: int = 10,
) -> PatientContext:
    return PatientContext(
        patient=patient or make_patient(),
        ticks_waiting=ticks_waiting,
        ward_occupancy_pct=ward_occupancy_pct,
        doctor_available=doctor_available,
        current_tick=current_tick,
    )


def make_sim_event(
    tick: int = 5,
    event_type: str = "doctor_decision",
    entity_id: int = 1,
    entity_type: str = "doctor",
    raw_description: str = "Dr. Smith assigned to Patient #3",
    severity: str = "info",
) -> SimEvent:
    return SimEvent(
        tick=tick,
        event_type=event_type,
        entity_id=entity_id,
        entity_type=entity_type,
        raw_description=raw_description,
        llm_explanation=None,
        severity=severity,
    )


def make_simulation_state(
    tick: int = 20,
    patients: Optional[list] = None,
    doctors: Optional[list] = None,
    events: Optional[list] = None,
    scenario: str = "normal",
) -> SimulationState:
    _patients = patients or [make_patient(id=1, severity="critical", condition="worsening")]
    _doctors = doctors or [make_doctor(id=1)]
    _events = events or []

    wards = {
        "waiting": Ward(name="waiting", capacity=50, occupied=12),
        "general_ward": Ward(name="general_ward", capacity=20, occupied=15),
        "icu": Ward(name="icu", capacity=5, occupied=3),
        "discharged": Ward(name="discharged", capacity=999, occupied=10),
    }
    metrics = MetricsSnapshot(
        tick=tick,
        simulated_hour=tick,
        total_patients_arrived=30,
        total_patients_discharged=10,
        avg_wait_time_ticks=3.5,
        avg_treatment_time_ticks=7.0,
        current_queue_length=12,
        general_ward_occupancy_pct=75.0,
        icu_occupancy_pct=60.0,
        doctor_utilisation_pct=75.0,
        throughput_last_10_ticks=4,
        critical_patients_waiting=1,
    )
    return SimulationState(
        tick=tick,
        timestamp=1711634400.0,
        patients=_patients,
        doctors=_doctors,
        beds=[],
        wards=wards,
        metrics=metrics,
        events=_events,
        scenario=scenario,
        is_running=True,
    )


def make_client() -> AnthropicLLMClient:
    return AnthropicLLMClient(api_key="test-key", model="claude-haiku-4-5-20251001")


# ── Helper to mock _call_llm ───────────────────────────────────────────────────

def mock_call_llm(client: AnthropicLLMClient, return_value: Optional[str]):
    """Patch _call_llm to return a fixed value without hitting the API."""
    return patch.object(client, "_call_llm", new=AsyncMock(return_value=return_value))


# ══════════════════════════════════════════════════════════════════════════════
# Tests: doctor_decide
# ══════════════════════════════════════════════════════════════════════════════

class TestDoctorDecide:

    @pytest.mark.asyncio
    async def test_returns_valid_patient_id_from_llm(self):
        """LLM returns valid JSON with a patient id in the candidate list."""
        client = make_client()
        context = make_doctor_context(
            patients=[make_patient(id=10), make_patient(id=11)],
        )
        llm_json = json.dumps({
            "target_patient_id": 10,
            "reason": "Critical patient needs immediate attention",
            "confidence": 0.95,
        })
        with mock_call_llm(client, llm_json):
            decision = await client.doctor_decide(context)

        assert decision.target_patient_id == 10
        assert len(decision.reason) > 5
        assert 0.0 <= decision.confidence <= 1.0
        assert decision.fallback_used is False

    @pytest.mark.asyncio
    async def test_handles_markdown_fenced_json(self):
        """LLM wraps response in ```json ... ``` fences — must still parse."""
        client = make_client()
        context = make_doctor_context(
            patients=[make_patient(id=7)],
        )
        fenced = "```json\n{\"target_patient_id\": 7, \"reason\": \"Urgent\", \"confidence\": 0.8}\n```"
        with mock_call_llm(client, fenced):
            decision = await client.doctor_decide(context)

        assert decision.target_patient_id == 7
        assert decision.fallback_used is False

    @pytest.mark.asyncio
    async def test_falls_back_on_malformed_json(self):
        """Malformed JSON from LLM triggers rule-based fallback."""
        client = make_client()
        patients = [
            make_patient(id=1, severity="low", wait_time_ticks=1),
            make_patient(id=2, severity="critical", wait_time_ticks=5),
        ]
        context = make_doctor_context(patients=patients)
        with mock_call_llm(client, "NOT VALID JSON AT ALL !!!"):
            decision = await client.doctor_decide(context)

        assert decision.fallback_used is True
        assert decision.target_patient_id == 2  # rule-based: highest severity

    @pytest.mark.asyncio
    async def test_falls_back_on_invalid_patient_id(self):
        """LLM returns a patient_id not in the candidate list → fallback."""
        client = make_client()
        patients = [make_patient(id=3, severity="medium")]
        context = make_doctor_context(patients=patients)
        bad_json = json.dumps({
            "target_patient_id": 999,  # not in candidates
            "reason": "Test",
            "confidence": 0.5,
        })
        with mock_call_llm(client, bad_json):
            decision = await client.doctor_decide(context)

        assert decision.fallback_used is True
        assert decision.target_patient_id == 3  # the only valid candidate

    @pytest.mark.asyncio
    async def test_fallback_picks_critical_over_low(self):
        """Rule-based fallback: critical severity takes precedence over low."""
        client = make_client()
        patients = [
            make_patient(id=1, severity="low", wait_time_ticks=10),
            make_patient(id=2, severity="critical", wait_time_ticks=1),
            make_patient(id=3, severity="medium", wait_time_ticks=5),
        ]
        context = make_doctor_context(patients=patients)
        with mock_call_llm(client, "broken{json}"):
            decision = await client.doctor_decide(context)

        assert decision.target_patient_id == 2
        assert decision.fallback_used is True

    @pytest.mark.asyncio
    async def test_fallback_breaks_severity_tie_by_wait_time(self):
        """Rule-based fallback: among equal severity, longer wait wins."""
        client = make_client()
        patients = [
            make_patient(id=1, severity="critical", wait_time_ticks=2),
            make_patient(id=2, severity="critical", wait_time_ticks=8),
            make_patient(id=3, severity="critical", wait_time_ticks=5),
        ]
        context = make_doctor_context(patients=patients)
        with mock_call_llm(client, "{}"):
            decision = await client.doctor_decide(context)

        assert decision.target_patient_id == 2  # longest wait
        assert decision.fallback_used is True

    @pytest.mark.asyncio
    async def test_no_patients_returns_negative_one(self):
        """Empty patient list returns sentinel -1."""
        client = make_client()
        context = make_doctor_context(patients=[])
        with mock_call_llm(client, None):
            decision = await client.doctor_decide(context)

        assert decision.target_patient_id == -1
        assert decision.fallback_used is True

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self):
        """LLM call that exceeds TIMEOUT_SECONDS falls back within deadline."""
        client = make_client()
        client.TIMEOUT_SECONDS = 0.1  # 100ms for fast tests

        patients = [make_patient(id=5, severity="critical")]
        context = make_doctor_context(patients=patients)

        async def slow_call(*_):
            await asyncio.sleep(5)  # will be cancelled by timeout
            return '{"target_patient_id": 5, "reason": "test", "confidence": 0.9}'

        with patch.object(client, "_call_llm", new=slow_call):
            decision = await client.doctor_decide(context)

        assert decision.fallback_used is True
        assert decision.target_patient_id == 5  # rule-based selects only candidate


# ══════════════════════════════════════════════════════════════════════════════
# Tests: patient_reevaluate
# ══════════════════════════════════════════════════════════════════════════════

class TestPatientReevaluate:

    @pytest.mark.asyncio
    async def test_returns_valid_update_from_llm(self):
        """LLM returns well-formed patient update JSON."""
        client = make_client()
        context = make_patient_context(
            patient=make_patient(id=5, condition="stable", severity="medium"),
        )
        llm_json = json.dumps({
            "condition": "worsening",
            "new_severity": "critical",
            "priority_change": True,
            "reason": "Patient deteriorating without treatment",
        })
        with mock_call_llm(client, llm_json):
            update = await client.patient_reevaluate(context)

        assert update.patient_id == 5
        assert update.new_condition == "worsening"
        assert update.new_severity == "critical"
        assert update.priority_change is True
        assert update.fallback_used is False

    @pytest.mark.asyncio
    async def test_null_severity_means_no_change(self):
        """new_severity: null means severity is unchanged."""
        client = make_client()
        context = make_patient_context(patient=make_patient(id=3))
        llm_json = json.dumps({
            "condition": "improving",
            "new_severity": None,
            "priority_change": False,
            "reason": "Responding to treatment",
        })
        with mock_call_llm(client, llm_json):
            update = await client.patient_reevaluate(context)

        assert update.new_severity is None
        assert update.new_condition == "improving"
        assert update.fallback_used is False

    @pytest.mark.asyncio
    async def test_invalid_condition_preserved_from_context(self):
        """Invalid condition in LLM response falls back to current context condition."""
        client = make_client()
        patient = make_patient(id=2, condition="stable")
        context = make_patient_context(patient=patient)
        llm_json = json.dumps({
            "condition": "INVALID_VALUE",
            "new_severity": None,
            "priority_change": False,
            "reason": "Test",
        })
        with mock_call_llm(client, llm_json):
            update = await client.patient_reevaluate(context)

        assert update.new_condition == "stable"  # preserved from context

    @pytest.mark.asyncio
    async def test_malformed_json_returns_no_change_fallback(self):
        """Malformed JSON returns a no-change fallback."""
        client = make_client()
        patient = make_patient(id=8, condition="worsening")
        context = make_patient_context(patient=patient)
        with mock_call_llm(client, "this is not json"):
            update = await client.patient_reevaluate(context)

        assert update.fallback_used is True
        assert update.patient_id == 8
        assert update.new_condition == "worsening"  # unchanged
        assert update.new_severity is None
        assert update.priority_change is False

    @pytest.mark.asyncio
    async def test_handles_fenced_json(self):
        """Markdown-fenced JSON is correctly extracted."""
        client = make_client()
        context = make_patient_context()
        fenced = "```\n{\"condition\": \"stable\", \"new_severity\": null, \"priority_change\": false, \"reason\": \"Stable\"}\n```"
        with mock_call_llm(client, fenced):
            update = await client.patient_reevaluate(context)

        assert update.new_condition == "stable"
        assert update.fallback_used is False

    @pytest.mark.asyncio
    async def test_timeout_returns_no_change(self):
        """Timeout on patient reevaluation returns no-change fallback."""
        client = make_client()
        client.TIMEOUT_SECONDS = 0.05
        patient = make_patient(id=9, condition="worsening")
        context = make_patient_context(patient=patient)

        async def slow_call(*_):
            await asyncio.sleep(5)
            return "{}"

        with patch.object(client, "_call_llm", new=slow_call):
            update = await client.patient_reevaluate(context)

        assert update.fallback_used is True
        assert update.new_condition == "worsening"  # unchanged from context


# ══════════════════════════════════════════════════════════════════════════════
# Tests: explain_event
# ══════════════════════════════════════════════════════════════════════════════

class TestExplainEvent:

    @pytest.mark.asyncio
    async def test_returns_llm_explanation(self):
        """Successful LLM call returns the generated explanation text."""
        client = make_client()
        event = make_sim_event(raw_description="Dr. Patel assigned to Patient #1")
        explanation = "Dr. Patel prioritised the critical cardiac patient over two stable cases."
        with mock_call_llm(client, explanation):
            result = await client.explain_event(event)

        assert result == explanation

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_description_on_failure(self):
        """On LLM failure, returns the event's raw_description."""
        client = make_client()
        event = make_sim_event(raw_description="Fallback text here")
        with mock_call_llm(client, None):
            result = await client.explain_event(event)

        assert result == "Fallback text here"

    @pytest.mark.asyncio
    async def test_falls_back_on_empty_string(self):
        """Empty LLM response falls back to raw_description."""
        client = make_client()
        event = make_sim_event(raw_description="Raw fallback")
        with mock_call_llm(client, "   "):
            result = await client.explain_event(event)

        assert result == "Raw fallback"

    @pytest.mark.asyncio
    async def test_timeout_returns_raw_description(self):
        """Timeout falls back to raw_description."""
        client = make_client()
        client.TIMEOUT_SECONDS = 0.05
        event = make_sim_event(raw_description="Timeout fallback")

        async def slow(*_):
            await asyncio.sleep(5)
            return "Will never return"

        with patch.object(client, "_call_llm", new=slow):
            result = await client.explain_event(event)

        assert result == "Timeout fallback"


# ══════════════════════════════════════════════════════════════════════════════
# Tests: LLM call stats
# ══════════════════════════════════════════════════════════════════════════════

class TestClientStats:

    @pytest.mark.asyncio
    async def test_request_count_increments_on_success(self):
        client = make_client()
        context = make_doctor_context(patients=[make_patient(id=1)])
        llm_json = json.dumps({"target_patient_id": 1, "reason": "ok", "confidence": 0.9})
        with mock_call_llm(client, llm_json):
            await client.doctor_decide(context)

        assert client.stats["total_requests"] == 1
        assert client.stats["fallback_count"] == 0

    @pytest.mark.asyncio
    async def test_fallback_count_increments_on_timeout(self):
        client = make_client()
        client.TIMEOUT_SECONDS = 0.05
        context = make_doctor_context(patients=[make_patient(id=1)])

        async def slow(*_):
            await asyncio.sleep(5)

        with patch.object(client, "_call_llm", new=slow):
            await client.doctor_decide(context)

        assert client.stats["fallback_count"] == 1
        assert client.stats["total_requests"] == 0

    def test_fallback_rate_zero_when_all_successful(self):
        client = make_client()
        client._request_count = 10
        client._fallback_count = 0
        assert client.stats["fallback_rate"] == 0.0

    def test_fallback_rate_calculation(self):
        client = make_client()
        client._request_count = 7
        client._fallback_count = 3
        rate = client.stats["fallback_rate"]
        assert abs(rate - 0.3) < 0.001


# ══════════════════════════════════════════════════════════════════════════════
# Tests: JSON helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractJson:

    def test_parses_clean_json(self):
        result = _extract_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_parses_json_with_fences(self):
        fenced = "```json\n{\"a\": 1}\n```"
        assert _extract_json(fenced) == {"a": 1}

    def test_parses_json_with_plain_fences(self):
        fenced = "```\n{\"b\": 2}\n```"
        assert _extract_json(fenced) == {"b": 2}

    def test_raises_on_malformed(self):
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json at all")

    def test_strips_whitespace(self):
        assert _extract_json('  {"x": 99}  ') == {"x": 99}


class TestSafeFloat:

    def test_clamps_below_min(self):
        assert _safe_float(-1.0, 0.0, 1.0) == 0.0

    def test_clamps_above_max(self):
        assert _safe_float(2.5, 0.0, 1.0) == 1.0

    def test_passes_through_valid_value(self):
        assert _safe_float(0.75, 0.0, 1.0) == 0.75

    def test_returns_midpoint_on_invalid(self):
        assert _safe_float("bad", 0.0, 1.0) == 0.5

    def test_converts_string_float(self):
        assert _safe_float("0.8", 0.0, 1.0) == 0.8


# ══════════════════════════════════════════════════════════════════════════════
# Tests: LLMTriggerGuard
# ══════════════════════════════════════════════════════════════════════════════

class TestLLMTriggerGuard:

    # ── Initialisation ─────────────────────────────────────────────────────────

    def test_initial_state(self):
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        assert guard.calls_this_tick == 0
        assert guard.budget_remaining_this_tick == LLMTriggerGuard.GLOBAL_CALLS_PER_TICK_LIMIT

    # ── Global per-tick limit ──────────────────────────────────────────────────

    def test_global_limit_blocks_excess_calls(self):
        """
        10 doctors all qualify for LLM — only GLOBAL_CALLS_PER_TICK_LIMIT=3 should fire.
        """
        guard = LLMTriggerGuard()
        guard.new_tick(100)

        approved = 0
        for doctor_id in range(10):
            # Each doctor has 2 critical patients — should qualify individually
            patients = [
                make_patient(id=doctor_id * 10, severity="critical"),
                make_patient(id=doctor_id * 10 + 1, severity="critical"),
            ]
            context = make_doctor_context(
                doctor=make_doctor(id=doctor_id, workload="overwhelmed"),
                patients=patients,
                current_tick=100,
            )
            if guard.should_call_llm_for_doctor(doctor_id, context):
                guard.record_doctor_call(doctor_id)
                approved += 1

        assert approved == LLMTriggerGuard.GLOBAL_CALLS_PER_TICK_LIMIT

    def test_per_tick_limit_resets_on_new_tick(self):
        """After new_tick(), the budget is restored."""
        guard = LLMTriggerGuard()
        guard.new_tick(1)

        # Exhaust budget on tick 1
        for i in range(LLMTriggerGuard.GLOBAL_CALLS_PER_TICK_LIMIT):
            guard.record_doctor_call(i)

        assert guard.budget_remaining_this_tick == 0

        # New tick resets budget
        guard.new_tick(2)
        assert guard.budget_remaining_this_tick == LLMTriggerGuard.GLOBAL_CALLS_PER_TICK_LIMIT

    # ── Doctor cooldown ────────────────────────────────────────────────────────

    def test_doctor_cooldown_blocks_repeat_calls(self):
        """Same doctor cannot trigger LLM within DOCTOR_COOLDOWN_TICKS ticks."""
        guard = LLMTriggerGuard()
        guard.new_tick(10)

        patients = [
            make_patient(id=1, severity="critical"),
            make_patient(id=2, severity="critical"),
        ]
        context = make_doctor_context(doctor=make_doctor(id=42), patients=patients, current_tick=10)

        # First call should be allowed
        assert guard.should_call_llm_for_doctor(42, context) is True
        guard.record_doctor_call(42)

        # Immediately on same tick — still blocked (cooldown just started)
        guard.new_tick(11)
        context_t11 = make_doctor_context(doctor=make_doctor(id=42), patients=patients, current_tick=11)
        assert guard.should_call_llm_for_doctor(42, context_t11) is False

        # Still blocked at tick 12 (only 2 ticks elapsed, need 3)
        guard.new_tick(12)
        context_t12 = make_doctor_context(doctor=make_doctor(id=42), patients=patients, current_tick=12)
        assert guard.should_call_llm_for_doctor(42, context_t12) is False

        # Tick 13 — 3 ticks elapsed — should be allowed again
        guard.new_tick(13)
        context_t13 = make_doctor_context(doctor=make_doctor(id=42), patients=patients, current_tick=13)
        assert guard.should_call_llm_for_doctor(42, context_t13) is True

    def test_different_doctors_have_independent_cooldowns(self):
        """Doctor A's cooldown doesn't affect Doctor B."""
        guard = LLMTriggerGuard()
        guard.new_tick(10)

        patients = [make_patient(id=1, severity="critical"), make_patient(id=2, severity="critical")]
        ctx_a = make_doctor_context(doctor=make_doctor(id=1), patients=patients, current_tick=10)
        ctx_b = make_doctor_context(doctor=make_doctor(id=2), patients=patients, current_tick=10)

        guard.should_call_llm_for_doctor(1, ctx_a)
        guard.record_doctor_call(1)

        # Doctor 2 has never been called — should still be eligible
        assert guard.should_call_llm_for_doctor(2, ctx_b) is True

    # ── Doctor trigger conditions ──────────────────────────────────────────────

    def test_doctor_triggers_on_two_critical_patients(self):
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        patients = [
            make_patient(id=1, severity="critical"),
            make_patient(id=2, severity="critical"),
        ]
        context = make_doctor_context(patients=patients)
        assert guard.should_call_llm_for_doctor(1, context) is True

    def test_doctor_does_not_trigger_on_one_critical(self):
        """One critical patient — not enough to trigger without other conditions."""
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        patients = [
            make_patient(id=1, severity="critical"),
            make_patient(id=2, severity="low"),
        ]
        context_no_overwhelm = DoctorContext(
            doctor=make_doctor(workload="moderate"),
            available_patients=patients,
            icu_is_full=False,
            general_ward_is_full=False,
            current_tick=1,
        )
        assert guard.should_call_llm_for_doctor(1, context_no_overwhelm) is False

    def test_doctor_triggers_on_overwhelmed_workload(self):
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        context = DoctorContext(
            doctor=make_doctor(workload="overwhelmed"),
            available_patients=[make_patient(id=1, severity="low")],
            icu_is_full=False,
            general_ward_is_full=False,
            current_tick=1,
        )
        assert guard.should_call_llm_for_doctor(1, context) is True

    def test_doctor_triggers_on_icu_full_critical_in_general_ward(self):
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        patients = [make_patient(id=1, severity="critical", location="general_ward")]
        context = make_doctor_context(
            patients=patients,
            icu_is_full=True,
        )
        assert guard.should_call_llm_for_doctor(1, context) is True

    # ── Patient cooldown ───────────────────────────────────────────────────────

    def test_patient_cooldown_blocks_repeat_calls(self):
        guard = LLMTriggerGuard()
        guard.new_tick(0)

        patient = make_patient(id=99, condition="worsening")
        ctx = make_patient_context(patient=patient, ticks_waiting=6, current_tick=0)

        assert guard.should_call_llm_for_patient(99, ctx) is True
        guard.record_patient_call(99)

        # Within cooldown window
        for tick in range(1, LLMTriggerGuard.PATIENT_COOLDOWN_TICKS):
            guard.new_tick(tick)
            ctx_t = PatientContext(
                patient=patient,
                ticks_waiting=6,
                ward_occupancy_pct=60.0,
                doctor_available=True,
                current_tick=tick,
            )
            assert guard.should_call_llm_for_patient(99, ctx_t) is False

        # After full cooldown elapsed
        tick_after = LLMTriggerGuard.PATIENT_COOLDOWN_TICKS
        guard.new_tick(tick_after)
        ctx_after = PatientContext(
            patient=patient,
            ticks_waiting=6,
            ward_occupancy_pct=60.0,
            doctor_available=True,
            current_tick=tick_after,
        )
        assert guard.should_call_llm_for_patient(99, ctx_after) is True

    # ── Patient trigger conditions ─────────────────────────────────────────────

    def test_patient_triggers_on_long_wait(self):
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        patient = make_patient(id=5, condition="stable")
        ctx = make_patient_context(
            patient=patient,
            ticks_waiting=LLMTriggerGuard.CRITICAL_WAIT_THRESHOLD + 1,
            current_tick=1,
        )
        assert guard.should_call_llm_for_patient(5, ctx) is True

    def test_patient_triggers_on_worsening_condition(self):
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        patient = make_patient(id=5, condition="worsening")
        ctx = make_patient_context(
            patient=patient,
            ticks_waiting=1,  # not long
            current_tick=1,
        )
        assert guard.should_call_llm_for_patient(5, ctx) is True

    def test_patient_triggers_on_periodic_sweep(self):
        """Tick that is a multiple of PATIENT_COOLDOWN_TICKS triggers a sweep."""
        guard = LLMTriggerGuard()
        sweep_tick = LLMTriggerGuard.PATIENT_COOLDOWN_TICKS  # e.g. tick 5
        guard.new_tick(sweep_tick)
        patient = make_patient(id=6, condition="stable")
        ctx = make_patient_context(patient=patient, ticks_waiting=1, current_tick=sweep_tick)
        assert guard.should_call_llm_for_patient(6, ctx) is True

    def test_patient_does_not_trigger_without_condition(self):
        """No long wait, no worsening, not a sweep tick — should not trigger."""
        guard = LLMTriggerGuard()
        guard.new_tick(3)  # not a multiple of 5
        patient = make_patient(id=7, condition="stable")
        ctx = make_patient_context(
            patient=patient,
            ticks_waiting=1,
            current_tick=3,
        )
        assert guard.should_call_llm_for_patient(7, ctx) is False

    # ── Stats ──────────────────────────────────────────────────────────────────

    def test_stats_tracks_totals(self):
        guard = LLMTriggerGuard()
        guard.new_tick(1)
        guard.record_doctor_call(1)
        guard.record_doctor_call(2)
        guard.new_tick(10)
        guard.record_patient_call(5)

        s = guard.stats
        assert s["total_doctor_calls"] == 2
        assert s["total_patient_calls"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# Tests: ExplainerService
# ══════════════════════════════════════════════════════════════════════════════

class TestExplainerService:

    def test_build_state_summary_contains_key_info(self):
        """Summary string includes tick, scenario, and key metrics."""
        state = make_simulation_state(tick=42, scenario="surge")
        service = ExplainerService(MagicMock())
        summary = service._build_state_summary(state)

        assert "42" in summary
        assert "surge" in summary
        # Should mention occupancy
        assert "%" in summary

    def test_build_patient_context_missing_patient(self):
        """Requesting context for a non-existent patient returns error dict."""
        state = make_simulation_state()
        service = ExplainerService(MagicMock())
        ctx = service._build_patient_context_dict(9999, state)
        assert "error" in ctx

    def test_build_patient_context_includes_patient_fields(self):
        """Patient context dict contains the patient's core fields."""
        patient = make_patient(id=1, severity="critical", diagnosis="Heart attack", age=70)
        state = make_simulation_state(patients=[patient])
        service = ExplainerService(MagicMock())
        ctx = service._build_patient_context_dict(1, state)

        assert ctx["id"] == 1
        assert ctx["severity"] == "critical"
        assert ctx["diagnosis"] == "Heart attack"
        assert ctx["age"] == 70

    def test_build_patient_context_enriches_with_doctor(self):
        """Patient context includes assigned doctor info when doctor is in state."""
        patient = make_patient(id=1, assigned_doctor_id=5)
        doctor = make_doctor(id=5, name="Dr. Jones")
        state = make_simulation_state(patients=[patient], doctors=[doctor])
        service = ExplainerService(MagicMock())
        ctx = service._build_patient_context_dict(1, state)

        assert ctx.get("assigned_doctor_name") == "Dr. Jones"

    def test_build_patient_context_includes_recent_events(self):
        """Recent events for the patient are included in context."""
        patient = make_patient(id=2)
        events = [
            make_sim_event(entity_id=2, entity_type="patient", tick=15),
            make_sim_event(entity_id=2, entity_type="patient", tick=18),
            make_sim_event(entity_id=99, entity_type="patient", tick=19),  # different patient
        ]
        state = make_simulation_state(patients=[patient], events=events)
        service = ExplainerService(MagicMock())
        ctx = service._build_patient_context_dict(2, state)

        assert "recent_events" in ctx
        assert len(ctx["recent_events"]) == 2
        # Events for patient 99 should not appear
        for ev in ctx["recent_events"]:
            assert ev["tick"] in (15, 18)

    def test_build_doctor_context_missing_doctor(self):
        """Requesting context for a non-existent doctor returns error dict."""
        state = make_simulation_state()
        service = ExplainerService(MagicMock())
        ctx = service._build_doctor_context_dict(9999, state)
        assert "error" in ctx

    def test_build_doctor_context_includes_doctor_fields(self):
        """Doctor context dict contains core doctor fields."""
        doctor = make_doctor(id=3, name="Dr. Hart", workload="heavy", decisions_made=20)
        state = make_simulation_state(doctors=[doctor])
        service = ExplainerService(MagicMock())
        ctx = service._build_doctor_context_dict(3, state)

        assert ctx["id"] == 3
        assert ctx["name"] == "Dr. Hart"
        assert ctx["workload"] == "heavy"
        assert ctx["decisions_made"] == 20

    def test_build_doctor_context_includes_assigned_patient_summaries(self):
        """Doctor context lists names and severities of assigned patients."""
        patient_a = make_patient(id=10, severity="critical", assigned_doctor_id=1)
        patient_b = make_patient(id=11, severity="medium", assigned_doctor_id=1)
        doctor = make_doctor(id=1, assigned_patient_ids=[10, 11])
        state = make_simulation_state(patients=[patient_a, patient_b], doctors=[doctor])
        service = ExplainerService(MagicMock())
        ctx = service._build_doctor_context_dict(1, state)

        assert ctx["assigned_patient_count"] == 2
        # At least one assigned patient summary should mention "critical"
        summaries = "\n".join(ctx.get("assigned_patients", []))
        assert "critical" in summaries

    @pytest.mark.asyncio
    async def test_explain_patient_calls_llm_client(self):
        """explain_patient delegates to llm_client.explain_entity."""
        mock_llm = AsyncMock()
        mock_llm.explain_entity = AsyncMock(return_value="Patient is critical.")
        service = ExplainerService(mock_llm)
        patient = make_patient(id=1)
        state = make_simulation_state(patients=[patient])

        result = await service.explain_patient(1, state)

        assert result == "Patient is critical."
        mock_llm.explain_entity.assert_called_once()
        call_args = mock_llm.explain_entity.call_args
        assert call_args[0][0] == "patient"
        assert call_args[0][1] == 1

    @pytest.mark.asyncio
    async def test_explain_doctor_calls_llm_client(self):
        """explain_doctor delegates to llm_client.explain_entity."""
        mock_llm = AsyncMock()
        mock_llm.explain_entity = AsyncMock(return_value="Doctor is overwhelmed.")
        service = ExplainerService(mock_llm)
        doctor = make_doctor(id=2)
        state = make_simulation_state(doctors=[doctor])

        result = await service.explain_doctor(2, state)

        assert result == "Doctor is overwhelmed."
        mock_llm.explain_entity.assert_called_once()
        call_args = mock_llm.explain_entity.call_args
        assert call_args[0][0] == "doctor"
        assert call_args[0][1] == 2


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Prompt builders (smoke tests — verify they produce non-empty strings)
# ══════════════════════════════════════════════════════════════════════════════

class TestPromptBuilders:

    def test_doctor_decision_prompt_contains_patient_ids(self):
        from llm.prompts import build_doctor_decision_prompt
        patients = [
            make_patient(id=1, severity="critical", diagnosis="Cardiac arrest"),
            make_patient(id=2, severity="medium", diagnosis="Fracture"),
        ]
        context = make_doctor_context(patients=patients)
        prompt = build_doctor_decision_prompt(context)

        assert "#1" in prompt
        assert "#2" in prompt
        assert "critical" in prompt
        assert "Cardiac arrest" in prompt
        assert "target_patient_id" in prompt  # JSON format hint

    def test_doctor_decision_prompt_empty_patients(self):
        from llm.prompts import build_doctor_decision_prompt
        context = make_doctor_context(patients=[])
        prompt = build_doctor_decision_prompt(context)
        assert len(prompt) > 10  # should return a safe message

    def test_patient_reeval_prompt_contains_patient_info(self):
        from llm.prompts import build_patient_reeval_prompt
        patient = make_patient(id=5, severity="critical", diagnosis="Stroke", age=80)
        context = make_patient_context(patient=patient, ticks_waiting=9)
        prompt = build_patient_reeval_prompt(context)

        assert "#5" in prompt
        assert "Stroke" in prompt
        assert "critical" in prompt
        assert "9" in prompt  # ticks_waiting
        assert "condition" in prompt  # JSON format hint

    def test_event_explanation_prompt_contains_event_info(self):
        from llm.prompts import build_event_explanation_prompt
        event = make_sim_event(
            event_type="surge_triggered",
            entity_type="doctor",
            entity_id=3,
            raw_description="Mass casualty event triggered",
            severity="critical",
        )
        prompt = build_event_explanation_prompt(event)

        assert "surge_triggered" in prompt
        assert "Mass casualty event triggered" in prompt
        assert "critical" in prompt

    def test_explain_entity_prompt_contains_entity_type(self):
        from llm.prompts import build_explain_entity_prompt
        state = {
            "patients_by_id": {
                "12": {"id": 12, "name": "Patient #12", "severity": "critical"},
            },
            "summary": "Tick 30: surge. ICU 100%.",
        }
        prompt = build_explain_entity_prompt("patient", 12, state)

        assert "patient" in prompt.lower()
        assert "12" in prompt
        assert "critical" in prompt


# ── Pytest configuration ───────────────────────────────────────────────────────

@pytest.fixture
def event_loop_policy():
    """Use default asyncio event loop policy."""
    return asyncio.DefaultEventLoopPolicy()

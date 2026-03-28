"""
ExplainerService — On-demand explanation for patients and doctors.

Called by Agent 3's WebSocket handler when the frontend sends an
explain_patient or explain_doctor command. Builds rich context from
the live SimulationState and delegates the actual LLM call to
AnthropicLLMClient.explain_entity().

Usage (Agent 3):
    explainer = ExplainerService(llm_client)
    text = await explainer.explain_patient(patient_id=12, state=current_state)
    text = await explainer.explain_doctor(doctor_id=2, state=current_state)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm.client import AnthropicLLMClient
    from simulation.types import SimulationState

logger = logging.getLogger(__name__)


class ExplainerService:
    """
    Handles on-demand 'Explain' requests triggered by the frontend.

    Responsibilities:
      - Extract rich context from SimulationState
      - Build structured context dicts for the LLM prompt
      - Delegate to AnthropicLLMClient.explain_entity()
      - Return a clean string for the WebSocket explanation response
    """

    def __init__(self, llm_client: "AnthropicLLMClient") -> None:
        self._client = llm_client

    # ── Public API ─────────────────────────────────────────────────────────────

    async def explain_patient(
        self,
        patient_id: int,
        state: "SimulationState",
    ) -> str:
        """
        Generate a 2-3 sentence explanation of this patient's current situation.

        Context includes: patient demographics, current condition, assigned doctor,
        ward occupancy, recent events related to this patient.
        """
        context_dict = self._build_patient_context_dict(patient_id, state)
        state_summary = self._build_state_summary(state)

        # Inject summary so the LLM has hospital-wide context
        snapshot = {
            "patients_by_id": {
                str(p.id): self._patient_to_dict(p)
                for p in state.patients
            },
            "summary": state_summary,
        }

        result = await self._client.explain_entity("patient", patient_id, snapshot)
        logger.debug("explain_patient(%d): %r", patient_id, result[:80])
        return result

    async def explain_doctor(
        self,
        doctor_id: int,
        state: "SimulationState",
    ) -> str:
        """
        Generate a 2-3 sentence explanation of this doctor's current situation.

        Context includes: doctor specialty, workload, assigned patients and their
        severity, recent decisions, ward pressure.
        """
        context_dict = self._build_doctor_context_dict(doctor_id, state)
        state_summary = self._build_state_summary(state)

        snapshot = {
            "doctors_by_id": {
                str(d.id): self._doctor_to_enriched_dict(d, state)
                for d in state.doctors
            },
            "summary": state_summary,
        }

        result = await self._client.explain_entity("doctor", doctor_id, snapshot)
        logger.debug("explain_doctor(%d): %r", doctor_id, result[:80])
        return result

    # ── Context builders ───────────────────────────────────────────────────────

    def _build_patient_context_dict(
        self,
        patient_id: int,
        state: "SimulationState",
    ) -> dict:
        """
        Extract and flatten all relevant patient info into a dict for the prompt.

        Includes: all Patient fields, assigned doctor name and workload,
        ward occupancy, recent events for this patient.
        """
        patient = next((p for p in state.patients if p.id == patient_id), None)
        if patient is None:
            return {"error": f"Patient #{patient_id} not found in state"}

        base = self._patient_to_dict(patient)

        # Enrich with doctor name if assigned
        if patient.assigned_doctor_id is not None:
            doctor = next(
                (d for d in state.doctors if d.id == patient.assigned_doctor_id),
                None,
            )
            if doctor:
                base["assigned_doctor_name"] = doctor.name
                base["assigned_doctor_specialty"] = doctor.specialty
                base["assigned_doctor_workload"] = doctor.workload

        # Add ward occupancy for context
        ward = state.wards.get(patient.location)
        if ward is not None:
            base["ward_occupancy_pct"] = round(ward.occupancy_pct, 1)
            base["ward_is_full"] = ward.is_full

        # Recent events for this patient (last 5)
        recent_events = [
            {
                "tick": e.tick,
                "type": e.event_type,
                "description": e.llm_explanation or e.raw_description,
            }
            for e in state.events
            if e.entity_id == patient_id and e.entity_type == "patient"
        ]
        if recent_events:
            base["recent_events"] = recent_events[-5:]

        return base

    def _build_doctor_context_dict(
        self,
        doctor_id: int,
        state: "SimulationState",
    ) -> dict:
        """
        Extract and flatten all relevant doctor info.

        Includes: doctor fields, names + severities of assigned patients,
        recent decision events for this doctor.
        """
        doctor = next((d for d in state.doctors if d.id == doctor_id), None)
        if doctor is None:
            return {"error": f"Doctor #{doctor_id} not found in state"}

        base = self._doctor_to_enriched_dict(doctor, state)

        # Recent decision events for this doctor (last 5)
        recent_decisions = [
            {
                "tick": e.tick,
                "type": e.event_type,
                "description": e.llm_explanation or e.raw_description,
            }
            for e in state.events
            if e.entity_id == doctor_id and e.entity_type == "doctor"
        ]
        if recent_decisions:
            base["recent_decisions"] = recent_decisions[-5:]

        return base

    def _build_state_summary(self, state: "SimulationState") -> str:
        """
        Build a one-paragraph hospital status summary for LLM context.

        Example:
            "Tick 42: Surge scenario. ICU at 100%, general ward at 90%.
             12 patients in queue, 2 critical unattended. 4 doctors active,
             1 overwhelmed. Throughput: 8 discharges in last 10 ticks."
        """
        m = state.metrics
        overwhelmed = sum(1 for d in state.doctors if d.workload == "overwhelmed")
        active_doctors = len(state.doctors)
        icu_status = (
            "FULL" if state.wards.get("icu", None) and state.wards["icu"].is_full
            else f"{m.icu_occupancy_pct:.0f}%"
        )

        return (
            f"Tick {state.tick}: Scenario '{state.scenario}'. "
            f"ICU at {icu_status}, general ward at {m.general_ward_occupancy_pct:.0f}%. "
            f"{m.current_queue_length} patients in queue"
            f"{f', {m.critical_patients_waiting} critical unattended' if m.critical_patients_waiting else ''}. "
            f"{active_doctors} doctors active"
            f"{f', {overwhelmed} overwhelmed' if overwhelmed else ''}. "
            f"Throughput: {m.throughput_last_10_ticks} discharges in last 10 ticks. "
            f"Total admitted: {m.total_patients_arrived}, "
            f"discharged: {m.total_patients_discharged}."
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _patient_to_dict(patient) -> dict:
        """Flatten a Patient dataclass into a plain dict for prompts."""
        return {
            "id": patient.id,
            "name": patient.name,
            "age": patient.age,
            "diagnosis": patient.diagnosis,
            "severity": patient.severity,
            "condition": patient.condition,
            "location": patient.location,
            "assigned_doctor_id": patient.assigned_doctor_id,
            "arrived_at_tick": patient.arrived_at_tick,
            "treatment_started_tick": patient.treatment_started_tick,
            "treatment_duration_ticks": patient.treatment_duration_ticks,
            "wait_time_ticks": patient.wait_time_ticks,
            "last_event_explanation": patient.last_event_explanation,
        }

    @staticmethod
    def _doctor_to_enriched_dict(doctor, state: "SimulationState") -> dict:
        """Flatten a Doctor and enrich with assigned patient summaries."""
        assigned_patient_summaries = []
        for pid in doctor.assigned_patient_ids:
            p = next((x for x in state.patients if x.id == pid), None)
            if p:
                assigned_patient_summaries.append(
                    f"Patient #{p.id} ({p.name}): {p.severity} severity, "
                    f"{p.condition}, {p.diagnosis}"
                )

        return {
            "id": doctor.id,
            "name": doctor.name,
            "specialty": doctor.specialty,
            "workload": doctor.workload,
            "capacity": doctor.capacity,
            "is_available": doctor.is_available,
            "decisions_made": doctor.decisions_made,
            "assigned_patient_count": len(doctor.assigned_patient_ids),
            "assigned_patients": assigned_patient_summaries,
        }

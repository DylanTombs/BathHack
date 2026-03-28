"""
DoctorAgent — manages a Doctor's assignment decisions and workload.

Rule-based default: highest-severity + longest-waiting patient.
LLM decision: injected via llm_callback when pressure conditions are met.

LLM is triggered when:
  - ≥2 critical patients are waiting simultaneously
  - OR ICU is full AND a critical patient is in general_ward
  - OR workload is 'overwhelmed'
  - NOT more than once every DOCTOR_LLM_COOLDOWN_TICKS (default 3) ticks
"""
from __future__ import annotations

import random
import logging
from typing import Optional, TYPE_CHECKING

from simulation.types import (
    Doctor,
    DoctorContext,
    DoctorDecision,
    SimEvent,
    WorkloadLevel,
)

if TYPE_CHECKING:
    from simulation.hospital import Hospital
    from simulation.patient import PatientAgent

logger = logging.getLogger(__name__)

# ─── Simulation constants ──────────────────────────────────────────────────────
DOCTOR_LLM_COOLDOWN_TICKS = 3
DOCTOR_CAPACITY = 3

# ─── Doctor cosmetics ──────────────────────────────────────────────────────────
_DOCTOR_NAMES = [
    "Dr. Patel", "Dr. Kim", "Dr. Jones", "Dr. Okonkwo", "Dr. Silva",
    "Dr. Chen", "Dr. Murphy", "Dr. Santos", "Dr. Ali", "Dr. Nguyen",
    "Dr. Brown", "Dr. Garcia", "Dr. Wilson", "Dr. Taylor", "Dr. Anderson",
]

_SPECIALTIES = ["General", "ICU", "Triage", "Emergency", "Cardiology"]

# Grid zones for doctor placement (from data-contracts.md §6)
_WARD_ZONES = {
    "waiting":      (0.0,  7.0, 0.0,  5.0),
    "general_ward": (0.0, 11.0, 6.0, 12.0),
    "icu":          (12.0, 19.0, 6.0, 12.0),
}

_SEVERITY_RANK = {"critical": 2, "medium": 1, "low": 0}


class DoctorAgent:
    """
    Manages a Doctor's assignment decisions and workload tracking.
    """

    def __init__(self, doctor: Doctor, llm_callback=None) -> None:
        self.doctor = doctor
        self._llm_callback = llm_callback
        self._last_llm_tick: int = -999

    # ── Public API ────────────────────────────────────────────────────────────

    async def tick(
        self,
        tick: int,
        waiting_patients: list["PatientAgent"],
        hospital: "Hospital",
    ) -> list[SimEvent]:
        """
        Called once per tick.
        1. If doctor has capacity, decide which patient to take next.
        2. Update workload level.
        3. Emit decision events.
        """
        events: list[SimEvent] = []
        self._update_workload()

        # Keep assigning until at capacity or no candidates remain
        while self.doctor.is_available and waiting_patients:
            chosen = await self.decide_next_patient(waiting_patients, tick, hospital)
            if chosen is None:
                break
            event = self._assign_patient(chosen, tick)
            events.append(event)
            waiting_patients.remove(chosen)
            self._update_workload()

        return events

    # ── Decision logic ────────────────────────────────────────────────────────

    async def decide_next_patient(
        self,
        candidates: list["PatientAgent"],
        tick: int,
        hospital: "Hospital",
    ) -> Optional["PatientAgent"]:
        """
        Choose the next patient to treat.
        Uses LLM when pressure triggers are met; otherwise rule-based.
        """
        if not candidates:
            return None

        if self._should_call_llm_for_decision(tick, candidates, hospital):
            chosen = await self._llm_decide(candidates, tick, hospital)
            if chosen is not None:
                self._last_llm_tick = tick
                return chosen
            # Fall through to rule-based

        return self._rule_based_pick(candidates)

    def _rule_based_pick(
        self, candidates: list["PatientAgent"]
    ) -> Optional["PatientAgent"]:
        """
        Priority order:
          1. critical severity (longest waiting first)
          2. medium severity (longest waiting first)
          3. low severity (longest waiting first)
        Ties broken by arrived_at_tick (FIFO).
        """
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda pa: (
                -_SEVERITY_RANK[pa.patient.severity],
                pa.patient.arrived_at_tick,
            ),
        )

    def _should_call_llm_for_decision(
        self,
        tick: int,
        candidates: list["PatientAgent"],
        hospital: "Hospital",
    ) -> bool:
        """
        LLM is triggered when:
          - ≥2 critical patients are waiting
          - OR ICU is full AND a critical patient is in general_ward
          - OR workload is 'overwhelmed'
          - AND cooldown period has elapsed
        """
        if self._llm_callback is None:
            return False
        if tick - self._last_llm_tick < DOCTOR_LLM_COOLDOWN_TICKS:
            return False

        critical_count = sum(
            1 for pa in candidates if pa.patient.severity == "critical"
        )
        if critical_count >= 2:
            return True

        if hospital.is_ward_full("icu"):
            critical_in_general = any(
                pa.patient.severity == "critical"
                and pa.patient.location == "general_ward"
                for pa in candidates
            )
            if critical_in_general:
                return True

        if self.doctor.workload == "overwhelmed":
            return True

        return False

    async def _llm_decide(
        self,
        candidates: list["PatientAgent"],
        tick: int,
        hospital: "Hospital",
    ) -> Optional["PatientAgent"]:
        """
        Build DoctorContext and call llm_callback.doctor_decide().
        Falls back to rule-based if LLM returns invalid patient_id or raises.
        """
        context = DoctorContext(
            doctor=self.doctor,
            available_patients=[pa.patient for pa in candidates],
            icu_is_full=hospital.is_ward_full("icu"),
            general_ward_is_full=hospital.is_ward_full("general_ward"),
            current_tick=tick,
        )

        try:
            decision: DoctorDecision = await self._llm_callback.doctor_decide(context)
        except Exception as exc:
            logger.warning(
                "LLM doctor_decide failed for doctor %d: %s", self.doctor.id, exc
            )
            return None

        # Validate returned patient id
        candidate_ids = {pa.patient.id for pa in candidates}
        if decision.target_patient_id not in candidate_ids:
            logger.warning(
                "LLM returned invalid patient_id %d for doctor %d; falling back",
                decision.target_patient_id,
                self.doctor.id,
            )
            return None

        chosen = next(
            pa for pa in candidates if pa.patient.id == decision.target_patient_id
        )
        # Store the LLM reasoning separately so _assign_patient can use it
        # (avoids confusion with patient-level last_event_explanation)
        chosen._pending_doctor_reason = decision.reason
        return chosen

    def _assign_patient(self, patient: "PatientAgent", tick: int) -> SimEvent:
        """
        Record the assignment on both doctor and patient.
        Returns a doctor_decision SimEvent.
        """
        p = patient.patient
        d = self.doctor

        d.assigned_patient_ids.append(p.id)
        d.decisions_made += 1
        d.is_available = len(d.assigned_patient_ids) < d.capacity

        p.assigned_doctor_id = d.id
        p.treatment_started_tick = tick

        # Only use an LLM explanation if the DOCTOR's LLM was invoked for this decision
        # (_pending_doctor_reason is set exclusively by _llm_decide, not by patient reevaluation)
        explanation = getattr(patient, "_pending_doctor_reason", None)
        if hasattr(patient, "_pending_doctor_reason"):
            del patient._pending_doctor_reason

        return SimEvent(
            tick=tick,
            event_type="doctor_decision",
            entity_id=d.id,
            entity_type="doctor",
            raw_description=f"{d.name} assigned to {p.name} ({p.severity})",
            llm_explanation=explanation,
            severity=(
                "critical" if p.severity == "critical"
                else "warning" if p.severity == "medium"
                else "info"
            ),
        )

    def _update_workload(self) -> None:
        """
        light:       0 patients
        moderate:    1 to capacity//2
        heavy:       capacity//2+1 to capacity-1
        overwhelmed: at capacity
        """
        assigned = len(self.doctor.assigned_patient_ids)
        cap = self.doctor.capacity

        if assigned == 0:
            level: WorkloadLevel = "light"
        elif assigned <= cap // 2:
            level = "moderate"
        elif assigned < cap:
            level = "heavy"
        else:
            level = "overwhelmed"

        self.doctor.workload = level
        self.doctor.is_available = assigned < cap

    # ── Factory ───────────────────────────────────────────────────────────────

    @staticmethod
    def create_with_specialty(
        doctor_id: int,
        specialty: str,
        llm_callback=None,
    ) -> "DoctorAgent":
        """
        Create a doctor with an explicitly chosen specialty.
        Used for the +/- doctor controls on the frontend.
        """
        name = _DOCTOR_NAMES[(doctor_id - 1) % len(_DOCTOR_NAMES)]

        zone_map = {
            "Triage":      "waiting",
            "General":     "general_ward",
            "ICU":         "icu",
            "Emergency":   "general_ward",
            "Cardiology":  "icu",
        }
        zone = zone_map.get(specialty, "general_ward")
        x0, x1, y0, y1 = _WARD_ZONES[zone]

        # Spread position within zone using id as a jitter seed
        import random as _r
        _r.seed(doctor_id * 31)
        grid_x = round(x0 + _r.uniform(0.2, 0.8) * (x1 - x0), 2)
        grid_y = round((y0 + y1) / 2 + _r.uniform(-0.8, 0.8), 2)
        _r.seed()  # restore global seed

        doctor = Doctor(
            id=doctor_id,
            name=name,
            assigned_patient_ids=[],
            capacity=DOCTOR_CAPACITY,
            workload="light",
            specialty=specialty,
            grid_x=grid_x,
            grid_y=grid_y,
            is_available=True,
            decisions_made=0,
        )
        return DoctorAgent(doctor, llm_callback=llm_callback)

    @staticmethod
    def create_initial(
        doctor_id: int,
        num_doctors: int,
        llm_callback=None,
    ) -> "DoctorAgent":
        """
        Create a doctor with a name, specialty, capacity=3, and a grid position
        distributed evenly across general_ward and ICU zones.
        """
        name = _DOCTOR_NAMES[(doctor_id - 1) % len(_DOCTOR_NAMES)]

        # Distribute specialties: first ≈25% Triage, middle ≈50% General, last ≈25% ICU
        fraction = (doctor_id - 1) / max(num_doctors - 1, 1)
        if fraction < 0.25:
            specialty = "Triage"
            zone = "waiting"
        elif fraction < 0.75:
            specialty = "General"
            zone = "general_ward"
        else:
            specialty = "ICU"
            zone = "icu"

        # Position within zone
        x0, x1, y0, y1 = _WARD_ZONES[zone]
        # Spread doctors evenly within their zone using their id as offset
        t = (doctor_id - 1) / max(num_doctors, 1)
        grid_x = round(x0 + t * (x1 - x0), 2)
        grid_y = round((y0 + y1) / 2, 2)

        doctor = Doctor(
            id=doctor_id,
            name=name,
            assigned_patient_ids=[],
            capacity=DOCTOR_CAPACITY,
            workload="light",
            specialty=specialty,
            grid_x=grid_x,
            grid_y=grid_y,
            is_available=True,
            decisions_made=0,
        )

        return DoctorAgent(doctor, llm_callback=llm_callback)

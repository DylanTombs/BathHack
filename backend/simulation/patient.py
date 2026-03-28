"""
PatientAgent — wraps the Patient dataclass with state-transition logic.

All rule-based transitions live here.  LLM decisions are injected via the
optional llm_callback (any object implementing LLMInterface Protocol).

Patient lifecycle:
  ARRIVE (waiting, unassigned)
    ↓ bed assigned by engine._assign_beds()
  IN_WARD (general_ward or icu, unassigned — waiting for doctor)
    ↓ doctor assigned by engine._run_doctor_assignments()
  IN_TREATMENT (general_ward or icu, doctor assigned, treatment progressing)
    ↓ treatment complete + condition stable/improving
  DISCHARGED
    ↑ treatment complete + condition worsening → extend / escalate
"""
from __future__ import annotations

import random
import logging
from typing import Optional, TYPE_CHECKING

from simulation.types import (
    Patient,
    PatientCondition,
    Severity,
    SimEvent,
    PatientContext,
    PatientUpdate,
    PatientSpec,
)

if TYPE_CHECKING:
    from simulation.hospital import Hospital

logger = logging.getLogger(__name__)

# ─── Simulation constants (shared with engine.py) ─────────────────────────────
PATIENT_REEVAL_EVERY_N_TICKS = 5
CRITICAL_WAIT_THRESHOLD_TICKS = 4

# ─── Patient cosmetics ────────────────────────────────────────────────────────
_FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Henry",
    "Iris", "Jack", "Karen", "Liam", "Maya", "Noah", "Olivia", "Peter",
    "Quinn", "Rachel", "Sam", "Tara", "Uma", "Victor", "Wendy", "Xander",
    "Yara", "Zack", "Ava", "Ben", "Clara", "Dylan", "Ella", "Finn",
    "Gina", "Hana", "Ivan", "Julia", "Kyle", "Luna", "Marco", "Nina",
    "Oscar", "Priya", "Ravi", "Sara", "Tom", "Ursula", "Vera", "Wade",
    "Xena", "Yusuf",
]

_DIAGNOSES: dict[str, list[str]] = {
    "critical": [
        "Cardiac arrest", "Stroke", "Severe trauma",
        "Septic shock", "Pulmonary embolism", "Internal bleeding",
    ],
    "medium": [
        "Appendicitis", "Fracture", "Pneumonia", "Chest pain",
        "Severe asthma", "Diabetic emergency",
    ],
    "low": [
        "Sprain", "Minor laceration", "Headache", "Nausea",
        "Mild fever", "Allergic reaction",
    ],
}

# Treatment duration ranges (min_ticks, max_ticks)
_TREATMENT_TICKS: dict[str, tuple[int, int]] = {
    "critical": (6, 12),
    "medium": (3, 7),
    "low": (1, 4),
}

# Severity arrival distribution (realistic baseline A&E mix):
# low ~72%, medium ~24%, critical ~4%
_SEVERITY_WEIGHTS = [("low", 0.72), ("medium", 0.24), ("critical", 0.04)]


def _make_random_spec(force_severity: Optional[Severity] = None) -> PatientSpec:
    """Produce a random PatientSpec using the existing static pools (fallback path)."""
    sev: Severity = force_severity if force_severity else _random_severity()
    return PatientSpec(
        name=random.choice(_FIRST_NAMES),
        age=random.randint(18, 90),
        severity=sev,
        diagnosis=random.choice(_DIAGNOSES[sev]),
        backstory=None,
    )


def _random_severity() -> Severity:
    r = random.random()
    cumulative = 0.0
    for sev, weight in _SEVERITY_WEIGHTS:
        cumulative += weight
        if r < cumulative:
            return sev  # type: ignore[return-value]
    return "low"


class PatientAgent:
    """
    Wraps a Patient dataclass with state-transition logic.
    """

    def __init__(self, patient: Patient, llm_callback=None) -> None:
        self.patient = patient
        self._llm_callback = llm_callback
        self._last_llm_tick: int = -999   # tick when LLM was last called for this patient
        self._condition_changed_this_tick: bool = False
        self._last_death_risk_pct: float = 0.0
        self._died_this_tick: bool = False
        self.death_risk_multiplier: float = 1.0  # scaled by engine severity level

    # ── Public API ────────────────────────────────────────────────────────────

    async def tick(self, tick: int, hospital: "Hospital") -> list[SimEvent]:
        """
        Advance this patient one simulation tick.
        Returns a list of SimEvents that occurred.
        """
        events: list[SimEvent] = []
        p = self.patient
        self._condition_changed_this_tick = False
        self._died_this_tick = False

        if p.location in ("discharged", "deceased"):
            return events

        # ── Patients waiting without a doctor ─────────────────────────────────
        if p.assigned_doctor_id is None:
            self._increment_wait()
            event = self._check_deterioration(tick)
            if event:
                events.append(event)
                self._condition_changed_this_tick = True
        else:
            # ── Patients in active treatment ──────────────────────────────────
            event = self._progress_treatment(tick)
            if event:
                events.append(event)

        # ── LLM reevaluation (for any non-discharged patient) ─────────────────
        if self._should_call_llm_for_reevaluation(tick):
            event = await self._llm_reevaluate(tick, hospital)
            if event:
                events.append(event)
                self._last_llm_tick = tick

        # ── Death checks ──────────────────────────────────────────────────────
        death_event = self._check_death(tick)
        if death_event:
            events.append(death_event)

        return events

    # ── State transitions (rule-based) ────────────────────────────────────────

    def _increment_wait(self) -> None:
        """Bump wait_time_ticks for unassigned patients."""
        self.patient.wait_time_ticks += 1

    def _progress_treatment(self, tick: int) -> Optional[SimEvent]:
        """
        For patients in active treatment:
        - Small probability of condition improvement each tick.
        - If treatment duration is exceeded and condition is worsening,
          extend treatment and potentially escalate severity.
        Returns a SimEvent if something notable happened, else None.
        """
        p = self.patient
        if p.treatment_started_tick is None:
            return None

        elapsed = tick - p.treatment_started_tick

        # Condition changes during treatment
        if p.condition == "worsening":
            # Treatment slowly reverses worsening: 15% chance of stabilising per tick
            if random.random() < 0.15:
                p.condition = "stable"
                self._condition_changed_this_tick = True
                return SimEvent(
                    tick=tick,
                    event_type="patient_improved",
                    entity_id=p.id,
                    entity_type="patient",
                    raw_description=f"{p.name} stabilised during treatment",
                    llm_explanation=None,
                    severity="info",
                )
        elif p.condition == "stable":
            # 20% chance of progressing to improving
            if random.random() < 0.20:
                p.condition = "improving"
                self._condition_changed_this_tick = True
                return SimEvent(
                    tick=tick,
                    event_type="patient_improved",
                    entity_id=p.id,
                    entity_type="patient",
                    raw_description=f"{p.name} improving steadily",
                    llm_explanation=None,
                    severity="info",
                )

        # If treatment duration exceeded and still worsening → extend
        if elapsed >= p.treatment_duration_ticks and p.condition == "worsening":
            extension = max(2, p.treatment_duration_ticks // 2)
            p.treatment_duration_ticks += extension
            # Severity escalation: low → medium → critical
            if p.severity == "low":
                p.severity = "medium"
            elif p.severity == "medium":
                p.severity = "critical"
            self._condition_changed_this_tick = True
            return SimEvent(
                tick=tick,
                event_type="patient_escalated",
                entity_id=p.id,
                entity_type="patient",
                raw_description=(
                    f"{p.name} not responding to treatment — {p.diagnosis} worsening"
                ),
                llm_explanation=None,
                severity="warning",
            )

        return None

    def _check_deterioration(self, tick: int) -> Optional[SimEvent]:
        """
        Rule-based deterioration for patients waiting without a doctor.

        Rules:
          low  severity, waiting > 5 ticks  → 10% chance/tick → medium
          medium severity, waiting > 3 ticks → 15% chance/tick → critical
          critical, waiting > 2 ticks       → 20% chance/tick of critical event
          worsening in general_ward          → flags need for ICU escalation
        """
        p = self.patient
        event: Optional[SimEvent] = None

        if p.severity == "low" and p.wait_time_ticks > 5:
            if random.random() < 0.10:
                p.severity = "medium"
                p.condition = "worsening"
                event = SimEvent(
                    tick=tick,
                    event_type="patient_escalated",
                    entity_id=p.id,
                    entity_type="patient",
                    raw_description=(
                        f"{p.name} deteriorated to medium severity — {p.diagnosis} worsening"
                    ),
                    llm_explanation=None,
                    severity="warning",
                )

        elif p.severity == "medium" and p.wait_time_ticks > 3:
            if random.random() < 0.15:
                p.severity = "critical"
                p.condition = "worsening"
                event = SimEvent(
                    tick=tick,
                    event_type="patient_escalated",
                    entity_id=p.id,
                    entity_type="patient",
                    raw_description=(
                        f"{p.name} deteriorated to critical — {p.diagnosis} worsening"
                    ),
                    llm_explanation=None,
                    severity="critical",
                )

        elif p.severity == "critical" and p.wait_time_ticks > 2:
            if random.random() < 0.20:
                # Critical patient with no care — emit danger event
                p.condition = "worsening"
                event = SimEvent(
                    tick=tick,
                    event_type="patient_escalated",
                    entity_id=p.id,
                    entity_type="patient",
                    raw_description=(
                        f"{p.name} critical and untreated — {p.diagnosis} deteriorating"
                    ),
                    llm_explanation=None,
                    severity="critical",
                )

        return event

    def _check_death(self, tick: int) -> Optional[SimEvent]:
        """
        Check whether this patient dies this tick.

        Two death paths:
          1. Unattended death: wait_time_ticks >= fatal_wait_ticks (LLM-set threshold)
          2. In-treatment death: random chance per tick from _last_death_risk_pct (LLM-set)

        Sets p.location = "deceased" and self._died_this_tick = True if death occurs.
        """
        p = self.patient
        if p.location in ("discharged", "deceased"):
            return None

        died = False

        # Unattended death
        if (
            p.assigned_doctor_id is None
            and p.fatal_wait_ticks is not None
            and p.wait_time_ticks >= p.fatal_wait_ticks
        ):
            died = True

        # In-treatment death (only if not already dying from unattended)
        elif (
            p.assigned_doctor_id is not None
            and self._last_death_risk_pct > 0.0
            and random.random() < self._last_death_risk_pct * self.death_risk_multiplier
        ):
            died = True

        if not died:
            return None

        p.location = "deceased"
        p.deceased_tick = tick
        self._died_this_tick = True

        if p.assigned_doctor_id is None:
            cause = f"left untreated with {p.diagnosis}"
        else:
            cause = f"fatal complication from {p.diagnosis}"
        logger.info("Tick %d: %s deceased — %s", tick, p.name, cause)

        return SimEvent(
            tick=tick,
            event_type="patient_deceased",
            entity_id=p.id,
            entity_type="patient",
            raw_description=f"{p.name} died — {cause}",
            llm_explanation=None,
            severity="critical",
        )

    # ── LLM trigger logic ─────────────────────────────────────────────────────

    def _should_call_llm_for_reevaluation(self, tick: int) -> bool:
        """
        Returns True when LLM reevaluation should be triggered:
          - Every PATIENT_REEVAL_EVERY_N_TICKS ticks
          - OR condition just changed to worsening
          - OR patient has been waiting > CRITICAL_WAIT_THRESHOLD_TICKS
          - NOT if already called this tick
          - NOT if patient is discharged or deceased
        """
        p = self.patient
        if p.location in ("discharged", "deceased"):
            return False
        if self._last_llm_tick == tick:
            return False
        if self._llm_callback is None:
            return False

        if tick % PATIENT_REEVAL_EVERY_N_TICKS == 0 and tick > 0:
            return True
        if self._condition_changed_this_tick and p.condition == "worsening":
            return True
        if p.wait_time_ticks > CRITICAL_WAIT_THRESHOLD_TICKS:
            return True

        return False

    async def _llm_reevaluate(
        self, tick: int, hospital: "Hospital"
    ) -> Optional[SimEvent]:
        """
        Call llm_callback.patient_reevaluate(context) if available.
        Falls back to no-op if callback is None or raises.
        Returns a SimEvent with llm_explanation populated, or None.
        """
        p = self.patient
        if self._llm_callback is None:
            return None

        # Build context
        ward = hospital.get_ward(p.location if p.location not in ("discharged", "deceased") else "waiting")
        context = PatientContext(
            patient=p,
            ticks_waiting=p.wait_time_ticks,
            ward_occupancy_pct=ward.occupancy_pct,
            doctor_available=(p.assigned_doctor_id is not None),
            current_tick=tick,
        )

        try:
            update: PatientUpdate = await self._llm_callback.patient_reevaluate(context)
        except Exception as exc:
            logger.warning("LLM patient_reevaluate failed for patient %d: %s", p.id, exc)
            return None

        # Apply update
        old_condition = p.condition
        p.condition = update.new_condition
        if update.new_severity is not None:
            p.severity = update.new_severity
        if update.new_condition != old_condition:
            self._condition_changed_this_tick = True

        # Cache death risk for use in _check_death this tick
        self._last_death_risk_pct = update.death_risk_pct

        # Store last explanation on the Patient for UI
        if update.reason:
            p.last_event_explanation = update.reason

        return SimEvent(
            tick=tick,
            event_type="patient_escalated" if p.condition == "worsening" else "patient_improved",
            entity_id=p.id,
            entity_type="patient",
            raw_description=f"{p.name} reevaluated at tick {tick}",
            llm_explanation=update.reason,
            severity=(
                "critical" if p.severity == "critical"
                else "warning" if p.condition == "worsening"
                else "info"
            ),
        )

    # ── Factory ───────────────────────────────────────────────────────────────

    @staticmethod
    def create_new(
        patient_id: int,
        tick: int,
        hospital: "Hospital",
        llm_callback=None,
        force_severity: Optional[Severity] = None,
    ) -> "PatientAgent":
        """
        Generate a new patient with stochastic attributes:
          Severity: 60% low, 30% medium, 10% critical (or force_severity)
          Name: random from the names list
          Diagnosis: appropriate to severity
          Age: 18–90
          Grid position: assigned from waiting-zone slot
        """
        severity: Severity = force_severity if force_severity else _random_severity()
        name = random.choice(_FIRST_NAMES)
        diagnosis = random.choice(_DIAGNOSES[severity])
        age = random.randint(18, 90)
        duration = random.randint(*_TREATMENT_TICKS[severity])

        # Assign waiting zone position
        grid_x, grid_y = hospital.claim_waiting_slot(patient_id)

        patient = Patient(
            id=patient_id,
            name=name,
            severity=severity,
            condition="stable",
            location="waiting",
            assigned_doctor_id=None,
            arrived_at_tick=tick,
            treatment_started_tick=None,
            treatment_duration_ticks=duration,
            wait_time_ticks=0,
            age=age,
            diagnosis=diagnosis,
            grid_x=grid_x,
            grid_y=grid_y,
            last_event_explanation=None,
            backstory=None,
        )

        return PatientAgent(patient, llm_callback=llm_callback)

    @classmethod
    def create_from_spec(
        cls,
        patient_id: int,
        tick: int,
        hospital: "Hospital",
        spec: PatientSpec,
        llm_callback=None,
    ) -> "PatientAgent":
        """
        Create a PatientAgent from an LLM-generated PatientSpec.
        Grid position and treatment duration are determined locally.
        """
        duration = random.randint(*_TREATMENT_TICKS[spec.severity])
        grid_x, grid_y = hospital.claim_waiting_slot(patient_id)

        patient = Patient(
            id=patient_id,
            name=spec.name,
            severity=spec.severity,
            condition="stable",
            location="waiting",
            assigned_doctor_id=None,
            arrived_at_tick=tick,
            treatment_started_tick=None,
            treatment_duration_ticks=duration,
            wait_time_ticks=0,
            age=spec.age,
            diagnosis=spec.diagnosis,
            grid_x=grid_x,
            grid_y=grid_y,
            last_event_explanation=None,
            backstory=spec.backstory,
            fatal_wait_ticks=spec.fatal_wait_ticks,
        )
        return cls(patient, llm_callback=llm_callback)

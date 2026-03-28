"""
MockSimulationEngine — self-contained simulation for Agent 3 standalone development.

Generates realistic hospital simulation state without importing the real simulation
engine (Agent 1). Uses the same dataclass types from simulation.types so the
serializer and WebSocket layer work identically to the production path.

Replaced at integration time by:
    from simulation.engine import SimulationEngine
    engine = SimulationEngine(config, llm_callback=llm_client)
"""
from __future__ import annotations

import math
import random
import time
from typing import Optional

from simulation.types import (
    Bed,
    Doctor,
    MetricsSnapshot,
    Patient,
    ScenarioConfig,
    SimEvent,
    SimulationState,
    Ward,
)

# ─── Static data ──────────────────────────────────────────────────────────────

_DIAGNOSES = [
    "Chest pain",
    "Fractured wrist",
    "Cardiac arrest",
    "Appendicitis",
    "Nausea and vomiting",
    "Head injury",
    "Respiratory distress",
    "Stroke",
    "Severe abdominal pain",
    "Burns",
    "Severe allergic reaction",
    "Internal bleeding",
    "Pneumonia",
    "Diabetic emergency",
    "Spinal injury",
]

# Grid zone boundaries (from data-contracts.md §6)
#   WAITING:      cols 0-7,  rows 0-5
#   GENERAL WARD: cols 0-11, rows 6-12
#   ICU:          cols 12-19, rows 6-12
#   DISCHARGE:    cols 0-19, rows 13-14

_ZONE = {
    "waiting":      (0.5, 6.5, 0.5, 4.5),
    "general_ward": (0.5, 10.5, 6.5, 11.5),
    "icu":          (12.5, 18.5, 6.5, 11.5),
    "discharged":   (0.5, 18.5, 13.0, 14.0),
}

_DOCTOR_DEFAULTS = [
    dict(id=1, name="Dr. Patel",   specialty="ICU",       grid_x=14.0, grid_y=8.0),
    dict(id=2, name="Dr. Kim",     specialty="General",   grid_x=5.0,  grid_y=9.0),
    dict(id=3, name="Dr. Jones",   specialty="Triage",    grid_x=3.0,  grid_y=2.0),
    dict(id=4, name="Dr. Okonkwo", specialty="Emergency", grid_x=8.0,  grid_y=10.0),
]

# Zone in which each doctor roams
_DOCTOR_ZONE = {
    1: "icu",
    2: "general_ward",
    3: "waiting",
    4: "general_ward",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _poisson(lam: float) -> int:
    """Knuth's algorithm for a Poisson-distributed random integer."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _random_in_zone(zone_name: str) -> tuple[float, float]:
    x0, x1, y0, y1 = _ZONE[zone_name]
    return random.uniform(x0, x1), random.uniform(y0, y1)


# ─── Engine ───────────────────────────────────────────────────────────────────

class MockSimulationEngine:
    """
    Generates realistic-looking SimulationState data without the real engine.
    Implements the same interface that main.py expects:
        .is_running, .current_tick
        .start(), .pause(), .reset()
        .trigger_surge(), .trigger_shortage(), .trigger_recovery()
        .apply_config(ScenarioConfig)
        async .tick() -> SimulationState
        .get_state() -> SimulationState
        .get_metrics_history() -> list[MetricsSnapshot]
    """

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._tick: int = 0
        self._running: bool = False
        self._scenario: str = "normal"

        self._patients: list[Patient] = []
        self._doctors: list[Doctor] = []
        self._beds: list[Bed] = []

        self._next_patient_id: int = 1
        self._total_arrived: int = 0
        self._total_discharged: int = 0
        self._discharge_ticks: list[int] = []  # tick at which each discharge happened
        self._treatment_durations: list[int] = []  # for avg_treatment_time calc

        self._arrival_rate: float = 1.5
        self._metrics_history: list[MetricsSnapshot] = []
        self._last_events: list[SimEvent] = []

        # Shortage state: which doctor ids are disabled
        self._shortage_disabled: set[int] = set()

        self._init_hospital()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_tick(self) -> int:
        return self._tick

    # ── Control commands ──────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True

    def pause(self) -> None:
        self._running = False

    def reset(self) -> None:
        self.__init__()

    def trigger_surge(self) -> None:
        self._scenario = "surge"
        # Add a burst of new patients immediately to make the effect visible
        events: list[SimEvent] = []
        for _ in range(random.randint(5, 8)):
            self._add_patient(events, severity_bias="critical")
        self._last_events = events

    def trigger_shortage(self) -> None:
        self._scenario = "shortage"
        # Disable doctors 3 and 4 (indices 2 and 3)
        self._shortage_disabled = {3, 4}
        for doc in self._doctors:
            if doc.id in self._shortage_disabled:
                doc.is_available = False

    def trigger_recovery(self) -> None:
        self._scenario = "normal"
        self._shortage_disabled = set()
        # Re-enable all doctors
        for doc in self._doctors:
            doc.is_available = len(doc.assigned_patient_ids) < doc.capacity

    def apply_config(self, config) -> None:
        """Update runtime configuration from a ScenarioConfig."""
        if config is None:
            return
        rate = getattr(config, "arrival_rate_per_tick", None)
        if rate is not None:
            self._arrival_rate = float(rate)
        # General/ICU bed counts and doctor count changes would require
        # complex state surgery; for the mock we just update arrival rate.
        # tick_speed_seconds is handled by the main loop, not the engine.

    # ── Tick ──────────────────────────────────────────────────────────────────

    async def tick(self) -> SimulationState:
        """Advance simulation by one tick, return new state."""
        self._tick += 1
        self._evolve_state()
        state = self.get_state()
        # Store metrics snapshot for history
        self._metrics_history.append(state.metrics)
        if len(self._metrics_history) > 100:
            self._metrics_history.pop(0)
        return state

    # ── State accessors ───────────────────────────────────────────────────────

    def get_state(self) -> SimulationState:
        """Build and return the current SimulationState dataclass."""
        wards = self._build_wards()
        metrics = self._build_metrics()
        return SimulationState(
            tick=self._tick,
            timestamp=time.time(),
            patients=list(self._patients),
            doctors=list(self._doctors),
            beds=list(self._beds),
            wards=wards,
            metrics=metrics,
            events=list(self._last_events),
            scenario=self._scenario,
            is_running=self._running,
        )

    def get_metrics_history(self) -> list[MetricsSnapshot]:
        return list(self._metrics_history)

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_hospital(self) -> None:
        """
        Spawn fixed hospital layout:
        - 20 general ward beds (cols 1-9, rows 7-11)
        - 5 ICU beds (cols 13-17, rows 7-9)
        - 4 doctors
        - 3 initial waiting patients
        """
        self._beds = []
        bed_id = 1

        # General ward: 4 rows × 5 cols = 20 beds
        for row in range(4):
            for col in range(5):
                self._beds.append(Bed(
                    id=bed_id,
                    ward="general_ward",
                    occupied_by_patient_id=None,
                    grid_x=1.0 + col * 2.0,    # x: 1, 3, 5, 7, 9
                    grid_y=7.0 + row * 1.5,     # y: 7, 8.5, 10, 11.5
                ))
                bed_id += 1

        # ICU: 5 beds at fixed positions
        icu_positions = [(13.0, 7.0), (15.0, 7.0), (17.0, 7.0),
                         (13.0, 9.5), (15.0, 9.5)]
        for x, y in icu_positions:
            self._beds.append(Bed(
                id=bed_id,
                ward="icu",
                occupied_by_patient_id=None,
                grid_x=x,
                grid_y=y,
            ))
            bed_id += 1

        # Doctors
        self._doctors = [
            Doctor(
                id=spec["id"],
                name=spec["name"],
                assigned_patient_ids=[],
                capacity=3,
                workload="light",
                specialty=spec["specialty"],
                grid_x=spec["grid_x"],
                grid_y=spec["grid_y"],
                is_available=True,
                decisions_made=0,
            )
            for spec in _DOCTOR_DEFAULTS
        ]

        # 3 initial waiting patients (no events tracked at init)
        self._patients = []
        init_events: list[SimEvent] = []
        for _ in range(3):
            self._add_patient(init_events)
        self._last_events = []  # don't expose init arrivals as tick-0 events

    # ── State evolution ───────────────────────────────────────────────────────

    def _evolve_state(self) -> None:
        """Called each tick. Advances hospital state one step."""
        events: list[SimEvent] = []

        # 1. New patient arrivals
        if self._scenario == "surge":
            n_arrivals = _poisson(3.5)
        else:
            n_arrivals = _poisson(self._arrival_rate)

        for _ in range(n_arrivals):
            self._add_patient(events)

        # 2. Assign waiting patients to available doctors
        self._assign_patients(events)

        # 3. Advance treatment, discharge completed patients
        self._advance_treatment(events)

        # 4. Evolve patient conditions
        self._evolve_conditions(events)

        # 5. Nudge doctor positions (random walk within zone)
        self._move_doctors()

        # 6. Update doctor is_available flags after all assignments/discharges
        for doc in self._doctors:
            if doc.id not in self._shortage_disabled:
                doc.is_available = len(doc.assigned_patient_ids) < doc.capacity

        self._last_events = events

    def _add_patient(
        self,
        events: list[SimEvent],
        severity_bias: Optional[str] = None,
    ) -> Patient:
        """Spawn a new patient in the waiting area and append an arrival event."""
        if severity_bias == "critical":
            weights = [0.1, 0.3, 0.6]
        elif self._scenario == "surge":
            weights = [0.25, 0.40, 0.35]
        else:
            weights = [0.50, 0.35, 0.15]

        severity = random.choices(["low", "medium", "critical"], weights=weights)[0]
        treatment_duration = {
            "low": random.randint(5, 9),
            "medium": random.randint(3, 7),
            "critical": random.randint(6, 14),
        }[severity]

        gx, gy = _random_in_zone("waiting")
        patient = Patient(
            id=self._next_patient_id,
            name=f"Patient #{self._next_patient_id}",
            severity=severity,
            condition="stable",
            location="waiting",
            assigned_doctor_id=None,
            arrived_at_tick=self._tick,
            treatment_started_tick=None,
            treatment_duration_ticks=treatment_duration,
            wait_time_ticks=0,
            age=random.randint(18, 90),
            diagnosis=random.choice(_DIAGNOSES),
            grid_x=gx,
            grid_y=gy,
            last_event_explanation=None,
        )
        self._patients.append(patient)
        self._next_patient_id += 1
        self._total_arrived += 1

        event_severity = (
            "critical" if severity == "critical"
            else "warning" if severity == "medium"
            else "info"
        )
        events.append(SimEvent(
            tick=self._tick,
            event_type="patient_arrived",
            entity_id=patient.id,
            entity_type="patient",
            raw_description=(
                f"Patient #{patient.id} arrived: {patient.diagnosis} "
                f"({severity} severity, age {patient.age})"
            ),
            llm_explanation=None,
            severity=event_severity,
        ))
        return patient

    def _assign_patients(self, events: list[SimEvent]) -> None:
        """
        Assign unassigned waiting patients to available doctors.
        Priority: critical patients first, then longest wait time.
        """
        waiting = [
            p for p in self._patients
            if p.location == "waiting" and p.assigned_doctor_id is None
        ]
        # Sort: critical > medium > low, then by wait time descending
        waiting.sort(key=lambda p: (
            0 if p.severity == "critical" else 1 if p.severity == "medium" else 2,
            -p.wait_time_ticks,
        ))

        for patient in waiting:
            doc = self._find_available_doctor(patient)
            if doc is None:
                break  # no capacity left — remaining patients wait

            # Choose target ward and find a free bed
            if patient.severity == "critical":
                bed = self._find_free_bed("icu") or self._find_free_bed("general_ward")
            else:
                bed = self._find_free_bed("general_ward") or self._find_free_bed("icu")

            if bed is None:
                continue  # no beds at all — patient stays in waiting

            # Assign doctor → patient → bed
            doc.assigned_patient_ids.append(patient.id)
            doc.workload = self._calc_workload(doc)
            doc.is_available = len(doc.assigned_patient_ids) < doc.capacity
            doc.decisions_made += 1

            patient.assigned_doctor_id = doc.id
            patient.location = bed.ward
            patient.treatment_started_tick = self._tick
            patient.grid_x = bed.grid_x
            patient.grid_y = bed.grid_y

            bed.occupied_by_patient_id = patient.id

            event_sev = "critical" if patient.severity == "critical" else "info"
            events.append(SimEvent(
                tick=self._tick,
                event_type="patient_assigned",
                entity_id=doc.id,
                entity_type="doctor",
                raw_description=(
                    f"{doc.name} assigned to Patient #{patient.id} "
                    f"({patient.severity}, {patient.diagnosis}) in {bed.ward}"
                ),
                llm_explanation=None,
                severity=event_sev,
            ))

    def _advance_treatment(self, events: list[SimEvent]) -> None:
        """Discharge patients whose treatment is complete."""
        to_discharge = [
            p for p in self._patients
            if p.location in ("general_ward", "icu")
            and p.treatment_started_tick is not None
            and (self._tick - p.treatment_started_tick) >= p.treatment_duration_ticks
        ]
        for patient in to_discharge:
            self._discharge_patient(patient, events)

    def _discharge_patient(self, patient: Patient, events: list[SimEvent]) -> None:
        """Free bed, unlink from doctor, move patient to discharged zone."""
        # Free bed
        for bed in self._beds:
            if bed.occupied_by_patient_id == patient.id:
                bed.occupied_by_patient_id = None
                break

        # Unlink doctor
        if patient.assigned_doctor_id is not None:
            doc = self._get_doctor(patient.assigned_doctor_id)
            if doc is not None and patient.id in doc.assigned_patient_ids:
                doc.assigned_patient_ids.remove(patient.id)
                doc.workload = self._calc_workload(doc)
                if doc.id not in self._shortage_disabled:
                    doc.is_available = len(doc.assigned_patient_ids) < doc.capacity
            patient.assigned_doctor_id = None

        # Record treatment duration for stats
        if patient.treatment_started_tick is not None:
            self._treatment_durations.append(
                self._tick - patient.treatment_started_tick
            )

        patient.location = "discharged"
        patient.condition = "improving"
        patient.grid_x, patient.grid_y = _random_in_zone("discharged")

        self._total_discharged += 1
        self._discharge_ticks.append(self._tick)

        events.append(SimEvent(
            tick=self._tick,
            event_type="patient_discharged",
            entity_id=patient.id,
            entity_type="patient",
            raw_description=f"Patient #{patient.id} discharged after treatment",
            llm_explanation=None,
            severity="info",
        ))

    def _evolve_conditions(self, events: list[SimEvent]) -> None:
        """
        Randomly evolve patient conditions each tick.
        - Waiting patients accumulate wait_time and may worsen.
        - Patients in treatment mostly improve, small chance of deterioration.
        """
        for patient in self._patients:
            if patient.location == "discharged":
                continue

            if patient.location == "waiting":
                patient.wait_time_ticks += 1

                # Critical patients deteriorate faster when untreated
                if patient.severity == "critical" and random.random() < 0.12:
                    patient.condition = "worsening"
                # Medium may escalate to critical after long waits
                elif (
                    patient.severity == "medium"
                    and patient.wait_time_ticks >= 4
                    and random.random() < 0.08
                ):
                    old_sev = patient.severity
                    patient.severity = "critical"
                    patient.condition = "worsening"
                    events.append(SimEvent(
                        tick=self._tick,
                        event_type="patient_escalated",
                        entity_id=patient.id,
                        entity_type="patient",
                        raw_description=(
                            f"Patient #{patient.id} escalated from {old_sev} "
                            f"to critical after {patient.wait_time_ticks} ticks waiting"
                        ),
                        llm_explanation=None,
                        severity="critical",
                    ))

            elif patient.location in ("general_ward", "icu"):
                r = random.random()
                if r < 0.30:
                    if patient.condition != "improving":
                        patient.condition = "improving"
                        events.append(SimEvent(
                            tick=self._tick,
                            event_type="patient_improved",
                            entity_id=patient.id,
                            entity_type="patient",
                            raw_description=f"Patient #{patient.id} condition improving",
                            llm_explanation=None,
                            severity="info",
                        ))
                elif r < 0.40:
                    patient.condition = "stable"
                elif r < 0.45 and patient.severity != "critical":
                    # Small chance of deterioration even in treatment
                    patient.condition = "worsening"

    def _move_doctors(self) -> None:
        """Random-walk each doctor within their assigned zone."""
        for doc in self._doctors:
            zone = _DOCTOR_ZONE.get(doc.id, "general_ward")
            x0, x1, y0, y1 = _ZONE[zone]
            doc.grid_x = _clamp(doc.grid_x + random.uniform(-0.4, 0.4), x0, x1)
            doc.grid_y = _clamp(doc.grid_y + random.uniform(-0.4, 0.4), y0, y1)

    # ── State builders ────────────────────────────────────────────────────────

    def _build_wards(self) -> dict:
        """Build the wards dict from current bed/patient state."""
        general_beds = [b for b in self._beds if b.ward == "general_ward"]
        icu_beds = [b for b in self._beds if b.ward == "icu"]

        general_occupied = sum(
            1 for b in general_beds if b.occupied_by_patient_id is not None
        )
        icu_occupied = sum(
            1 for b in icu_beds if b.occupied_by_patient_id is not None
        )
        waiting_count = sum(1 for p in self._patients if p.location == "waiting")

        # Pass empty beds list to Ward — top-level state.beds carries bed detail.
        # This avoids duplicating all bed data inside every ward object.
        return {
            "waiting": Ward(
                name="waiting",
                capacity=50,
                occupied=waiting_count,
                beds=[],
            ),
            "general_ward": Ward(
                name="general_ward",
                capacity=20,
                occupied=general_occupied,
                beds=[],
            ),
            "icu": Ward(
                name="icu",
                capacity=5,
                occupied=icu_occupied,
                beds=[],
            ),
            "discharged": Ward(
                name="discharged",
                capacity=999,
                occupied=self._total_discharged,
                beds=[],
            ),
        }

    def _build_metrics(self) -> MetricsSnapshot:
        """Compute current MetricsSnapshot from live state."""
        waiting_patients = [p for p in self._patients if p.location == "waiting"]
        general_occupied = sum(
            1 for b in self._beds
            if b.ward == "general_ward" and b.occupied_by_patient_id is not None
        )
        icu_occupied = sum(
            1 for b in self._beds
            if b.ward == "icu" and b.occupied_by_patient_id is not None
        )

        # Average wait time (patients currently waiting)
        avg_wait = 0.0
        if waiting_patients:
            avg_wait = sum(p.wait_time_ticks for p in waiting_patients) / len(
                waiting_patients
            )

        # Average treatment time (last 20 completed treatments)
        avg_treatment = 0.0
        recent_durations = self._treatment_durations[-20:]
        if recent_durations:
            avg_treatment = sum(recent_durations) / len(recent_durations)

        # Doctor utilisation: fraction of total capacity currently used
        total_slots = sum(d.capacity for d in self._doctors)
        used_slots = sum(len(d.assigned_patient_ids) for d in self._doctors)
        doctor_utilisation = (used_slots / total_slots * 100.0) if total_slots > 0 else 0.0

        # Throughput: discharges in last 10 ticks
        throughput = sum(
            1 for t in self._discharge_ticks if self._tick - t < 10
        )

        critical_waiting = sum(
            1 for p in waiting_patients if p.severity == "critical"
        )

        return MetricsSnapshot(
            tick=self._tick,
            simulated_hour=self._tick,
            total_patients_arrived=self._total_arrived,
            total_patients_discharged=self._total_discharged,
            avg_wait_time_ticks=round(avg_wait, 2),
            avg_treatment_time_ticks=round(avg_treatment, 2),
            current_queue_length=len(waiting_patients),
            general_ward_occupancy_pct=round(general_occupied / 20.0 * 100.0, 2),
            icu_occupancy_pct=round(icu_occupied / 5.0 * 100.0, 2),
            doctor_utilisation_pct=round(doctor_utilisation, 2),
            throughput_last_10_ticks=throughput,
            critical_patients_waiting=critical_waiting,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _find_free_bed(self, ward: str) -> Optional[Bed]:
        for bed in self._beds:
            if bed.ward == ward and bed.occupied_by_patient_id is None:
                return bed
        return None

    def _find_available_doctor(self, patient: Patient) -> Optional[Doctor]:
        """
        Find the best available doctor for this patient.
        ICU doctors are preferred for critical patients.
        Otherwise prefer the least-loaded doctor.
        """
        available = [
            d for d in self._doctors
            if d.is_available
            and len(d.assigned_patient_ids) < d.capacity
            and d.id not in self._shortage_disabled
        ]
        if not available:
            return None

        if patient.severity == "critical":
            icu_docs = [d for d in available if d.specialty == "ICU"]
            if icu_docs:
                return min(icu_docs, key=lambda d: len(d.assigned_patient_ids))

        return min(available, key=lambda d: len(d.assigned_patient_ids))

    def _get_doctor(self, doctor_id: int) -> Optional[Doctor]:
        for doc in self._doctors:
            if doc.id == doctor_id:
                return doc
        return None

    @staticmethod
    def _calc_workload(doc: Doctor) -> str:
        n = len(doc.assigned_patient_ids)
        if n == 0:
            return "light"
        elif n == 1:
            return "moderate"
        elif n == 2:
            return "heavy"
        else:
            return "overwhelmed"

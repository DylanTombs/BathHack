"""
Shared domain types for the Hospital Simulation Platform.
Source of truth: .claude/data-contracts.md §1

All backend modules import from here. Frontend types are mirrored in
frontend/src/types/simulation.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


# ─── Type Aliases ─────────────────────────────────────────────────────────────

Severity = Literal["low", "medium", "critical"]
PatientCondition = Literal["stable", "worsening", "improving"]
PatientLocation = Literal["waiting", "general_ward", "icu", "discharged"]
WorkloadLevel = Literal["light", "moderate", "heavy", "overwhelmed"]
WardName = Literal["waiting", "general_ward", "icu", "discharged"]
EventSeverity = Literal["info", "warning", "critical"]
EventType = Literal[
    "patient_arrived",
    "patient_assigned",
    "patient_escalated",
    "patient_improved",
    "patient_discharged",
    "doctor_decision",
    "surge_triggered",
    "staff_shortage",
    "icu_overload",
]


# ─── Patient ──────────────────────────────────────────────────────────────────

@dataclass
class Patient:
    id: int
    name: str                                # e.g. "Patient #12"
    severity: Severity
    condition: PatientCondition
    location: PatientLocation
    assigned_doctor_id: Optional[int]        # None if unassigned
    arrived_at_tick: int
    treatment_started_tick: Optional[int]    # None until treatment begins
    treatment_duration_ticks: int            # how many ticks treatment takes
    wait_time_ticks: int                     # ticks spent waiting
    age: int
    diagnosis: str                           # e.g. "Chest pain"
    # Grid position for UI rendering
    grid_x: float
    grid_y: float
    # LLM explanation for last condition change (optional)
    last_event_explanation: Optional[str] = None


# ─── Doctor ───────────────────────────────────────────────────────────────────

@dataclass
class Doctor:
    id: int
    name: str                                # e.g. "Dr. Smith"
    assigned_patient_ids: list[int]          # currently treating
    capacity: int                            # max concurrent patients
    workload: WorkloadLevel
    specialty: str                           # "General", "ICU", "Triage"
    grid_x: float
    grid_y: float
    is_available: bool                       # False if at max capacity
    decisions_made: int                      # total decisions this session


# ─── Bed ──────────────────────────────────────────────────────────────────────

@dataclass
class Bed:
    id: int
    ward: WardName
    occupied_by_patient_id: Optional[int]   # None if free
    grid_x: float
    grid_y: float


# ─── Ward / Hospital Resource ─────────────────────────────────────────────────

@dataclass
class Ward:
    name: WardName
    capacity: int
    occupied: int
    beds: list[Bed] = field(default_factory=list)

    @property
    def occupancy_pct(self) -> float:
        return (self.occupied / self.capacity * 100) if self.capacity > 0 else 0.0

    @property
    def is_full(self) -> bool:
        return self.occupied >= self.capacity


# ─── Metrics ──────────────────────────────────────────────────────────────────

@dataclass
class MetricsSnapshot:
    tick: int
    simulated_hour: int
    total_patients_arrived: int
    total_patients_discharged: int
    avg_wait_time_ticks: float
    avg_treatment_time_ticks: float
    current_queue_length: int                # waiting, unassigned
    general_ward_occupancy_pct: float
    icu_occupancy_pct: float
    doctor_utilisation_pct: float            # % of doctors at capacity
    throughput_last_10_ticks: int            # discharges in last 10 ticks
    critical_patients_waiting: int


# ─── Events (LLM-generated explanations) ─────────────────────────────────────

@dataclass
class SimEvent:
    tick: int
    event_type: EventType
    entity_id: int                           # patient_id or doctor_id
    entity_type: Literal["patient", "doctor"]
    raw_description: str                     # rule-based fallback text
    llm_explanation: Optional[str]           # populated by Agent 2 if triggered
    severity: EventSeverity


# ─── Simulation State (the broadcast payload) ─────────────────────────────────

@dataclass
class SimulationState:
    tick: int
    timestamp: float                         # unix time
    patients: list[Patient]
    doctors: list[Doctor]
    beds: list[Bed]
    wards: dict[WardName, Ward]
    metrics: MetricsSnapshot
    events: list[SimEvent]                   # events since last tick
    scenario: str                            # "normal", "surge", "shortage"
    is_running: bool


# ─── Control Messages (frontend → backend) ────────────────────────────────────

@dataclass
class ScenarioConfig:
    general_ward_beds: int           # default 20
    icu_beds: int                    # default 5
    num_doctors: int                 # default 4
    arrival_rate_per_tick: float     # mean patients per tick (Poisson)
    tick_speed_seconds: float        # real seconds per sim tick


@dataclass
class TriggerCommand:
    command: Literal[
        "start",
        "pause",
        "reset",
        "trigger_surge",
        "trigger_shortage",
        "trigger_recovery",
        "explain_patient",
        "explain_doctor",
        "update_config",
    ]
    target_id: Optional[int] = None          # for explain_patient / explain_doctor
    config: Optional[ScenarioConfig] = None  # for update_config


# ─── LLM Decision Types (Agent 2 outputs) ────────────────────────────────────

@dataclass
class DoctorDecision:
    target_patient_id: int
    reason: str                              # LLM-generated rationale
    confidence: float                        # 0.0 – 1.0
    fallback_used: bool                      # True if LLM was skipped


@dataclass
class PatientUpdate:
    patient_id: int
    new_condition: PatientCondition
    new_severity: Optional[Severity]         # None = no change
    priority_change: bool
    reason: str                              # LLM-generated rationale
    fallback_used: bool


# ─── LLM Context Objects (inputs to Agent 2) ─────────────────────────────────

@dataclass
class DoctorContext:
    doctor: Doctor
    available_patients: list[Patient]
    icu_is_full: bool
    general_ward_is_full: bool
    current_tick: int


@dataclass
class PatientContext:
    patient: Patient
    ticks_waiting: int
    ward_occupancy_pct: float
    doctor_available: bool
    current_tick: int

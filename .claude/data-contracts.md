# Data Contracts — Shared Types & Wire Format

**All four agents must treat this file as the source of truth.** Any change here requires coordination across all agents.

---

## 1. Core Domain Types (Python)

These live in `backend/simulation/types.py` and are imported by all backend modules.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional
from enum import Enum
import time

# ─── Enums ────────────────────────────────────────────────────────────────────

Severity = Literal["low", "medium", "critical"]
PatientCondition = Literal["stable", "worsening", "improving"]
PatientLocation = Literal["waiting", "general_ward", "icu", "discharged"]
WorkloadLevel = Literal["light", "moderate", "heavy", "overwhelmed"]
WardName = Literal["waiting", "general_ward", "icu", "discharged"]

# ─── Patient ──────────────────────────────────────────────────────────────────

@dataclass
class Patient:
    id: int
    name: str                               # e.g. "Patient #12"
    severity: Severity
    condition: PatientCondition
    location: PatientLocation
    assigned_doctor_id: Optional[int]       # None if unassigned
    arrived_at_tick: int
    treatment_started_tick: Optional[int]   # None until treatment begins
    treatment_duration_ticks: int           # how many ticks treatment takes
    wait_time_ticks: int                    # ticks spent waiting
    age: int                                # cosmetic
    diagnosis: str                          # cosmetic, e.g. "Chest pain"
    # Grid position for UI rendering
    grid_x: float
    grid_y: float
    # LLM explanation for last condition change (optional)
    last_event_explanation: Optional[str] = None

# ─── Doctor ───────────────────────────────────────────────────────────────────

@dataclass
class Doctor:
    id: int
    name: str                               # e.g. "Dr. Smith"
    assigned_patient_ids: list[int]         # currently treating
    capacity: int                           # max concurrent patients
    workload: WorkloadLevel
    specialty: str                          # "General", "ICU", "Triage"
    grid_x: float
    grid_y: float
    is_available: bool                      # False if at max capacity
    decisions_made: int                     # total decisions this session

# ─── Bed ──────────────────────────────────────────────────────────────────────

@dataclass
class Bed:
    id: int
    ward: WardName
    occupied_by_patient_id: Optional[int]  # None if free
    grid_x: float
    grid_y: float

# ─── Ward / Hospital Resource ─────────────────────────────────────────────────

@dataclass
class Ward:
    name: WardName
    capacity: int
    occupied: int
    beds: list[Bed]

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
    current_queue_length: int               # waiting, unassigned
    general_ward_occupancy_pct: float
    icu_occupancy_pct: float
    doctor_utilisation_pct: float           # % of doctors at capacity
    throughput_last_10_ticks: int           # discharges in last 10 ticks
    critical_patients_waiting: int

# ─── Events (LLM-generated explanations) ─────────────────────────────────────

@dataclass
class SimEvent:
    tick: int
    event_type: Literal[
        "patient_arrived",
        "patient_assigned",
        "patient_escalated",
        "patient_improved",
        "patient_discharged",
        "doctor_decision",
        "surge_triggered",
        "staff_shortage",
        "icu_overload"
    ]
    entity_id: int                          # patient_id or doctor_id
    entity_type: Literal["patient", "doctor"]
    raw_description: str                    # rule-based fallback
    llm_explanation: Optional[str]          # populated by Agent 2 if triggered
    severity: Literal["info", "warning", "critical"]

# ─── Simulation State (the broadcast payload) ─────────────────────────────────

@dataclass
class SimulationState:
    tick: int
    timestamp: float                        # unix time
    patients: list[Patient]
    doctors: list[Doctor]
    beds: list[Bed]
    wards: dict[WardName, Ward]
    metrics: MetricsSnapshot
    events: list[SimEvent]                  # events since last tick
    scenario: str                           # "normal", "surge", "shortage"
    is_running: bool

# ─── Control Messages (frontend → backend) ────────────────────────────────────

@dataclass
class ScenarioConfig:
    general_ward_beds: int          # default 20
    icu_beds: int                   # default 5
    num_doctors: int                # default 4
    arrival_rate_per_tick: float    # mean patients per tick (Poisson)
    tick_speed_seconds: float       # real seconds per sim tick

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
        "update_config"
    ]
    target_id: Optional[int] = None         # for explain_patient / explain_doctor
    config: Optional[ScenarioConfig] = None # for update_config

# ─── LLM Decision Types (Agent 2 outputs) ────────────────────────────────────

@dataclass
class DoctorDecision:
    target_patient_id: int
    reason: str                             # LLM-generated
    confidence: float                       # 0.0 – 1.0
    fallback_used: bool                     # True if LLM was skipped

@dataclass
class PatientUpdate:
    patient_id: int
    new_condition: PatientCondition
    new_severity: Optional[Severity]        # None = no change
    priority_change: bool
    reason: str                             # LLM-generated
    fallback_used: bool

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
```

---

## 2. Wire Format (WebSocket JSON)

The WebSocket server (Agent 3) emits this JSON blob every tick. The frontend (Agent 4) consumes it.

```jsonc
// Backend → Frontend (every tick, on "sim_state" event)
{
  "type": "sim_state",
  "tick": 42,
  "timestamp": 1711634400.0,
  "scenario": "surge",
  "is_running": true,
  "patients": [
    {
      "id": 1,
      "name": "Patient #1",
      "severity": "critical",
      "condition": "worsening",
      "location": "icu",
      "assigned_doctor_id": 2,
      "arrived_at_tick": 10,
      "treatment_started_tick": 12,
      "treatment_duration_ticks": 8,
      "wait_time_ticks": 2,
      "age": 67,
      "diagnosis": "Cardiac arrest",
      "grid_x": 3.5,
      "grid_y": 2.0,
      "last_event_explanation": "Patient escalated to ICU due to deteriorating vitals after 2-tick wait"
    }
  ],
  "doctors": [
    {
      "id": 1,
      "name": "Dr. Patel",
      "assigned_patient_ids": [1, 3],
      "capacity": 3,
      "workload": "heavy",
      "specialty": "ICU",
      "grid_x": 4.0,
      "grid_y": 2.5,
      "is_available": true,
      "decisions_made": 14
    }
  ],
  "beds": [
    {
      "id": 1,
      "ward": "icu",
      "occupied_by_patient_id": 1,
      "grid_x": 3.5,
      "grid_y": 2.0
    }
  ],
  "wards": {
    "waiting":      { "name": "waiting",      "capacity": 50, "occupied": 12, "occupancy_pct": 24.0, "is_full": false },
    "general_ward": { "name": "general_ward", "capacity": 20, "occupied": 18, "occupancy_pct": 90.0, "is_full": false },
    "icu":          { "name": "icu",          "capacity": 5,  "occupied": 5,  "occupancy_pct": 100.0,"is_full": true  },
    "discharged":   { "name": "discharged",   "capacity": 999,"occupied": 47, "occupancy_pct": 0.0,  "is_full": false }
  },
  "metrics": {
    "tick": 42,
    "simulated_hour": 42,
    "total_patients_arrived": 61,
    "total_patients_discharged": 47,
    "avg_wait_time_ticks": 3.2,
    "avg_treatment_time_ticks": 6.8,
    "current_queue_length": 12,
    "general_ward_occupancy_pct": 90.0,
    "icu_occupancy_pct": 100.0,
    "doctor_utilisation_pct": 87.5,
    "throughput_last_10_ticks": 8,
    "critical_patients_waiting": 2
  },
  "events": [
    {
      "tick": 42,
      "event_type": "doctor_decision",
      "entity_id": 1,
      "entity_type": "doctor",
      "raw_description": "Dr. Patel assigned to Patient #1",
      "llm_explanation": "Dr. Patel prioritised Patient #1 (cardiac arrest, critical) over Patient #7 (fracture, medium) — ICU capacity is full, immediate intervention required to prevent fatality.",
      "severity": "critical"
    }
  ]
}
```

---

## 3. Frontend → Backend Messages

```jsonc
// Start simulation
{ "type": "command", "command": "start" }

// Pause
{ "type": "command", "command": "pause" }

// Reset
{ "type": "command", "command": "reset" }

// Trigger surge (mass casualty)
{ "type": "command", "command": "trigger_surge" }

// Trigger staff shortage
{ "type": "command", "command": "trigger_shortage" }

// Request explanation for a specific patient
{ "type": "command", "command": "explain_patient", "target_id": 12 }

// Request explanation for a specific doctor
{ "type": "command", "command": "explain_doctor", "target_id": 2 }

// Update simulation config live
{
  "type": "command",
  "command": "update_config",
  "config": {
    "general_ward_beds": 25,
    "icu_beds": 8,
    "num_doctors": 6,
    "arrival_rate_per_tick": 2.5,
    "tick_speed_seconds": 0.5
  }
}
```

---

## 4. Backend → Frontend: One-Off Responses

```jsonc
// Explanation response (after explain_patient or explain_doctor command)
{
  "type": "explanation",
  "target_id": 12,
  "target_type": "patient",
  "explanation": "Patient #12 was escalated from general ward to ICU at tick 38 because their condition deteriorated to critical over 3 ticks of treatment. The ICU slot opened due to Patient #9's discharge at tick 37.",
  "tick": 42
}

// Config acknowledgement
{
  "type": "config_ack",
  "config": { ... },
  "tick": 42
}

// Error
{
  "type": "error",
  "message": "LLM service unavailable, falling back to rule-based decisions",
  "tick": 42
}
```

---

## 5. TypeScript Types (Frontend — Agent 4)

```typescript
// frontend/src/types/simulation.ts

export type Severity = 'low' | 'medium' | 'critical';
export type PatientCondition = 'stable' | 'worsening' | 'improving';
export type PatientLocation = 'waiting' | 'general_ward' | 'icu' | 'discharged';
export type WorkloadLevel = 'light' | 'moderate' | 'heavy' | 'overwhelmed';
export type WardName = 'waiting' | 'general_ward' | 'icu' | 'discharged';
export type EventSeverity = 'info' | 'warning' | 'critical';

export interface Patient {
  id: number;
  name: string;
  severity: Severity;
  condition: PatientCondition;
  location: PatientLocation;
  assigned_doctor_id: number | null;
  arrived_at_tick: number;
  treatment_started_tick: number | null;
  treatment_duration_ticks: number;
  wait_time_ticks: number;
  age: number;
  diagnosis: string;
  grid_x: number;
  grid_y: number;
  last_event_explanation: string | null;
}

export interface Doctor {
  id: number;
  name: string;
  assigned_patient_ids: number[];
  capacity: number;
  workload: WorkloadLevel;
  specialty: string;
  grid_x: number;
  grid_y: number;
  is_available: boolean;
  decisions_made: number;
}

export interface Bed {
  id: number;
  ward: WardName;
  occupied_by_patient_id: number | null;
  grid_x: number;
  grid_y: number;
}

export interface WardState {
  name: WardName;
  capacity: number;
  occupied: number;
  occupancy_pct: number;
  is_full: boolean;
}

export interface Metrics {
  tick: number;
  simulated_hour: number;
  total_patients_arrived: number;
  total_patients_discharged: number;
  avg_wait_time_ticks: number;
  avg_treatment_time_ticks: number;
  current_queue_length: number;
  general_ward_occupancy_pct: number;
  icu_occupancy_pct: number;
  doctor_utilisation_pct: number;
  throughput_last_10_ticks: number;
  critical_patients_waiting: number;
}

export interface SimEvent {
  tick: number;
  event_type: string;
  entity_id: number;
  entity_type: 'patient' | 'doctor';
  raw_description: string;
  llm_explanation: string | null;
  severity: EventSeverity;
}

export interface SimulationState {
  type: 'sim_state';
  tick: number;
  timestamp: number;
  scenario: string;
  is_running: boolean;
  patients: Patient[];
  doctors: Doctor[];
  beds: Bed[];
  wards: Record<WardName, WardState>;
  metrics: Metrics;
  events: SimEvent[];
}

export interface ExplanationResponse {
  type: 'explanation';
  target_id: number;
  target_type: 'patient' | 'doctor';
  explanation: string;
  tick: number;
}

export interface ScenarioConfig {
  general_ward_beds: number;
  icu_beds: number;
  num_doctors: number;
  arrival_rate_per_tick: number;
  tick_speed_seconds: number;
}
```

---

## 6. Grid Layout Constants

The hospital map uses a logical grid. All `grid_x` / `grid_y` values are in grid units (not pixels — scaling is handled by the renderer).

```
Grid: 20 columns × 15 rows

┌─────────────────────────────────────────────┐  Row 0
│  WAITING AREA          (cols 0-7, rows 0-5) │
│                                             │
├──────────────────────┬──────────────────────┤  Row 6
│  GENERAL WARD        │  ICU                 │
│  (cols 0-11, rows    │  (cols 12-19, rows   │
│   6-12)              │   6-12)              │
├──────────────────────┴──────────────────────┤  Row 13
│  DISCHARGE / EXIT      (cols 0-19, rows     │
│                         13-14)              │
└─────────────────────────────────────────────┘  Row 14

DOCTORS roam within their assigned ward zone.
PATIENTS occupy beds (fixed grid positions per bed).
```

# Agent 1 — Simulation Engine

**Branch:** `feature/simulation-engine`
**Owns:** `backend/simulation/`
**Depends on:** Nothing. This module is pure Python with no network calls, no LLM, no FastAPI.
**Progress file:** `.claude/progress-agent1.md`

---

## Mission

Build the deterministic core of the hospital simulation: patient and doctor agents, hospital resource management, the tick-based event loop, and metrics collection. Every other backend module depends on this — but this module depends on nothing.

The simulation must run standalone, testable via a simple `python -m simulation.engine` invocation that prints state to stdout.

---

## File Structure

```
backend/
├── simulation/
│   ├── __init__.py           # exports SimulationEngine, all types
│   ├── types.py              # all dataclasses from data-contracts.md §1
│   ├── engine.py             # SimulationEngine — main orchestrator
│   ├── patient.py            # PatientAgent class + state transitions
│   ├── doctor.py             # DoctorAgent class + assignment logic
│   ├── hospital.py           # Hospital — owns all wards, beds, resource mgmt
│   ├── queue_manager.py      # PriorityQueue for patient assignment
│   ├── metrics.py            # MetricsCollector
│   └── mock_llm.py           # Stub LLMInterface for testing
├── config.py                 # loads env vars, exposes Config dataclass
└── requirements.txt
```

---

## Detailed Implementation Spec

### `types.py`
Copy verbatim from `data-contracts.md §1`. This is the single source of truth for all domain types. Do not add extra fields without updating the data contract.

---

### `config.py`

```python
import os
from dataclasses import dataclass

@dataclass
class Config:
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    tick_interval_seconds: float = 1.0
    max_beds_general: int = 20
    max_beds_icu: int = 5
    initial_doctors: int = 4
    log_level: str = "INFO"
    arrival_rate_per_tick: float = 1.5   # Poisson mean

def load_config() -> Config:
    return Config(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
        tick_interval_seconds=float(os.getenv("TICK_INTERVAL_SECONDS", "1.0")),
        max_beds_general=int(os.getenv("MAX_BEDS_GENERAL", "20")),
        max_beds_icu=int(os.getenv("MAX_BEDS_ICU", "5")),
        initial_doctors=int(os.getenv("INITIAL_DOCTORS", "4")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        arrival_rate_per_tick=float(os.getenv("ARRIVAL_RATE_PER_TICK", "1.5")),
    )
```

---

### `hospital.py`

Manages all physical resources. No agent logic lives here — pure resource management.

```python
class Hospital:
    def __init__(self, general_beds: int, icu_beds: int): ...

    # Wards
    def get_ward(self, name: WardName) -> Ward: ...
    def all_wards(self) -> dict[WardName, Ward]: ...

    # Bed management
    def assign_bed(self, patient_id: int, ward: WardName) -> Optional[Bed]:
        """Find a free bed in the ward and mark it occupied. Returns None if full."""

    def free_bed(self, patient_id: int) -> None:
        """Mark the bed occupied by patient_id as free."""

    def get_bed_for_patient(self, patient_id: int) -> Optional[Bed]: ...

    def is_ward_full(self, ward: WardName) -> bool: ...
    def free_beds_in(self, ward: WardName) -> int: ...

    # Grid layout
    def _layout_beds(self) -> None:
        """
        Assign grid_x, grid_y to each bed according to the grid spec in
        data-contracts.md §6. Called once at init.
        Waiting: rows 0-5, cols 0-7
        General ward: rows 6-12, cols 0-11
        ICU: rows 6-12, cols 12-19
        Discharge: rows 13-14, cols 0-19
        """
```

**Bed layout algorithm:** Place beds in a regular grid within each zone. For N beds in a zone that spans R rows × C cols, distribute evenly with padding. Return floating-point grid coordinates so the frontend can place icons precisely.

---

### `patient.py`

```python
class PatientAgent:
    """
    Wraps a Patient dataclass with state-transition logic.
    All rule-based transitions live here.
    LLM decisions are injected via the llm_callback.
    """

    NAMES = ["Alice", "Bob", "Carol", ...]         # 50 names
    DIAGNOSES = {
        "critical": ["Cardiac arrest", "Stroke", "Severe trauma", "Septic shock"],
        "medium":   ["Appendicitis", "Fracture", "Pneumonia", "Chest pain"],
        "low":      ["Sprain", "Minor laceration", "Headache", "Nausea"],
    }
    TREATMENT_TICKS = {
        "critical": (6, 12),   # (min, max) ticks range
        "medium":   (3, 7),
        "low":      (1, 4),
    }

    def __init__(self, patient: Patient, llm_callback=None): ...

    # ── Tick update ──────────────────────────────────────────────────────────

    async def tick(self, tick: int, hospital: Hospital) -> list[SimEvent]:
        """
        Called once per simulation tick for this patient.
        Returns list of events that occurred this tick.
        """

    # ── State transitions (rule-based) ────────────────────────────────────────

    def _increment_wait(self) -> None:
        """Increment wait_time_ticks if patient is in waiting/unassigned state."""

    def _progress_treatment(self) -> Optional[SimEvent]:
        """
        If patient is being treated, decrement remaining treatment ticks.
        If treatment completes:
          - condition stable/improving → discharge
          - condition worsening → escalate severity or move to ICU
        """

    def _check_deterioration(self) -> Optional[SimEvent]:
        """
        Rule-based deterioration check:
        - low severity patient waiting > 5 ticks → 10% chance per tick of → medium
        - medium severity waiting > 3 ticks → 15% chance per tick of → critical
        - critical anywhere + doctor unavailable > 2 ticks → 20% chance of death event
        - Worsening condition while in general ward → candidate for ICU escalation
        """

    # ── LLM trigger check ─────────────────────────────────────────────────────

    def _should_call_llm_for_reevaluation(self, tick: int) -> bool:
        """
        Returns True when:
        - Tick is a multiple of PATIENT_REEVAL_EVERY_N (default 5)
        - OR condition just changed to worsening
        - OR patient has been waiting > CRITICAL_WAIT_THRESHOLD ticks
        - NOT if patient is discharged
        """

    async def _llm_reevaluate(self, tick: int, hospital: Hospital) -> Optional[SimEvent]:
        """
        Calls llm_callback.patient_reevaluate(context) if available.
        Falls back to rule-based if llm_callback is None or raises.
        Returns an event with llm_explanation populated.
        """

    # ── Factory ───────────────────────────────────────────────────────────────

    @staticmethod
    def create_new(patient_id: int, tick: int, hospital: Hospital) -> 'PatientAgent':
        """
        Generate a new patient with stochastic severity:
          60% low, 30% medium, 10% critical
        Random name, diagnosis appropriate to severity, random age 18-90.
        Place in waiting zone with a free grid position.
        """
```

**Patient lifecycle state machine:**

```
ARRIVE (waiting, unassigned)
  │
  ├─[bed available + doctor available]──→ ASSIGNED (waiting → ward/icu)
  │                                           │
  │                                    [treatment starts]
  │                                           │
  │                                    IN_TREATMENT (ward/icu)
  │                                           │
  │                              ┌────────────┴────────────┐
  │                         [improving]               [worsening]
  │                              │                        │
  │                          DISCHARGE              [escalate?]
  │                                                       │
  │                                              [ICU if critical]
  │
  └─[waiting too long]──→ DETERIORATE (severity++)
```

---

### `doctor.py`

```python
class DoctorAgent:
    """
    Manages a Doctor's assignment decisions and workload tracking.
    Rule-based default: always pick highest-severity waiting patient.
    LLM decision: injected via llm_callback.
    """

    NAMES = ["Dr. Patel", "Dr. Kim", "Dr. Jones", "Dr. Okonkwo", "Dr. Silva", ...]
    SPECIALTIES = ["General", "ICU", "Triage", "Emergency", "Cardiology"]

    def __init__(self, doctor: Doctor, llm_callback=None): ...

    async def tick(self, tick: int, waiting_patients: list[PatientAgent],
                   hospital: Hospital) -> list[SimEvent]:
        """
        Called once per tick.
        1. If doctor has capacity, decide which patient to take next.
        2. Update workload level.
        3. Emit decision events.
        """

    # ── Decision logic ────────────────────────────────────────────────────────

    async def decide_next_patient(
        self,
        candidates: list[PatientAgent],
        tick: int,
        hospital: Hospital,
    ) -> Optional[PatientAgent]:
        """
        Candidates = unassigned patients doctor can treat given their specialty.
        Returns chosen patient or None.
        Calls LLM only when _should_call_llm_for_decision() is True.
        """

    def _rule_based_pick(self, candidates: list[PatientAgent]) -> Optional[PatientAgent]:
        """
        Priority order:
        1. critical severity (longest waiting first)
        2. medium severity (longest waiting first)
        3. low severity (longest waiting first)
        Ties broken by arrived_at_tick (FIFO).
        """

    def _should_call_llm_for_decision(self, tick: int, candidates: list[PatientAgent]) -> bool:
        """
        LLM is triggered when:
        - At least 2 critical patients are waiting simultaneously
        - OR ICU is full AND a critical patient is in general ward
        - OR workload is 'overwhelmed'
        - NOT more than once every DOCTOR_LLM_COOLDOWN_TICKS (default 3) ticks
        """

    async def _llm_decide(self, candidates: list[PatientAgent],
                          tick: int, hospital: Hospital) -> Optional[PatientAgent]:
        """
        Build DoctorContext and call llm_callback.doctor_decide().
        If LLM returns invalid patient_id, fall back to rule-based.
        Populate event.llm_explanation from DoctorDecision.reason.
        """

    def _assign_patient(self, patient: PatientAgent, tick: int) -> SimEvent: ...

    def _update_workload(self) -> None:
        """
        light:       0 patients assigned
        moderate:    1 to capacity//2
        heavy:       capacity//2+1 to capacity-1
        overwhelmed: at capacity
        """

    @staticmethod
    def create_initial(doctor_id: int, num_doctors: int) -> 'DoctorAgent':
        """
        Create a doctor with name from NAMES list, assign specialty,
        set capacity=3, place in appropriate ward zone on grid.
        Distribute doctors evenly across wards.
        """
```

---

### `queue_manager.py`

```python
class PriorityQueue:
    """
    Maintains the ordered list of unassigned patients.
    Priority: critical > medium > low, then FIFO within severity.
    """

    def __init__(self): ...

    def push(self, patient: PatientAgent) -> None: ...
    def pop(self) -> Optional[PatientAgent]: ...
    def peek(self) -> Optional[PatientAgent]: ...
    def remove(self, patient_id: int) -> None: ...
    def get_all(self) -> list[PatientAgent]: ...
    def length(self) -> int: ...

    def get_by_severity(self, severity: Severity) -> list[PatientAgent]: ...
    def critical_count(self) -> int: ...
```

---

### `metrics.py`

```python
class MetricsCollector:
    """
    Collects per-tick metrics and computes rolling statistics.
    Maintains a history buffer of the last 100 ticks for charts.
    """

    def __init__(self): ...

    def record_tick(self, tick: int, hospital: Hospital,
                    queue: PriorityQueue,
                    all_patients: list[PatientAgent],
                    all_doctors: list[DoctorAgent]) -> MetricsSnapshot: ...

    def record_discharge(self, patient: PatientAgent, tick: int) -> None:
        """Track wait + treatment times for rolling averages."""

    def get_history(self) -> list[MetricsSnapshot]:
        """Returns last 100 snapshots — used to seed chart history on connect."""

    def get_throughput_window(self, last_n_ticks: int = 10) -> int:
        """Count discharges in the last N ticks."""
```

---

### `engine.py`

This is the main orchestrator. It owns the tick loop and coordinates all sub-components.

```python
class SimulationEngine:
    """
    Main simulation orchestrator.
    Designed to be driven externally (Agent 3 calls tick() on a timer).
    """

    def __init__(self, config: Config, llm_callback=None):
        self.config = config
        self.llm_callback = llm_callback      # injected by Agent 3 after merge
        self.hospital = Hospital(config.max_beds_general, config.max_beds_icu)
        self.queue = PriorityQueue()
        self.metrics = MetricsCollector()
        self.patients: dict[int, PatientAgent] = {}
        self.doctors: list[DoctorAgent] = []
        self._tick = 0
        self._running = False
        self._scenario = "normal"
        self._patient_id_counter = 0
        self._events_this_tick: list[SimEvent] = []

        self._init_doctors()

    # ── Public API (called by Agent 3) ────────────────────────────────────────

    async def tick(self) -> SimulationState:
        """
        Advance simulation by one tick. Returns full SimulationState.
        Thread-safe: should be called from a single async task.

        Tick order:
        1. Generate new patients (stochastic arrival)
        2. Update all patient states (deterioration, treatment progress)
        3. Run doctor assignment decisions
        4. Move patients between wards (bed assignments)
        5. Discharge completed patients
        6. Collect metrics
        7. Clear events buffer
        8. Return SimulationState
        """

    def apply_config(self, config: ScenarioConfig) -> None:
        """
        Hot-reload config mid-simulation.
        Adding beds/doctors: spawn new resources.
        Removing beds: mark excess beds unavailable (don't evict patients).
        """

    def trigger_surge(self) -> None:
        """
        Mass casualty event:
        - arrival_rate_per_tick *= 4 for 10 ticks
        - 50% of new arrivals are critical/medium
        - Emit surge event
        """

    def trigger_shortage(self) -> None:
        """
        Staff shortage:
        - Randomly incapacitate 50% of doctors for 8 ticks
        - Emit shortage event
        """

    def trigger_recovery(self) -> None:
        """Reset scenario to normal."""

    def get_metrics(self) -> MetricsSnapshot: ...

    def get_state(self) -> SimulationState:
        """Build and return current SimulationState without advancing tick."""

    def reset(self) -> None:
        """Full reset — new hospital, new queues, tick=0."""

    def start(self) -> None: ...
    def pause(self) -> None: ...

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _generate_arrivals(self) -> list[PatientAgent]:
        """
        Draw from Poisson(arrival_rate_per_tick).
        During surge: scale rate, adjust severity distribution.
        """

    def _assign_beds(self) -> None:
        """
        For each newly arrived patient (unassigned, no bed):
        - critical → try ICU first, then general ward
        - medium/low → general ward only
        Sets patient.location based on assigned ward.
        """

    def _run_doctor_assignments(self) -> None:
        """
        For each available doctor (capacity > current assigned):
          call doctor.decide_next_patient(queue candidates)
          assign chosen patient, update queue
        """

    def _discharge_patients(self) -> None:
        """
        Find patients whose treatment is complete and condition != worsening.
        Move to 'discharged', free their bed.
        """

    def _build_state(self) -> SimulationState:
        """Serialise all agents + hospital + metrics into SimulationState."""

    def _init_doctors(self) -> None:
        """Create initial set of DoctorAgent instances from config."""
```

---

### `mock_llm.py`

Used for testing Agent 1 in isolation without Agent 2 present.

```python
class MockLLMInterface:
    """
    Synchronous stub that returns plausible-looking LLM decisions
    without calling any API. Useful for testing the engine standalone.
    """

    async def doctor_decide(self, context: DoctorContext) -> DoctorDecision:
        # Pick highest severity patient (same as rule-based)
        best = max(context.available_patients, key=lambda p: {"critical":2,"medium":1,"low":0}[p.severity])
        return DoctorDecision(
            target_patient_id=best.id,
            reason=f"[MOCK] Critical severity requires immediate attention",
            confidence=0.9,
            fallback_used=True,
        )

    async def patient_reevaluate(self, context: PatientContext) -> PatientUpdate:
        return PatientUpdate(
            patient_id=context.patient.id,
            new_condition=context.patient.condition,
            new_severity=None,
            priority_change=False,
            reason="[MOCK] No change",
            fallback_used=True,
        )

    async def explain_event(self, event: SimEvent) -> str:
        return f"[MOCK] {event.raw_description}"
```

---

## Simulation Constants

```python
# In engine.py or constants.py
PATIENT_REEVAL_EVERY_N_TICKS = 5
DOCTOR_LLM_COOLDOWN_TICKS = 3
CRITICAL_WAIT_THRESHOLD_TICKS = 4
MAX_WAIT_BEFORE_DEATH_TICKS = 15        # critical patient, no bed, no doctor
SURGE_DURATION_TICKS = 10
SHORTAGE_DURATION_TICKS = 8
METRICS_HISTORY_BUFFER = 100
```

---

## Standalone Test Mode

`engine.py` should have an `if __name__ == "__main__"` block:

```python
if __name__ == "__main__":
    import asyncio
    from simulation.mock_llm import MockLLMInterface

    config = load_config()
    engine = SimulationEngine(config, llm_callback=MockLLMInterface())
    engine.start()

    async def run():
        for i in range(20):
            state = await engine.tick()
            print(f"Tick {state.tick}: {len(state.patients)} patients, "
                  f"queue={state.metrics.current_queue_length}, "
                  f"icu={state.metrics.icu_occupancy_pct:.0f}%")
            for ev in state.events:
                print(f"  [{ev.severity}] {ev.llm_explanation or ev.raw_description}")
            await asyncio.sleep(0)

    asyncio.run(run())
```

---

## Dependencies (`requirements.txt` additions)

```
# No external deps for simulation module itself
# Only stdlib: random, dataclasses, asyncio, typing, enum, math
```

---

## Integration Handoff to Agent 3

When Agent 3 merges this branch, they import:

```python
from simulation.engine import SimulationEngine
from simulation.types import SimulationState, ScenarioConfig, TriggerCommand
from config import load_config
```

The engine is instantiated once at server startup and `await engine.tick()` is called on a repeating async timer.
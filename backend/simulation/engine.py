"""
SimulationEngine — main orchestrator for the hospital simulation.

Designed to be driven externally: Agent 3 calls await engine.tick() on a
repeating async timer and broadcasts the returned SimulationState.

Public API (used by Agent 3):
  engine.tick()                  → SimulationState
  engine.apply_config(config)    → None
  engine.trigger_surge()         → None
  engine.trigger_shortage()      → None
  engine.trigger_recovery()      → None
  engine.get_metrics()           → MetricsSnapshot
  engine.get_state()             → SimulationState
  engine.reset()                 → None
  engine.start()                 → None
  engine.pause()                 → None
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from typing import Optional

from simulation.types import (
    ScenarioConfig,
    SimEvent,
    SimulationState,
    MetricsSnapshot,
    ArrivalContext,
    PatientSpec,
)
from simulation.hospital import Hospital
from simulation.patient import PatientAgent, _make_random_spec
from simulation.doctor import DoctorAgent
from simulation.queue_manager import PriorityQueue
from simulation.metrics import MetricsCollector

try:
    from config import load_config, Config
except ImportError:
    # Fallback for when running from a different CWD
    from simulation.types import ScenarioConfig as _SC
    Config = None  # type: ignore[assignment]
    load_config = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ─── Engine-level simulation constants ────────────────────────────────────────
PATIENT_REEVAL_EVERY_N_TICKS = 5
DOCTOR_LLM_COOLDOWN_TICKS = 3
CRITICAL_WAIT_THRESHOLD_TICKS = 4
MAX_WAIT_BEFORE_DEATH_TICKS = 15
SURGE_DURATION_TICKS = 10
SHORTAGE_DURATION_TICKS = 8
METRICS_HISTORY_BUFFER = 100

# Severity distribution during a surge (overrides normal 60/30/10)
_SURGE_SEVERITY_WEIGHTS = [("low", 0.20), ("medium", 0.30), ("critical", 0.50)]

# Simulated calendar — tick 0 = Monday 06:00, each tick = 15 simulated minutes
_SIM_START_DAY = 0    # 0=Monday
_SIM_START_HOUR = 6   # 06:00
_SIM_MINS_PER_TICK = 15
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _sim_datetime(tick: int) -> str:
    """Return a human-readable simulated datetime string for a given tick."""
    total_minutes = _SIM_START_HOUR * 60 + tick * _SIM_MINS_PER_TICK
    hour = (total_minutes // 60) % 24
    minute = total_minutes % 60
    day = (_SIM_START_DAY + total_minutes // (24 * 60)) % 7
    return f"{_DAY_NAMES[day]} {hour:02d}:{minute:02d}"


def _sim_hour_day(tick: int) -> tuple[int, int, str]:
    """Return (hour_of_day, day_of_week, day_name) for a given tick."""
    total_minutes = _SIM_START_HOUR * 60 + tick * _SIM_MINS_PER_TICK
    hour = (total_minutes // 60) % 24
    day = (_SIM_START_DAY + total_minutes // (24 * 60)) % 7
    return hour, day, _DAY_NAMES[day]


class SimulationEngine:
    """
    Main simulation orchestrator.
    Designed to be driven externally (Agent 3 calls tick() on a timer).

    Thread-safety: tick() is async and should be called from a single async task.
    """

    def __init__(self, config, llm_callback=None) -> None:
        self.config = config
        self.llm_callback = llm_callback

        # Core components
        self.hospital: Hospital = Hospital(
            config.max_beds_general, config.max_beds_icu
        )
        self.queue: PriorityQueue = PriorityQueue()
        self.metrics: MetricsCollector = MetricsCollector()

        # Agents
        self.patients: dict[int, PatientAgent] = {}
        self.doctors: list[DoctorAgent] = []

        # State
        self._tick: int = 0
        self._running: bool = False
        self._scenario: str = "normal"
        self._patient_id_counter: int = 0
        self._events_this_tick: list[SimEvent] = []

        # Surge state
        self._surge_ticks_remaining: int = 0
        self._surge_arrival_multiplier: float = 1.0

        # Shortage state
        self._shortage_ticks_remaining: int = 0
        self._incapacitated_doctor_ids: list[int] = []

        # Effective arrival rate (can be modified by apply_config or surge)
        self._arrival_rate: float = config.arrival_rate_per_tick

        self._init_doctors()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_tick(self) -> int:
        return self._tick

    def start(self) -> None:
        self._running = True

    def pause(self) -> None:
        self._running = False

    async def tick(self) -> SimulationState:
        """
        Advance simulation by one tick. Returns full SimulationState.

        Tick order:
          1. Generate new patient arrivals
          2. Update patient states (deterioration, treatment progress)
          3. Run doctor assignment decisions
          4. Assign beds to newly arrived patients / ICU escalations
          5. Discharge completed patients
          6. Collect metrics
          7. Build & return SimulationState (clears events buffer)
        """
        if not self._running:
            return self._build_state()

        self._tick += 1
        self._events_this_tick = []

        # ── Surge / shortage countdown ─────────────────────────────────────
        self._update_scenario_timers()

        # ── Step 1: Arrivals ───────────────────────────────────────────────
        new_patients = await self._generate_arrivals()
        for pa in new_patients:
            self.patients[pa.patient.id] = pa
            self.queue.push(pa)
            self.metrics.record_arrival()
            self._events_this_tick.append(SimEvent(
                tick=self._tick,
                event_type="patient_arrived",
                entity_id=pa.patient.id,
                entity_type="patient",
                raw_description=(
                    f"{pa.patient.name} arrived: {pa.patient.severity} — "
                    f"{pa.patient.diagnosis}"
                ),
                llm_explanation=None,
                severity=(
                    "critical" if pa.patient.severity == "critical"
                    else "warning" if pa.patient.severity == "medium"
                    else "info"
                ),
            ))

        # ── Step 2: Patient state updates ─────────────────────────────────
        patient_events = await self._update_patients()
        self._events_this_tick.extend(patient_events)

        # ── Step 3: Doctor assignment decisions ───────────────────────────
        assignment_events = await self._run_doctor_assignments()
        self._events_this_tick.extend(assignment_events)

        # ── Step 4: Bed assignment (new arrivals + ICU escalations) ───────
        self._assign_beds()

        # ── Step 5: Discharge completed patients ──────────────────────────
        self._discharge_patients()

        # ── Step 6: Collect metrics ────────────────────────────────────────
        snapshot = self.metrics.record_tick(
            self._tick,
            self.hospital,
            self.queue,
            list(self.patients.values()),
            self.doctors,
        )

        # ── Check for ICU overload ─────────────────────────────────────────
        if self.hospital.is_ward_full("icu"):
            has_critical_outside = any(
                pa.patient.severity == "critical"
                and pa.patient.location != "icu"
                for pa in self.patients.values()
                if pa.patient.location != "discharged"
            )
            if has_critical_outside:
                self._events_this_tick.append(SimEvent(
                    tick=self._tick,
                    event_type="icu_overload",
                    entity_id=0,
                    entity_type="doctor",
                    raw_description="ICU is full; critical patients cannot be escalated",
                    llm_explanation=None,
                    severity="critical",
                ))

        return self._build_state()

    def apply_config(self, config: ScenarioConfig) -> None:
        """
        Hot-reload config mid-simulation.
        Adding beds: spawn new resources.
        Removing beds: mark excess unavailable (no patient eviction).
        """
        current_gw = len(self.hospital.get_ward("general_ward").beds)
        current_icu = len(self.hospital.get_ward("icu").beds)

        if config.general_ward_beds > current_gw:
            self.hospital.add_general_beds(config.general_ward_beds - current_gw)
        if config.icu_beds > current_icu:
            self.hospital.add_icu_beds(config.icu_beds - current_icu)
        if config.general_ward_beds < current_gw:
            # Cannot physically remove occupied beds; just reduce capacity
            self.hospital.get_ward("general_ward").capacity = config.general_ward_beds
        if config.icu_beds < current_icu:
            self.hospital.get_ward("icu").capacity = config.icu_beds

        # Add or remove doctors
        current_doctors = len(self.doctors)
        if config.num_doctors > current_doctors:
            for i in range(current_doctors + 1, config.num_doctors + 1):
                self.doctors.append(
                    DoctorAgent.create_initial(i, config.num_doctors, self.llm_callback)
                )
        elif config.num_doctors < current_doctors:
            # Retire excess doctors (no abrupt patient removal)
            self.doctors = self.doctors[: config.num_doctors]

        self._arrival_rate = config.arrival_rate_per_tick

    def add_doctor(self, specialty: str = "General") -> None:
        """Add a new doctor with the given specialty mid-simulation."""
        new_id = max((d.doctor.id for d in self.doctors), default=0) + 1
        da = DoctorAgent.create_with_specialty(new_id, specialty, self.llm_callback)
        self.doctors.append(da)
        logger.info("Added %s doctor (id=%d). Total doctors: %d", specialty, new_id, len(self.doctors))

    def remove_doctor(self) -> None:
        """Remove the most recently added doctor (keep at least 1)."""
        if len(self.doctors) <= 1:
            logger.warning("Cannot remove last doctor")
            return
        removed = self.doctors.pop()
        logger.info("Removed %s (id=%d). Total doctors: %d",
                    removed.doctor.name, removed.doctor.id, len(self.doctors))

    def trigger_surge(self) -> None:
        """
        Mass casualty event:
          - arrival_rate *= 4 for SURGE_DURATION_TICKS ticks
          - 50% of new arrivals are critical/medium
          - Emit surge_triggered event
        """
        self._surge_ticks_remaining = SURGE_DURATION_TICKS
        self._surge_arrival_multiplier = 4.0
        self._scenario = "surge"
        logger.info("Surge triggered at tick %d", self._tick)
        self._events_this_tick.append(SimEvent(
            tick=self._tick,
            event_type="surge_triggered",
            entity_id=0,
            entity_type="doctor",
            raw_description=f"Mass casualty event: arrival rate × {self._surge_arrival_multiplier:.0f} for {SURGE_DURATION_TICKS} ticks",
            llm_explanation=None,
            severity="critical",
        ))

    def trigger_shortage(self) -> None:
        """
        Staff shortage: reduce to exactly 1 doctor per specialty.
        All others are incapacitated for SHORTAGE_DURATION_TICKS ticks.
        """
        from collections import defaultdict
        by_specialty: dict[str, list[int]] = defaultdict(list)
        for d in self.doctors:
            by_specialty[d.doctor.specialty].append(d.doctor.id)

        incapacitate = []
        for ids in by_specialty.values():
            incapacitate.extend(ids[1:])  # keep first of each specialty, bench the rest

        self._incapacitated_doctor_ids = incapacitate
        self._shortage_ticks_remaining = SHORTAGE_DURATION_TICKS
        self._scenario = "shortage"
        n_incapacitate = len(incapacitate)
        n_total = len(self.doctors)
        logger.info(
            "Shortage triggered at tick %d; %d/%d doctors incapacitated (1 per specialty kept)",
            self._tick, n_incapacitate, n_total,
        )
        self._events_this_tick.append(SimEvent(
            tick=self._tick,
            event_type="staff_shortage",
            entity_id=0,
            entity_type="doctor",
            raw_description=(
                f"Staff shortage: reduced to 1 doctor per specialty "
                f"({n_total - n_incapacitate} active, {n_incapacitate} stood down)"
            ),
            llm_explanation=None,
            severity="critical",
        ))

    def trigger_recovery(self) -> None:
        """Reset scenario to normal."""
        self._surge_ticks_remaining = 0
        self._surge_arrival_multiplier = 1.0
        self._shortage_ticks_remaining = 0
        self._incapacitated_doctor_ids = []
        self._scenario = "normal"
        logger.info("Recovery triggered at tick %d", self._tick)

    def get_metrics(self) -> MetricsSnapshot:
        history = self.metrics.get_history()
        if history:
            return history[-1]
        # Return a zeroed snapshot if no ticks recorded yet
        return MetricsSnapshot(
            tick=self._tick,
            simulated_hour=self._tick,
            total_patients_arrived=0,
            total_patients_discharged=0,
            avg_wait_time_ticks=0.0,
            avg_treatment_time_ticks=0.0,
            current_queue_length=0,
            general_ward_occupancy_pct=0.0,
            icu_occupancy_pct=0.0,
            doctor_utilisation_pct=0.0,
            throughput_last_10_ticks=0,
            critical_patients_waiting=0,
        )

    def get_metrics_history(self) -> list[MetricsSnapshot]:
        """Return last 100 MetricsSnapshot entries (used by API to seed frontend charts)."""
        return self.metrics.get_history()

    def get_state(self) -> SimulationState:
        """Build and return current SimulationState without advancing tick."""
        return self._build_state()

    def reset(self) -> None:
        """Full reset — new hospital, new queues, tick=0."""
        self.hospital = Hospital(
            self.config.max_beds_general, self.config.max_beds_icu
        )
        self.queue = PriorityQueue()
        self.metrics = MetricsCollector()
        self.patients = {}
        self.doctors = []
        self._tick = 0
        self._running = False
        self._scenario = "normal"
        self._patient_id_counter = 0
        self._events_this_tick = []
        self._surge_ticks_remaining = 0
        self._surge_arrival_multiplier = 1.0
        self._shortage_ticks_remaining = 0
        self._incapacitated_doctor_ids = []
        self._arrival_rate = self.config.arrival_rate_per_tick
        self._init_doctors()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _init_doctors(self) -> None:
        """Create initial DoctorAgent instances from config."""
        n = self.config.initial_doctors
        for i in range(1, n + 1):
            self.doctors.append(
                DoctorAgent.create_initial(i, n, self.llm_callback)
            )

    def _next_patient_id(self) -> int:
        self._patient_id_counter += 1
        return self._patient_id_counter

    def _update_scenario_timers(self) -> None:
        """Count down surge / shortage durations and reset when expired."""
        if self._surge_ticks_remaining > 0:
            self._surge_ticks_remaining -= 1
            if self._surge_ticks_remaining == 0:
                self._surge_arrival_multiplier = 1.0
                if self._scenario == "surge":
                    self._scenario = "normal"

        if self._shortage_ticks_remaining > 0:
            self._shortage_ticks_remaining -= 1
            if self._shortage_ticks_remaining == 0:
                self._incapacitated_doctor_ids = []
                if self._scenario == "shortage":
                    self._scenario = "normal"

    async def _generate_arrivals(self) -> list[PatientAgent]:
        """
        Generate new patient arrivals for this tick.

        Primary path (LLM): calls generate_patient_batch with time/hospital context;
        LLM decides count and generates coherent patient identities.

        Fallback path (rule-based): Poisson draw + static-pool random assembly,
        identical to the original behaviour.
        """
        rate = self._arrival_rate * self._surge_arrival_multiplier
        poisson_count = _poisson_draw(rate)

        def _fallback_specs() -> list[PatientSpec]:
            specs = []
            for _ in range(poisson_count):
                force_sev = None
                if self._surge_ticks_remaining > 0:
                    r, cum = random.random(), 0.0
                    for sev, w in _SURGE_SEVERITY_WEIGHTS:
                        cum += w
                        if r < cum:
                            force_sev = sev  # type: ignore[assignment]
                            break
                specs.append(_make_random_spec(force_sev))
            return specs

        generate_fn = getattr(self.llm_callback, "generate_patient_batch", None)
        if generate_fn is None:
            specs = _fallback_specs()
        else:
            metrics = self.get_metrics()
            hour, day, day_name = _sim_hour_day(self._tick)
            ctx = ArrivalContext(
                tick=self._tick,
                hour_of_day=hour,
                day_of_week=day,
                day_name=day_name,
                sim_datetime=_sim_datetime(self._tick),
                scenario=self._scenario,
                surge_active=self._surge_ticks_remaining > 0,
                current_queue_length=metrics.current_queue_length,
                general_ward_occupancy_pct=metrics.general_ward_occupancy_pct,
                icu_occupancy_pct=metrics.icu_occupancy_pct,
                arrival_rate_hint=rate,
            )
            specs = await generate_fn(ctx, _fallback_specs)

        arrivals = []
        for spec in specs:
            pid = self._next_patient_id()
            arrivals.append(PatientAgent.create_from_spec(
                patient_id=pid,
                tick=self._tick,
                hospital=self.hospital,
                spec=spec,
                llm_callback=self.llm_callback,
            ))
        return arrivals

    async def _update_patients(self) -> list[SimEvent]:
        """Call tick() on every living patient and collect events."""
        events: list[SimEvent] = []
        tasks = [
            pa.tick(self._tick, self.hospital)
            for pa in self.patients.values()
            if pa.patient.location != "discharged"
        ]
        results = await asyncio.gather(*tasks)
        for result in results:
            events.extend(result)
        return events

    async def _run_doctor_assignments(self) -> list[SimEvent]:
        """
        For each available doctor (not incapacitated):
          - Get all unassigned patients from queue
          - Call doctor.tick() which assigns patients up to capacity
          - Remove assigned patients from queue
        """
        events: list[SimEvent] = []

        for doctor_agent in self.doctors:
            # Skip incapacitated doctors during shortage
            if doctor_agent.doctor.id in self._incapacitated_doctor_ids:
                continue
            if not doctor_agent.doctor.is_available:
                continue

            # Candidates = all unassigned patients in the queue
            candidates = self.queue.get_all()
            if not candidates:
                break

            doctor_events = await doctor_agent.tick(
                self._tick, candidates, self.hospital
            )
            events.extend(doctor_events)

            # Remove newly-assigned patients from queue
            for ev in doctor_events:
                if ev.event_type == "doctor_decision":
                    # Find the patient who was just assigned to this doctor
                    # by looking at what changed in the doctor's list
                    # The last assigned patient is the one in doctor_events
                    pass

            # Clean way: after tick, remove any patient whose assigned_doctor_id is now set
            for pa in list(self.queue.get_all()):
                if pa.patient.assigned_doctor_id is not None:
                    self.queue.remove(pa.patient.id)

        return events

    def _assign_beds(self) -> None:
        """
        For each patient without a bed:
          - critical → try ICU first, then general ward
          - medium/low → general ward only
        Also handle ICU escalation for worsening critical patients in general_ward.
        Sets patient.location and grid_x/y based on assigned bed.
        """
        # Phase A: assign beds to patients who just arrived (location="waiting", no bed)
        for pa in list(self.patients.values()):
            p = pa.patient
            if p.location != "waiting":
                continue
            if self.hospital.get_bed_for_patient(p.id) is not None:
                continue  # already has a bed

            if p.severity == "critical":
                # Try ICU first
                bed = self.hospital.assign_bed(p.id, "icu")
                if bed:
                    p.location = "icu"
                    p.grid_x = bed.grid_x
                    p.grid_y = bed.grid_y
                    # Release waiting slot
                    self.hospital.release_waiting_slot(p.id)
                    continue
                # Fall through to general ward

            # Medium / low (or critical when ICU full) → general ward
            bed = self.hospital.assign_bed(p.id, "general_ward")
            if bed:
                p.location = "general_ward"
                p.grid_x = bed.grid_x
                p.grid_y = bed.grid_y
                self.hospital.release_waiting_slot(p.id)

        # Phase B: ICU escalation — worsening critical patients currently in general_ward
        for pa in list(self.patients.values()):
            p = pa.patient
            if (
                p.location == "general_ward"
                and p.severity == "critical"
                and p.condition == "worsening"
                and not self.hospital.is_ward_full("icu")
            ):
                # Free general ward bed
                self.hospital.free_bed(p.id)
                # Assign ICU bed
                icu_bed = self.hospital.assign_bed(p.id, "icu")
                if icu_bed:
                    p.location = "icu"
                    p.grid_x = icu_bed.grid_x
                    p.grid_y = icu_bed.grid_y
                    self._events_this_tick.append(SimEvent(
                        tick=self._tick,
                        event_type="patient_escalated",
                        entity_id=p.id,
                        entity_type="patient",
                        raw_description=(
                            f"{p.name} escalated from general ward to ICU "
                            f"(critical + worsening)"
                        ),
                        llm_explanation=None,
                        severity="critical",
                    ))

    def _discharge_patients(self) -> None:
        """
        Find patients whose treatment is complete and condition != worsening.
        Move to 'discharged', free their bed, update doctor list.
        """
        for pa in list(self.patients.values()):
            p = pa.patient
            if p.location == "discharged":
                continue
            if p.treatment_started_tick is None or p.assigned_doctor_id is None:
                continue

            elapsed = self._tick - p.treatment_started_tick
            if elapsed < p.treatment_duration_ticks:
                continue
            if p.condition == "worsening":
                continue  # treatment will be extended by _progress_treatment()

            # Discharge
            old_location = p.location
            p.location = "discharged"

            # Free bed
            self.hospital.free_bed(p.id)

            # Remove from doctor's list
            for doctor_agent in self.doctors:
                if p.id in doctor_agent.doctor.assigned_patient_ids:
                    doctor_agent.doctor.assigned_patient_ids.remove(p.id)
                    doctor_agent._update_workload()
                    break

            # Record in metrics
            self.metrics.record_discharge(pa, self._tick)

            # Move to discharge zone grid position
            gx, gy = self.hospital.next_discharged_position()
            p.grid_x = gx
            p.grid_y = gy

            self._events_this_tick.append(SimEvent(
                tick=self._tick,
                event_type="patient_discharged",
                entity_id=p.id,
                entity_type="patient",
                raw_description=(
                    f"{p.name} discharged after {elapsed} ticks of treatment"
                ),
                llm_explanation=p.last_event_explanation,
                severity="info",
            ))

            logger.debug(
                "Tick %d: %s discharged from %s after %d ticks",
                self._tick, p.name, old_location, elapsed,
            )

    def _build_state(self) -> SimulationState:
        """Serialise all agents + hospital + metrics into SimulationState."""
        metrics = self.get_metrics()
        wards = self.hospital.all_wards()
        beds = self.hospital.get_all_beds()

        return SimulationState(
            tick=self._tick,
            timestamp=time.time(),
            sim_datetime=_sim_datetime(self._tick),
            patients=[pa.patient for pa in self.patients.values()],
            doctors=[da.doctor for da in self.doctors],
            beds=beds,
            wards=wards,
            metrics=metrics,
            events=list(self._events_this_tick),
            scenario=self._scenario,
            is_running=self._running,
        )


# ─── Poisson draw helper ──────────────────────────────────────────────────────

def _poisson_draw(lam: float) -> int:
    """
    Draw a sample from Poisson(lam) using Knuth's algorithm.
    Pure stdlib — no numpy required.
    """
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


# ─── Standalone test mode ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import sys
    import os

    # Add backend/ to path so 'config' is importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from simulation.mock_llm import MockLLMInterface
    from config import load_config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = load_config()
    engine = SimulationEngine(cfg, llm_callback=MockLLMInterface())
    engine.start()

    async def run() -> None:
        for i in range(20):
            state = await engine.tick()
            print(
                f"Tick {state.tick:>3}: "
                f"{len(state.patients):>2} patients  "
                f"queue={state.metrics.current_queue_length:<3} "
                f"general={state.metrics.general_ward_occupancy_pct:>5.1f}%  "
                f"icu={state.metrics.icu_occupancy_pct:>5.1f}%  "
                f"discharged={state.metrics.total_patients_discharged:<3}"
            )
            for ev in state.events:
                label = ev.llm_explanation or ev.raw_description
                print(f"         [{ev.severity:>8}][{ev.event_type:<20}] {label}")
            await asyncio.sleep(0)

    asyncio.run(run())

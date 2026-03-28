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
SURGE_DURATION_TICKS = 4
SHORTAGE_DURATION_TICKS = 4
METRICS_HISTORY_BUFFER = 100

# Severity rank for priority resolution
_SEVERITY_RANK = {"critical": 2, "medium": 1, "low": 0}

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
        self._benched_doctors: list[DoctorAgent] = []  # physically removed during shortage

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

        # ── Step 4: Resolve pending destinations + auto-route ─────────────
        self._resolve_pending_destinations()

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
        Staff shortage: physically remove all but 1 doctor per specialty.
        Benched doctors are restored on trigger_recovery() or when the timer expires.
        """
        from collections import defaultdict
        by_specialty: dict[str, list] = defaultdict(list)
        for d in self.doctors:
            by_specialty[d.doctor.specialty].append(d)

        active = []
        benched = []
        for doctors_in_spec in by_specialty.values():
            active.append(doctors_in_spec[0])   # keep first of each specialty
            benched.extend(doctors_in_spec[1:]) # bench the rest

        self._benched_doctors = benched
        self.doctors = active
        self._shortage_ticks_remaining = SHORTAGE_DURATION_TICKS
        self._scenario = "shortage"
        logger.info(
            "Shortage triggered at tick %d; %d active, %d benched (1 per specialty kept)",
            self._tick, len(active), len(benched),
        )
        self._events_this_tick.append(SimEvent(
            tick=self._tick,
            event_type="staff_shortage",
            entity_id=0,
            entity_type="doctor",
            raw_description=(
                f"Staff shortage: reduced to 1 doctor per specialty "
                f"({len(active)} active, {len(benched)} stood down)"
            ),
            llm_explanation=None,
            severity="critical",
        ))

    def trigger_recovery(self) -> None:
        """Reset scenario to normal — restores benched doctors and default arrival rate."""
        self._surge_ticks_remaining = 0
        self._surge_arrival_multiplier = 1.0
        self._shortage_ticks_remaining = 0
        self._arrival_rate = self.config.arrival_rate_per_tick
        if self._benched_doctors:
            self.doctors.extend(self._benched_doctors)
            self._benched_doctors = []
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
        self._benched_doctors = []
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
                if self._benched_doctors:
                    self.doctors.extend(self._benched_doctors)
                    self._benched_doctors = []
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
        Ward-scoped doctor assignment:
          - Triage doctors (ward="waiting") see only waiting patients with no pending destination
          - Ward doctors see only unassigned patients in their ward
          - Routing actions are handled immediately after each doctor's turn
        """
        events: list[SimEvent] = []

        for doctor_agent in self.doctors:
            if not doctor_agent.doctor.is_available:
                continue

            doctor_ward = doctor_agent.doctor.ward
            if doctor_ward == "waiting":
                # Triage: only patients in waiting zone who haven't been routed yet
                candidates = [
                    pa for pa in self.queue.get_all()
                    if pa.patient.location == "waiting"
                    and pa.patient.pending_destination is None
                ]
            else:
                # General/ICU: unassigned patients already in this ward
                candidates = [
                    pa for pa in self.queue.get_all()
                    if pa.patient.location == doctor_ward
                ]

            if not candidates:
                continue

            doctor_events = await doctor_agent.tick(
                self._tick, candidates, self.hospital
            )
            events.extend(doctor_events)

            # Remove treated patients (assigned_doctor_id set) from queue
            for pa in list(self.queue.get_all()):
                if pa.patient.assigned_doctor_id is not None:
                    self.queue.remove(pa.patient.id)

            # Process routing actions immediately so other doctors don't re-route
            for pa in list(self.patients.values()):
                action = getattr(pa, "_pending_route_action", None)
                if action is None:
                    continue
                stay = getattr(pa, "_pending_discharge_stay", None)
                dis_sev = getattr(pa, "_pending_discharge_severity", None)
                dis_cond = getattr(pa, "_pending_discharge_condition", None)
                treatment_ticks = getattr(pa, "_pending_treatment_ticks", None)
                for attr in ("_pending_route_action", "_pending_discharge_stay",
                             "_pending_discharge_severity", "_pending_discharge_condition",
                             "_pending_treatment_ticks"):
                    if hasattr(pa, attr):
                        delattr(pa, attr)
                self.queue.remove(pa.patient.id)
                if action == "discharge":
                    self._move_to_discharge(pa, stay or 2, dis_sev, dis_cond)
                else:
                    # Apply triage's treatment estimate before routing
                    if treatment_ticks is not None:
                        pa.patient.treatment_duration_ticks = treatment_ticks
                    pa.patient.pending_destination = action

        return events

    def _resolve_pending_destinations(self) -> None:
        """
        Assign beds to patients routed by Triage doctors (pending_destination set).
        Sorted by severity so critical patients get beds first.
        Patients with no pending_destination stay in waiting until a Triage doctor sees them.
        """
        pending = sorted(
            [pa for pa in self.patients.values() if pa.patient.pending_destination],
            key=lambda pa: -_SEVERITY_RANK[pa.patient.severity],
        )

        for pa in pending:
            p = pa.patient
            dest = p.pending_destination
            bed = self.hospital.assign_bed(p.id, dest)
            if bed:
                # Free the old slot before moving
                if p.location in ("general_ward", "icu"):
                    self.hospital.free_bed(p.id)
                    # Clear old doctor assignment so ward doctor can pick them up fresh
                    for da in self.doctors:
                        if p.id in da.doctor.assigned_patient_ids:
                            da.doctor.assigned_patient_ids.remove(p.id)
                            da._update_workload()
                            break
                    p.assigned_doctor_id = None
                    p.treatment_started_tick = None
                elif p.location == "waiting":
                    self.hospital.release_waiting_slot(p.id)
                p.location = dest
                p.grid_x = bed.grid_x
                p.grid_y = bed.grid_y
                p.pending_destination = None
                # Re-add to queue so ward doctors can treat them next tick
                self.queue.push(pa)

    def _move_to_discharge(
        self,
        pa: PatientAgent,
        stay_ticks: int,
        discharge_severity: Optional[str] = None,
        discharge_condition: Optional[str] = None,
    ) -> None:
        """Move a patient to the discharge zone. Applies LLM-assessed final condition."""
        p = pa.patient
        old_location = p.location

        # Apply LLM-assessed final severity/condition at discharge
        if discharge_severity in ("low", "medium", "critical"):
            p.severity = discharge_severity
        if discharge_condition in ("stable", "worsening", "improving"):
            p.condition = discharge_condition

        p.location = "discharged"
        p.discharge_stay_ticks = stay_ticks
        p.discharge_started_tick = self._tick

        if old_location in ("general_ward", "icu"):
            self.hospital.free_bed(p.id)
        elif old_location == "waiting":
            self.hospital.release_waiting_slot(p.id)

        # Remove from treating doctor's patient list
        for doctor_agent in self.doctors:
            if p.id in doctor_agent.doctor.assigned_patient_ids:
                doctor_agent.doctor.assigned_patient_ids.remove(p.id)
                doctor_agent._update_workload()
                break

        self.metrics.record_discharge(pa, self._tick)
        gx, gy = self.hospital.next_discharged_position()
        p.grid_x = gx
        p.grid_y = gy
        self.queue.remove(p.id)

        self._events_this_tick.append(SimEvent(
            tick=self._tick,
            event_type="patient_discharged",
            entity_id=p.id,
            entity_type="patient",
            raw_description=f"{p.name} discharged (stay: {stay_ticks} ticks)",
            llm_explanation=p.last_event_explanation,
            severity="info",
        ))
        logger.debug(
            "Tick %d: %s discharged from %s (stay %d ticks)",
            self._tick, p.name, old_location, stay_ticks,
        )

    def _discharge_patients(self) -> None:
        """
        Phase A: Remove patients whose discharge stay has expired (clean up from sim).
        Phase B: Auto-discharge patients whose treatment is complete.
        """
        # Phase A: expire patients from discharge zone
        for pa in list(self.patients.values()):
            p = pa.patient
            if p.location == "discharged" and p.discharge_started_tick is not None:
                elapsed = self._tick - p.discharge_started_tick
                if elapsed >= p.discharge_stay_ticks:
                    del self.patients[p.id]

        # Phase B: discharge patients whose treatment is complete
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
                continue  # treatment extended by patient reevaluation

            self._move_to_discharge(pa, 2)

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
            arrival_rate=self._arrival_rate,
            surge_ticks_remaining=self._surge_ticks_remaining,
            shortage_ticks_remaining=self._shortage_ticks_remaining,
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

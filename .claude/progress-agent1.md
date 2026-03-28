# Agent 1 Progress — Simulation Engine

**Branch:** `feature/simulation-engine`
**Spec:** `.claude/agent1-simulation-engine.md`

Update this file as you complete each task. Mark items with:
- `[ ]` — not started
- `[~]` — in progress
- `[x]` — complete
- `[!]` — blocked / needs decision

---

## Phase 0 — Scaffolding
- [ ] Create `backend/` directory structure
- [ ] Create `backend/simulation/__init__.py`
- [ ] Create `backend/requirements.txt` with no external deps (stdlib only for this module)
- [ ] Create `backend/config.py` with `Config` dataclass and `load_config()`
- [ ] Create `.env.example` at repo root

**Done when:** `python -c "from config import load_config; print(load_config())"` runs without error.

---

## Phase 1 — Types
- [ ] Create `backend/simulation/types.py`
- [ ] Copy all dataclasses from `data-contracts.md §1` verbatim
- [ ] Verify: `from simulation.types import Patient, Doctor, SimulationState` imports cleanly

**Done when:** All types import with no errors. No logic — only data definitions.

---

## Phase 2 — Hospital Resource Manager
- [ ] Create `backend/simulation/hospital.py`
- [ ] `Hospital.__init__(general_beds, icu_beds)` — creates all Bed objects
- [ ] `_layout_beds()` — assigns grid_x/grid_y per zone spec in `data-contracts.md §6`
- [ ] `assign_bed(patient_id, ward)` — finds free bed, marks occupied, returns Bed or None
- [ ] `free_bed(patient_id)` — marks bed free
- [ ] `get_bed_for_patient(patient_id)` — lookup
- [ ] `is_ward_full(ward)` and `free_beds_in(ward)`
- [ ] `all_wards()` returns `dict[WardName, Ward]` with live counts

**Done when:** Unit test assigns 20 patients to general ward, 21st returns None.

---

## Phase 3 — Priority Queue
- [ ] Create `backend/simulation/queue_manager.py`
- [ ] `push(patient)` — inserts with priority (critical > medium > low, then FIFO)
- [ ] `pop()` — removes and returns highest priority patient
- [ ] `peek()` — returns without removing
- [ ] `remove(patient_id)` — remove by ID (for when patient is assigned mid-queue)
- [ ] `get_all()` — returns list without mutating
- [ ] `length()` and `critical_count()`
- [ ] `get_by_severity(severity)`

**Done when:** 10 patients of mixed severity are pushed, `pop()` always returns critical-first then medium then low, FIFO within severity.

---

## Phase 4 — Patient Agent
- [ ] Create `backend/simulation/patient.py`
- [ ] `PatientAgent.__init__(patient, llm_callback=None)`
- [ ] `create_new(patient_id, tick, hospital)` — stochastic severity (60/30/10), random name, diagnosis, age, grid position in waiting zone
- [ ] `tick(tick, hospital)` → `list[SimEvent]`
- [ ] `_increment_wait()` — bumps `wait_time_ticks` if unassigned/waiting
- [ ] `_progress_treatment()` — decrements treatment ticks, triggers discharge or escalation
- [ ] `_check_deterioration()` — rule-based probability checks per spec
- [ ] `_should_call_llm_for_reevaluation(tick)` — returns bool
- [ ] `_llm_reevaluate(tick, hospital)` — calls callback or falls back
- [ ] Patient lifecycle state machine transitions all correct

**Done when:** Create 10 patients, run 20 ticks, at least one deterioration event and one discharge occurs. All events have `entity_id`, `entity_type`, `raw_description` populated.

---

## Phase 5 — Doctor Agent
- [ ] Create `backend/simulation/doctor.py`
- [ ] `DoctorAgent.__init__(doctor, llm_callback=None)`
- [ ] `create_initial(doctor_id, num_doctors)` — name, specialty, capacity=3, grid position in ward zone
- [ ] `tick(tick, waiting_patients, hospital)` → `list[SimEvent]`
- [ ] `_rule_based_pick(candidates)` — critical-first, then medium, then low, FIFO tie-break
- [ ] `_should_call_llm_for_decision(tick, candidates)` — checks conditions per spec
- [ ] `_llm_decide(candidates, tick, hospital)` — calls callback, validates patient_id, falls back
- [ ] `_assign_patient(patient, tick)` → `SimEvent`
- [ ] `_update_workload()` — sets workload level based on assigned count vs capacity
- [ ] Doctor does not take more patients than capacity

**Done when:** 4 doctors, 12 waiting patients (mixed severity). Run 5 ticks. All doctors fill to capacity with highest-severity patients. Events emitted for each assignment.

---

## Phase 6 — Metrics Collector
- [ ] Create `backend/simulation/metrics.py`
- [ ] `MetricsCollector.__init__()`
- [ ] `record_tick(tick, hospital, queue, all_patients, all_doctors)` → `MetricsSnapshot`
- [ ] `record_discharge(patient, tick)` — accumulates wait/treatment time totals for rolling avg
- [ ] `get_history()` → list of last 100 MetricsSnapshot
- [ ] `get_throughput_window(last_n_ticks)` — count discharges in last N ticks
- [ ] All `MetricsSnapshot` fields populated correctly

**Done when:** Run 30 ticks. `get_history()` has ≤30 entries. `avg_wait_time_ticks` and `avg_treatment_time_ticks` are non-zero after first discharge. `icu_occupancy_pct` is accurate.

---

## Phase 7 — Simulation Engine
- [ ] Create `backend/simulation/engine.py`
- [ ] `SimulationEngine.__init__(config, llm_callback=None)`
- [ ] `_init_doctors()` — create initial doctors from config
- [ ] `start()` / `pause()` — set `_running`
- [ ] `tick()` — full tick sequence (arrivals → patient updates → doctor decisions → bed assignment → discharge → metrics → build state)
- [ ] `_generate_arrivals()` — Poisson draw, surge modifier
- [ ] `_assign_beds()` — critical → ICU first, then general; medium/low → general only
- [ ] `_run_doctor_assignments()` — iterate available doctors, call decide
- [ ] `_discharge_patients()` — find complete treatments, move to discharged, free bed
- [ ] `_build_state()` → `SimulationState`
- [ ] `apply_config(ScenarioConfig)` — hot reload
- [ ] `trigger_surge()` / `trigger_shortage()` / `trigger_recovery()`
- [ ] `get_metrics()` and `get_state()`
- [ ] `reset()` — full reinitialisation
- [ ] `if __name__ == "__main__"` test run (20 ticks, print state)

**Done when:** `python -m simulation.engine` runs 20 ticks with no errors, prints meaningful output including at least one patient arrival, one assignment, and one discharge.

---

## Phase 8 — Mock LLM + Integration Smoke Test
- [ ] Create `backend/simulation/mock_llm.py` with `MockLLMInterface`
- [ ] All three methods implemented: `doctor_decide`, `patient_reevaluate`, `explain_event`
- [ ] Run `python -m simulation.engine` with `MockLLMInterface` injected — confirm LLM calls are triggered and fallback_used=True events are emitted
- [ ] Confirm trigger guards work: LLM not called every tick

**Done when:** 20-tick run with MockLLMInterface shows some events with `fallback_used=True` and some where the mock was actually called (based on trigger conditions).

---

## Phase 9 — Final Verification Checklist

- [ ] `from simulation.engine import SimulationEngine` works from `backend/` root
- [ ] `from simulation.types import SimulationState, ScenarioConfig, TriggerCommand` works
- [ ] `SimulationState` output matches wire format shape in `data-contracts.md §2` (field names identical)
- [ ] Grid positions for all patients and doctors are within defined zones
- [ ] No import outside stdlib (`random`, `asyncio`, `dataclasses`, `typing`, `math`, `logging`)
- [ ] No hardcoded API keys or URLs

---

## Success Criteria

| Criterion | Signal | Target |
|-----------|--------|--------|
| Engine runs standalone | `python -m simulation.engine` exits clean | Must pass |
| Patient lifecycle complete | Arrival → treatment → discharge observed in 20 ticks | Must pass |
| Priority queue correct | Critical patients always assigned before medium/low | Must pass |
| ICU overload handled | When ICU full, critical patients go to general ward instead | Must pass |
| Surge mode works | `trigger_surge()` causes ≥3x arrival rate for 10 ticks | Must pass |
| Staff shortage works | `trigger_shortage()` reduces effective doctor count | Must pass |
| LLM trigger guards | LLM not called more than GLOBAL_CALLS_PER_TICK_LIMIT times per tick | Must pass |
| Metrics accuracy | `icu_occupancy_pct` matches actual ICU bed count ÷ capacity × 100 | Must pass |
| State serialisable | `dataclasses.asdict(engine.get_state())` produces pure-dict tree | Must pass |
| Hot config reload | `apply_config()` immediately affects next tick | Nice to have |

---

## Integration Handoff Notes

When ready to integrate with Agent 3:
1. Confirm `SimulationEngine` public API matches spec: `tick()`, `apply_config()`, `trigger_surge()`, `trigger_shortage()`, `trigger_recovery()`, `get_state()`, `get_metrics()`, `reset()`, `start()`, `pause()`
2. Confirm `llm_callback` parameter is `None`-safe everywhere
3. Note any field names in `SimulationState` that differ from `data-contracts.md §2` — Agent 3 needs to know
4. Export `SimulationEngine`, `SimulationState`, `ScenarioConfig` from `simulation/__init__.py`
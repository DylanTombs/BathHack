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
- [x] Create `backend/` directory structure
- [x] Create `backend/simulation/__init__.py`
- [x] Create `backend/requirements.txt` with no external deps (stdlib only for this module)
- [x] Create `backend/config.py` with `Config` dataclass and `load_config()`
- [x] Create `.env.example` at repo root

**Done when:** `python -c "from config import load_config; print(load_config())"` runs without error.
**Status:** ✅ COMPLETE — verified

---

## Phase 1 — Types
- [x] Create `backend/simulation/types.py`
- [x] Copy all dataclasses from `data-contracts.md §1` verbatim
- [x] Verify: `from simulation.types import Patient, Doctor, SimulationState` imports cleanly

**Done when:** All types import with no errors. No logic — only data definitions.
**Status:** ✅ COMPLETE — verified

---

## Phase 2 — Hospital Resource Manager
- [x] Create `backend/simulation/hospital.py`
- [x] `Hospital.__init__(general_beds, icu_beds)` — creates all Bed objects
- [x] `_layout_beds()` — assigns grid_x/grid_y per zone spec in `data-contracts.md §6`
- [x] `assign_bed(patient_id, ward)` — finds free bed, marks occupied, returns Bed or None
- [x] `free_bed(patient_id)` — marks bed free
- [x] `get_bed_for_patient(patient_id)` — lookup
- [x] `is_ward_full(ward)` and `free_beds_in(ward)`
- [x] `all_wards()` returns `dict[WardName, Ward]` with live counts
- [x] Waiting zone slot management (`claim_waiting_slot`, `release_waiting_slot`)
- [x] `add_general_beds()` / `add_icu_beds()` for hot-reload

**Done when:** Unit test assigns 20 patients to general ward, 21st returns None.
**Status:** ✅ COMPLETE — verified

---

## Phase 3 — Priority Queue
- [x] Create `backend/simulation/queue_manager.py`
- [x] `push(patient)` — inserts with priority (critical > medium > low, then FIFO)
- [x] `pop()` — removes and returns highest priority patient
- [x] `peek()` — returns without removing
- [x] `remove(patient_id)` — remove by ID (for when patient is assigned mid-queue)
- [x] `get_all()` — returns list without mutating
- [x] `length()` and `critical_count()`
- [x] `get_by_severity(severity)`

**Done when:** 10 patients of mixed severity are pushed, `pop()` always returns critical-first then medium then low, FIFO within severity.
**Status:** ✅ COMPLETE — verified

---

## Phase 4 — Patient Agent
- [x] Create `backend/simulation/patient.py`
- [x] `PatientAgent.__init__(patient, llm_callback=None)`
- [x] `create_new(patient_id, tick, hospital)` — stochastic severity (60/30/10), random name, diagnosis, age, grid position in waiting zone
- [x] `tick(tick, hospital)` → `list[SimEvent]`
- [x] `_increment_wait()` — bumps `wait_time_ticks` if unassigned/waiting
- [x] `_progress_treatment()` — condition changes during treatment (improving/worsening)
- [x] `_check_deterioration()` — rule-based probability checks per spec
- [x] `_should_call_llm_for_reevaluation(tick)` — returns bool
- [x] `_llm_reevaluate(tick, hospital)` — calls callback or falls back
- [x] Patient lifecycle state machine transitions all correct

**Done when:** Create 10 patients, run 20 ticks, at least one deterioration event and one discharge occurs. All events have `entity_id`, `entity_type`, `raw_description` populated.
**Status:** ✅ COMPLETE — verified (deteriorations and improvements observed)

---

## Phase 5 — Doctor Agent
- [x] Create `backend/simulation/doctor.py`
- [x] `DoctorAgent.__init__(doctor, llm_callback=None)`
- [x] `create_initial(doctor_id, num_doctors)` — name, specialty, capacity=3, grid position in ward zone
- [x] `tick(tick, waiting_patients, hospital)` → `list[SimEvent]`
- [x] `_rule_based_pick(candidates)` — critical-first, then medium, then low, FIFO tie-break
- [x] `_should_call_llm_for_decision(tick, candidates)` — checks conditions per spec
- [x] `_llm_decide(candidates, tick, hospital)` — calls callback, validates patient_id, falls back
- [x] `_assign_patient(patient, tick)` → `SimEvent`
- [x] `_update_workload()` — sets workload level based on assigned count vs capacity
- [x] Doctor does not take more patients than capacity
- [x] Fixed: `_pending_doctor_reason` correctly isolated from patient's `last_event_explanation`

**Done when:** 4 doctors, 12 waiting patients (mixed severity). Run 5 ticks. All doctors fill to capacity with highest-severity patients. Events emitted for each assignment.
**Status:** ✅ COMPLETE — verified

---

## Phase 6 — Metrics Collector
- [x] Create `backend/simulation/metrics.py`
- [x] `MetricsCollector.__init__()`
- [x] `record_tick(tick, hospital, queue, all_patients, all_doctors)` → `MetricsSnapshot`
- [x] `record_discharge(patient, tick)` — accumulates wait/treatment time totals for rolling avg
- [x] `get_history()` → list of last 100 MetricsSnapshot
- [x] `get_throughput_window(last_n_ticks)` — count discharges in last N ticks
- [x] All `MetricsSnapshot` fields populated correctly

**Done when:** Run 30 ticks. `get_history()` has ≤30 entries. `avg_wait_time_ticks` and `avg_treatment_time_ticks` are non-zero after first discharge. `icu_occupancy_pct` is accurate.
**Status:** ✅ COMPLETE — verified

---

## Phase 7 — Simulation Engine
- [x] Create `backend/simulation/engine.py`
- [x] `SimulationEngine.__init__(config, llm_callback=None)`
- [x] `_init_doctors()` — create initial doctors from config
- [x] `start()` / `pause()` — set `_running`
- [x] `tick()` — full tick sequence (arrivals → patient updates → doctor decisions → bed assignment → discharge → metrics → build state)
- [x] `_generate_arrivals()` — Poisson draw, surge modifier
- [x] `_assign_beds()` — critical → ICU first, then general; medium/low → general only; ICU escalation for worsening critical
- [x] `_run_doctor_assignments()` — iterate available doctors, call decide
- [x] `_discharge_patients()` — find complete treatments, move to discharged, free bed
- [x] `_build_state()` → `SimulationState`
- [x] `apply_config(ScenarioConfig)` — hot reload
- [x] `trigger_surge()` / `trigger_shortage()` / `trigger_recovery()`
- [x] `get_metrics()` and `get_state()`
- [x] `reset()` — full reinitialisation
- [x] `if __name__ == "__main__"` test run (20 ticks, print state)

**Done when:** `python -m simulation.engine` runs 20 ticks with no errors, prints meaningful output including at least one patient arrival, one assignment, and one discharge.
**Status:** ✅ COMPLETE — verified

---

## Phase 8 — Mock LLM + Integration Smoke Test
- [x] Create `backend/simulation/mock_llm.py` with `MockLLMInterface`
- [x] All three methods implemented: `doctor_decide`, `patient_reevaluate`, `explain_event`
- [x] Run `python -m simulation.engine` with `MockLLMInterface` injected — confirm LLM calls are triggered
- [x] Confirm trigger guards work: LLM not called every tick
- [x] Verified surge causes ≥3× arrival rate for 10 ticks
- [x] Verified shortage incapacitates ~50% of doctors
- [x] Verified recovery returns to normal scenario

**Done when:** 20-tick run with MockLLMInterface shows some events with `fallback_used=True` and some where the mock was actually called (based on trigger conditions).
**Status:** ✅ COMPLETE — verified (604 LLM calls vs 1817 possible = LLM guards working; 63 surge arrivals vs ~15 normal)

---

## Phase 9 — Final Verification Checklist

- [x] `from simulation.engine import SimulationEngine` works from `backend/` root
- [x] `from simulation.types import SimulationState, ScenarioConfig, TriggerCommand` works
- [x] `SimulationState` output matches wire format shape in `data-contracts.md §2` (field names identical)
- [x] Grid positions for all patients and doctors are within defined zones
- [x] No import outside stdlib (`random`, `asyncio`, `dataclasses`, `typing`, `math`, `logging`)
- [x] No hardcoded API keys or URLs
- [x] `dataclasses.asdict(engine.get_state())` produces pure-dict tree ✓
- [x] `apply_config()` immediately affects next tick ✓
- [x] ICU overload handled: critical → general_ward when ICU full ✓
- [x] Metrics accuracy: `icu_occupancy_pct` verified ✓

**Status:** ✅ ALL COMPLETE

---

## Success Criteria

| Criterion | Signal | Status |
|-----------|--------|--------|
| Engine runs standalone | `python -m simulation.engine` exits clean | ✅ PASS |
| Patient lifecycle complete | Arrival → treatment → discharge observed | ✅ PASS |
| Priority queue correct | Critical patients always assigned before medium/low | ✅ PASS |
| ICU overload handled | When ICU full, critical patients go to general ward | ✅ PASS |
| Surge mode works | trigger_surge() causes 4× arrival rate for 10 ticks | ✅ PASS (63 vs ~15 normal) |
| Staff shortage works | trigger_shortage() reduces effective doctor count | ✅ PASS |
| LLM trigger guards | LLM not called every tick | ✅ PASS (33% efficiency) |
| Metrics accuracy | `icu_occupancy_pct` matches actual count ÷ capacity × 100 | ✅ PASS |
| State serialisable | `dataclasses.asdict(engine.get_state())` produces pure dict | ✅ PASS |
| Hot config reload | `apply_config()` immediately affects next tick | ✅ PASS |

---

## Integration Handoff Notes

Agent 1 public API is ready for Agent 3 integration:

```python
from simulation.engine import SimulationEngine
from simulation.types import SimulationState, ScenarioConfig, TriggerCommand
from config import load_config

config = load_config()
engine = SimulationEngine(config, llm_callback=None)  # or inject Agent 2's LLMInterface
engine.start()

# Agent 3 calls this on a repeating async timer:
state: SimulationState = await engine.tick()

# Control:
engine.apply_config(ScenarioConfig(...))
engine.trigger_surge()
engine.trigger_shortage()
engine.trigger_recovery()
engine.reset()
engine.start() / engine.pause()
```

**Notes for Agent 3:**
1. All field names in `SimulationState` match `data-contracts.md §2` exactly
2. `llm_callback=None` is safe — all code guards against it
3. `Ward.occupancy_pct` and `Ward.is_full` are computed properties — they serialize correctly via `dataclasses.asdict()`
4. `discharged` ward capacity is 999 (effectively unbounded)
5. Export `SimulationEngine`, `SimulationState`, `ScenarioConfig` via `simulation/__init__.py`

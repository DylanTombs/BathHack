# Merge Guide — Agent 1 (`feature/simulation-engine`)

**For:** The merging agent / integration lead
**Branch:** `feature/simulation-engine`
**Merge order position:** 1 of 4 — merge this branch **first**

---

## What this branch contains

`backend/simulation/` — the complete, standalone hospital simulation engine.
`backend/config.py` — env-var config loader.
`backend/requirements.txt` — dependency manifest (stdlib only for this module).
`.env.example` — environment variable template.
`.gitignore` — Python / macOS / Node ignores.

No network calls, no FastAPI, no LLM API calls. Pure Python stdlib.

---

## Pre-merge checklist

Run these from `backend/` to confirm the branch is healthy before merging:

```bash
# 1. Smoke test — should run 20 ticks and print meaningful output
python3 -m simulation.engine

# 2. Imports — should print the Config dataclass
python3 -c "from config import load_config; print(load_config())"

# 3. Type imports
python3 -c "from simulation.types import Patient, Doctor, SimulationState; print('ok')"

# 4. Engine import
python3 -c "from simulation.engine import SimulationEngine; print('ok')"
```

All four must exit cleanly with no errors.

---

## Merge steps

```bash
# From main (or integration branch)
git fetch origin
git checkout main
git merge --no-ff origin/feature/simulation-engine
```

**Expected conflicts:** None. This branch only touches:
- `backend/` (new directory, not present on `main`)
- `.env.example` (new file)
- `.gitignore` (new file)
- `.claude/progress-agent1.md` (updated)

If `main` already has any of those files, resolve by keeping both sets of content.

---

## What Agent 3 (backend-api) must do after merge

Agent 3's code imports from this branch. Once merged, their imports will resolve against the real implementation instead of their mocks. The wiring is:

```python
# In backend/api/main.py (Agent 3's file)
from simulation.engine import SimulationEngine
from simulation.types import SimulationState, ScenarioConfig, TriggerCommand
from config import load_config

config = load_config()
engine = SimulationEngine(config, llm_callback=None)  # llm_callback injected after Agent 2 merges
engine.start()

# Agent 3 calls this on a repeating asyncio timer (e.g. every TICK_INTERVAL_SECONDS)
state: SimulationState = await engine.tick()
# → broadcast state over WebSocket as JSON (use dataclasses.asdict(state))

# Command handler (receives TriggerCommand from frontend WebSocket):
match command.command:
    case "start":    engine.start()
    case "pause":    engine.pause()
    case "reset":    engine.reset()
    case "trigger_surge":    engine.trigger_surge()
    case "trigger_shortage": engine.trigger_shortage()
    case "trigger_recovery": engine.trigger_recovery()
    case "update_config":    engine.apply_config(command.config)
```

`dataclasses.asdict(state)` produces a pure-dict tree ready for `json.dumps()`. The shape matches `data-contracts.md §2` exactly.

---

## What Agent 2 (llm-layer) must do after merge

Agent 2 injects their real `LLMInterface` implementation into the engine at startup:

```python
# In backend/api/main.py, after both branches are merged:
from llm.client import LLMClient          # Agent 2's module
from simulation.engine import SimulationEngine
from config import load_config

config = load_config()
llm = LLMClient(config)                   # Agent 2's real implementation
engine = SimulationEngine(config, llm_callback=llm)
engine.start()
```

**The engine is fully `llm_callback=None`-safe.** If Agent 2 is not merged yet, pass `None` and everything falls back to rule-based logic — no import errors, no exceptions.

### LLMInterface contract

Agent 2's client must implement exactly these three async methods:

```python
class LLMInterface(Protocol):
    async def doctor_decide(self, context: DoctorContext) -> DoctorDecision: ...
    async def patient_reevaluate(self, context: PatientContext) -> PatientUpdate: ...
    async def explain_event(self, event: SimEvent) -> str: ...
```

All input/output types live in `simulation.types`. Agent 2 can import them directly:

```python
from simulation.types import (
    DoctorContext, DoctorDecision,
    PatientContext, PatientUpdate,
    SimEvent,
)
```

**When the LLM is triggered (trigger guards already enforced by the engine):**

| Trigger | Frequency |
|---------|-----------|
| `patient_reevaluate` | Every 5 ticks per patient, OR condition just changed to worsening, OR wait > 4 ticks |
| `doctor_decide` | When ≥2 critical patients are waiting, OR ICU full + critical in general ward, OR workload = overwhelmed. Cooldown: max once per 3 ticks per doctor |

---

## Known behaviours to be aware of

### `patient_discharged` events carry `llm_explanation`
When a patient is discharged, the emitted `SimEvent` has `llm_explanation` set to the patient's most recent `last_event_explanation` (which may be an LLM reevaluation reason from the same tick). This is intentional — it gives the UI the LLM context at the point of discharge. Agent 3 should forward it as-is.

### `Ward.occupancy_pct` and `Ward.is_full` are computed properties
`dataclasses.asdict()` does **not** serialise computed properties. Agents 3 and 4 must handle serialisation manually for those two fields, or use the values from the `wards` dict in `SimulationState` which are already computed live inside `hospital.all_wards()`.

**Workaround already in engine:** `_build_state()` calls `hospital.all_wards()` which returns Ward objects with up-to-date `occupied` counts. Since `occupancy_pct` and `is_full` are derived from `occupied` and `capacity` (both real dataclass fields), `dataclasses.asdict()` does include `occupied` and `capacity`. Agent 3 can recompute them in `state_serializer.py` or call `.occupancy_pct` before serialising.

**Recommended approach in Agent 3's serialiser:**
```python
def serialise_ward(ward: Ward) -> dict:
    d = dataclasses.asdict(ward)
    d["occupancy_pct"] = ward.occupancy_pct
    d["is_full"] = ward.is_full
    d.pop("beds")   # beds are already in the top-level beds list; omit to reduce payload size
    return d
```

### `discharged` ward capacity is 999
The `discharged` ward has `capacity=999` and is never full. `occupancy_pct` will always be near 0 regardless of how many patients have been discharged. This is by design — discharged patients are kept in `engine.patients` for the lifetime of the session so their history is available for LLM explain queries.

### Surge arrival distribution
During `trigger_surge()`, severity weights shift to 20% low / 30% medium / 50% critical (vs 60/30/10 normal). This is intentional to create the overwhelm scenario for the demo.

### Doctor LLM calls require 2+ critical patients waiting
In normal operation with few patients, the doctor LLM will almost never fire — the rule-based fallback handles it. Trigger a surge to observe real LLM doctor decisions.

---

## Files delivered by this branch

```
backend/
├── config.py                        Config dataclass + load_config()
├── requirements.txt                 Dependency manifest
└── simulation/
    ├── __init__.py                  Package exports (SimulationEngine + all types)
    ├── types.py                     All domain dataclasses from data-contracts.md §1
    ├── hospital.py                  Bed/ward resource manager + grid layout
    ├── queue_manager.py             PriorityQueue (critical > medium > low, FIFO)
    ├── patient.py                   PatientAgent: deterioration, LLM triggers
    ├── doctor.py                    DoctorAgent: assignment logic, LLM triggers
    ├── metrics.py                   MetricsCollector: rolling history + throughput
    ├── engine.py                    SimulationEngine: tick loop, surge/shortage
    └── mock_llm.py                  MockLLMInterface for testing without API key
.env.example                         Environment variable template
.gitignore
```

---

## Post-merge smoke test (full stack)

Once Agents 1 + 2 + 3 are all on `main`, run:

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload

# Terminal 2 — verify engine is being ticked
curl http://localhost:8000/state   # should return SimulationState JSON

# Terminal 3 — frontend (Agent 4)
cd frontend
npm install && npm run dev
# open http://localhost:5173
```

If the backend starts but the engine produces no patients, check that `engine.start()` is called in Agent 3's startup and that `TICK_INTERVAL_SECONDS` is set in `.env`.

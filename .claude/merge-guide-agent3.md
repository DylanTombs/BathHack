# Integration & Merge Guide — Hospital Simulation Platform

**Audience:** The merging agent (or developer) responsible for combining all four feature branches into `main`.

**Merge order (critical — do not skip or reorder):**
1. `feature/simulation-engine` → `main`
2. `feature/backend-api` → `main`
3. `feature/llm-layer` → `main`
4. `feature/frontend-ui` → `main`

---

## Overview

Each branch was developed in isolation against shared data contracts. The branches do not conflict in terms of ownership — each agent owns a distinct directory. The friction points are:
- A few shared files that two agents both created stubs of (`types.py`, `config.py`, `requirements.txt`)
- Two code-wiring steps where mock objects are replaced with real implementations (engine swap, LLM injection)
- The frontend's WebSocket URL assumption needs to match the backend's actual address

---

## Pre-Merge Checklist

Before starting, verify all branches are ready:

```bash
git fetch --all

# Confirm each branch exists and is up to date
git log origin/feature/simulation-engine --oneline -3
git log origin/feature/backend-api       --oneline -3
git log origin/feature/llm-layer         --oneline -3
git log origin/feature/frontend-ui       --oneline -3
```

Confirm the `main` branch is clean:

```bash
git checkout main
git pull origin main
git status   # must be clean
```

---

## Step 1 — Merge `feature/simulation-engine`

This branch is foundational. It has no dependencies on any other branch.

```bash
git checkout main
git merge --no-ff feature/simulation-engine -m "merge: simulation engine (Agent 1)"
```

### Expected files added by Agent 1:
```
backend/
├── simulation/
│   ├── __init__.py        ← exports SimulationEngine + types
│   ├── types.py           ← authoritative domain types
│   ├── engine.py          ← SimulationEngine class
│   ├── patient.py         ← PatientAgent
│   ├── doctor.py          ← DoctorAgent
│   ├── hospital.py        ← Hospital resource manager
│   ├── queue_manager.py   ← PriorityQueue
│   ├── metrics.py         ← MetricsCollector
│   └── mock_llm.py        ← stub LLMInterface for standalone testing
├── config.py
└── requirements.txt
```

### Conflict likelihood: **LOW** (main is empty before this merge)

### Smoke test after Step 1:
```bash
cd backend
python -m simulation.engine
# Should print: "Tick N: X patients, queue=Y, icu=Z%"
# for 20 ticks, then exit cleanly.
```

---

## Step 2 — Merge `feature/backend-api`

This branch adds the FastAPI server, WebSocket layer, REST endpoints, and mock engine.

```bash
git checkout main
git merge --no-ff feature/backend-api -m "merge: backend API + WebSocket server (Agent 3)"
```

### Expected files added by Agent 3:
```
backend/
├── api/
│   ├── __init__.py
│   ├── main.py            ← FastAPI app + tick loop
│   ├── websocket.py       ← WebSocketManager + command dispatcher
│   ├── routes.py          ← REST endpoints
│   ├── state_serializer.py← serialize SimulationState → JSON
│   ├── mock_engine.py     ← standalone mock (to be swapped out)
│   └── mock_ws_server.py  ← standalone WS server for frontend dev
├── .env.example
├── .gitignore
└── requirements.txt       ← merged with Agent 1's
```

### Conflict zones and resolutions:

---

#### Conflict 1: `backend/simulation/types.py`

**What happened:** Agent 3 created a stub of `types.py` to develop against. Agent 1 created the real implementation. Both files should be identical in structure (both copied from `data-contracts.md §1`), but Agent 1's is authoritative.

**Resolution:** Keep Agent 1's `types.py`. Delete Agent 3's stub.

```bash
# During merge, if there's a conflict on this file:
git checkout feature/simulation-engine -- backend/simulation/types.py
git add backend/simulation/types.py
```

**Critical check:** Agent 1's `Ward` dataclass may use `@property` for `occupancy_pct` and `is_full` (as specified in data-contracts.md). Agent 3's `state_serializer._to_dict()` was specifically written to handle this — it walks the class's `@property` attributes in addition to declared fields. **No code change needed in the serializer.**

Verify this works after merge:
```python
# Quick test in backend/
python -c "
import sys; sys.path.insert(0, '.')
from simulation.types import Ward
from api.state_serializer import serialize_state, _to_dict
w = Ward(name='icu', capacity=5, occupied=3, beds=[])
d = _to_dict(w)
assert 'occupancy_pct' in d, 'occupancy_pct missing from Ward serialization'
assert 'is_full' in d, 'is_full missing from Ward serialization'
print('Ward serialization OK:', d)
"
```

---

#### Conflict 2: `backend/config.py`

**What happened:** Both Agent 1 and Agent 3 wrote a `Config` dataclass with `load_config()`. The fields are the same; the differences are:
- Agent 3 added `from dotenv import load_dotenv` and `load_dotenv()` at module level
- Agent 3 added `logging.basicConfig()` call inside `load_config()`

**Resolution:** Keep Agent 3's `config.py` — it is a strict superset of Agent 1's. During conflict, accept Agent 3's version:

```bash
git checkout feature/backend-api -- backend/config.py
git add backend/config.py
```

If Agent 1 added a field that Agent 3's version is missing, add it manually before committing.

---

#### Conflict 3: `backend/requirements.txt`

**What happened:** Agent 1 specified simulation-only deps (none, all stdlib). Agent 3 added API deps.

**Resolution:** The merged `requirements.txt` should be the union:

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-dotenv>=1.0.0
websockets>=12.0
anthropic>=0.25.0
```

Agent 1's simulation module has no external deps (pure stdlib), so Agent 3's file is the complete list.

```bash
git checkout feature/backend-api -- backend/requirements.txt
git add backend/requirements.txt
```

---

#### Conflict 4: `backend/simulation/__init__.py`

**What happened:** Agent 3 left this as an empty file. Agent 1 likely exports `SimulationEngine` and types from it.

**Resolution:** Keep Agent 1's `__init__.py`:

```bash
git checkout feature/simulation-engine -- backend/simulation/__init__.py
git add backend/simulation/__init__.py
```

---

### Wire in the real simulation engine (REQUIRED code change)

After the merge resolves, open `backend/api/main.py` and **replace the mock engine** with the real one.

Find and replace these lines:

```python
# REMOVE THIS:
from api.mock_engine import MockSimulationEngine  # swapped post-merge
engine = MockSimulationEngine()
```

```python
# REPLACE WITH:
from simulation.engine import SimulationEngine
engine = SimulationEngine(config)
```

The `SimulationEngine` constructor signature (from Agent 1's spec) is:
```python
SimulationEngine(config: Config, llm_callback=None)
```

Pass `llm_callback=None` for now — it will be injected in Step 3.

Save `main.py` and stage the change:
```bash
git add backend/api/main.py
```

---

### Smoke test after Step 2:

```bash
cd backend
pip install -r requirements.txt

# Start the server (no API key needed yet — LLM not wired)
uvicorn api.main:app --reload --port 8000
```

In a second terminal:
```bash
# Health check
curl http://localhost:8000/api/health
# Expected: {"status":"ok","engine":"paused","tick":0,...}

# Start the simulation
# (use wscat, websocat, or browser devtools)
# Send: {"command":"start"}
# Expect: sim_state messages arriving every ~1 second with real patient/doctor data

# After ~10 ticks:
curl http://localhost:8000/api/metrics/history
# Expected: JSON array of MetricsSnapshot objects
```

**Accept criteria:**
- `sim_state` messages arrive at ~1 Hz
- `patients` array contains real patient objects with valid `grid_x`/`grid_y` in zone bounds
- `wards.icu.occupancy_pct` increases when critical patients are assigned
- `POST /api/scenario/surge` causes visible ICU fill in subsequent ticks

---

## Step 3 — Merge `feature/llm-layer`

This branch adds the LLM decision brain. It has no file conflicts with the existing main.

```bash
git checkout main
git merge --no-ff feature/llm-layer -m "merge: LLM integration layer (Agent 2)"
```

### Expected files added by Agent 2:
```
backend/
└── llm/
    ├── __init__.py        ← exports AnthropicLLMClient, LLMTriggerGuard, ExplainerService
    ├── client.py          ← AnthropicLLMClient (implements LLMInterface)
    ├── triggers.py        ← LLMTriggerGuard (rate limiting / trigger logic)
    ├── prompts.py         ← prompt templates
    └── explainer.py       ← ExplainerService (on-demand explain endpoint)
```

### Conflict likelihood: **NONE** (Agent 2 only adds a new directory)

---

### Wire in the LLM client (REQUIRED code change)

Open `backend/api/main.py` and wire the LLM client into the engine.

Find the engine instantiation you set in Step 2:

```python
# CURRENT (from Step 2):
engine = SimulationEngine(config)
```

Replace it with the full LLM-wired setup:

```python
# REPLACE WITH:
from llm import AnthropicLLMClient, ExplainerService

llm_client = AnthropicLLMClient(
    api_key=config.anthropic_api_key,
    model=config.llm_model,
)
explainer = ExplainerService(llm_client)

engine = SimulationEngine(config, llm_callback=llm_client)
engine.explainer = explainer   # used by websocket._get_explanation()
```

**Note on `engine.explainer`:** Agent 3's `websocket.py` checks `hasattr(engine, 'explainer') and engine.explainer is not None` before using it. Setting `engine.explainer = explainer` after construction is intentional and the code is ready for it.

Save and stage:
```bash
git add backend/api/main.py
git commit -m "wire: connect LLM client and explainer to simulation engine"
```

---

### Smoke test after Step 3:

```bash
# Make sure ANTHROPIC_API_KEY is in your .env
cp backend/.env.example backend/.env
# Edit backend/.env and set ANTHROPIC_API_KEY=sk-ant-...

cd backend
uvicorn api.main:app --reload --port 8000
```

Verification steps:

1. Start simulation, trigger surge: `{"command":"start"}` then `{"command":"trigger_surge"}`
2. Watch server logs — after a few ticks you should see `LLM` log lines
3. After ~5 ticks in surge, some `sim_state` events should have `llm_explanation` populated (non-null)
4. Send `{"command":"explain_patient","target_id":1}` — response should be an LLM-generated paragraph, not the fallback rule-based string
5. Check `llm_client.stats` doesn't show 100% fallback rate

**If ANTHROPIC_API_KEY is not set:** The server still runs. `AnthropicLLMClient` falls back to rule-based decisions on every call (the fallback path is tested and working). The simulation will function; LLM explanations will be absent from event logs.

---

## Step 4 — Merge `feature/frontend-ui`

This branch adds the React frontend.

```bash
git checkout main
git merge --no-ff feature/frontend-ui -m "merge: frontend UI (Agent 4)"
```

### Expected files added by Agent 4:
```
frontend/
├── src/
│   ├── components/        ← Hospital map, charts, event log, control panel
│   ├── hooks/             ← useWebSocket, useSimulationState
│   ├── store/             ← state management
│   └── types/             ← TypeScript types (mirrors data-contracts.md §5)
├── package.json
└── vite.config.ts
```

### Conflict likelihood: **NONE** (frontend/ is an entirely new directory)

---

### Verify WebSocket URL

Agent 4 developed against `ws://localhost:8000/ws` (from `mock_ws_server.py`). Confirm the frontend's WebSocket hook points to the same address as the production backend:

```bash
grep -r "localhost:8000" frontend/src/
# Should find a WebSocket URL config pointing to ws://localhost:8000/ws
```

If the frontend hardcodes a different port, update it to `ws://localhost:8000/ws`.

---

### Install and run frontend:

```bash
cd frontend
npm install
npm run dev
# Vite dev server starts at http://localhost:5173
```

Ensure the backend is also running:
```bash
cd backend
uvicorn api.main:app --reload --port 8000
```

CORS is pre-configured in `backend/api/main.py` to allow `http://localhost:5173`.

---

### Full system smoke test after Step 4:

1. Open `http://localhost:5173` in browser
2. Hospital map renders with patient and doctor icons
3. Icons are in the correct zones:
   - Waiting patients: top-left area (grid cols 0-7, rows 0-5)
   - General ward patients/doctors: middle-left (cols 0-11, rows 6-12)
   - ICU patients/doctors: middle-right (cols 12-19, rows 6-12)
4. Send `start` command from control panel — tick counter increments in UI
5. Send `trigger_surge` — patient count visibly rises, ICU % climbs in charts
6. Click a patient icon → `explain_patient` command fires → explanation panel shows
7. Click a doctor icon → `explain_doctor` command fires → reasoning shown
8. Send `trigger_shortage` → 2 doctors become unavailable → queue backs up
9. Send `trigger_recovery` → system stabilises

---

## Shared File Conflict Resolution Reference

| File | Agent 1 | Agent 3 | Resolution |
|------|---------|---------|------------|
| `backend/simulation/types.py` | Real impl | Stub | Keep Agent 1's |
| `backend/simulation/__init__.py` | Exports engine+types | Empty | Keep Agent 1's |
| `backend/config.py` | Basic Config | Config + dotenv + logging | Keep Agent 3's (superset) |
| `backend/requirements.txt` | (empty / stdlib only) | API deps | Keep Agent 3's (full list) |

---

## Code Wiring Summary

Two explicit code changes are required in `backend/api/main.py`. Here is the final state after both steps:

```python
# backend/api/main.py — final wired imports (replace mock_engine section)

from config import load_config
from simulation.engine import SimulationEngine          # ← Agent 1
from llm import AnthropicLLMClient, ExplainerService   # ← Agent 2
from api.websocket import WebSocketManager, websocket_endpoint
from api.routes import router

config = load_config()
ws_manager = WebSocketManager()

llm_client = AnthropicLLMClient(
    api_key=config.anthropic_api_key,
    model=config.llm_model,
)
explainer = ExplainerService(llm_client)

engine = SimulationEngine(config, llm_callback=llm_client)
engine.explainer = explainer
```

Everything else in `main.py` stays the same — the tick loop, lifespan, CORS, routes, and WebSocket endpoint are all already correct.

---

## Environment Setup

After all merges, create `backend/.env` from the example:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:
```env
ANTHROPIC_API_KEY=sk-ant-...       # required for LLM features
LLM_MODEL=claude-haiku-4-5-20251001
TICK_INTERVAL_SECONDS=1.0
MAX_BEDS_GENERAL=20
MAX_BEDS_ICU=5
INITIAL_DOCTORS=4
ARRIVAL_RATE_PER_TICK=1.5
LOG_LEVEL=INFO
```

---

## Final Integration Test

Run all components:

```bash
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Walk through the demo script from `CLAUDE.md`:

1. Idle hospital — a few patients in waiting area ✓
2. `trigger_surge` → mass patient flood ✓
3. ICU fills → queue backs up → doctor LLM decisions fire ✓
4. Click Explain on a doctor → LLM reasoning appears ✓
5. `trigger_shortage` → cascade visible ✓
6. Charts show occupancy spike, queue growth, throughput drop ✓
7. `trigger_recovery` → system recovers ✓

---

## Troubleshooting

### WebSocket messages not arriving
- Check `engine.is_running` — simulation starts **paused**. Send `{"command":"start"}`.
- Check CORS: browser console should not show CORS errors for `ws://localhost:8000/ws`.
- Check `backend/api/main.py` has the real `SimulationEngine`, not `MockSimulationEngine`.

### `ImportError: cannot import name 'SimulationEngine' from 'simulation'`
- Agent 1's `simulation/__init__.py` must export `SimulationEngine`.
- Fix: `git checkout feature/simulation-engine -- backend/simulation/__init__.py`

### Ward `occupancy_pct` / `is_full` missing from JSON
- Agent 1's `Ward` uses `@property` for these. Agent 3's serializer handles this.
- If missing, check that `_to_dict` in `state_serializer.py` has the `@property` walk loop.
- The relevant block is:
  ```python
  for name, attr in vars(type(obj)).items():
      if isinstance(attr, property) and name not in result:
          result[name] = _to_dict(getattr(obj, name))
  ```

### LLM calls all falling back (`fallback_rate` = 1.0)
- Check `ANTHROPIC_API_KEY` is set in `backend/.env` and `load_dotenv()` is being called.
- Test key directly: `python -c "import anthropic; print(anthropic.Anthropic().models.list())"`
- If key is correct but rate limiting, `LOG_LEVEL=DEBUG` will show the error.

### `serialize_state` raises `TypeError`
- A real dataclass field contains a non-serialisable type.
- Add a case to `_to_dict` in `state_serializer.py` for the offending type.
- Run `json.dumps(serialize_state(engine.get_state()))` in isolation to reproduce.

### Frontend shows stale/disconnected state
- Agent 4's WebSocket hook should reconnect automatically on disconnect.
- Confirm the hook retries with exponential backoff; if not, check `frontend/src/hooks/`.
- If the backend restarts, the frontend must send `{"command":"start"}` again since the engine resets to paused state.

---

## Post-Integration Cleanup

Once integration is confirmed working, the following files are no longer needed but are harmless to leave:

- `backend/api/mock_engine.py` — superseded by real engine (keep for fallback / offline testing)
- `backend/api/mock_ws_server.py` — superseded by full stack (keep for frontend-only development)

Do **not** delete `backend/simulation/types.py` stub — that is now the real Agent 1 file.

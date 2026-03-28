# Integration & Merge Guide

**For:** Merging agent / lead developer
**Purpose:** Step-by-step instructions to integrate all four feature branches into `main` and wire the complete system together.

---

## Overview

Four branches, four owners, one integration point (Agent 3's `main.py`):

| Branch | Owner | Status | Key deliverable |
|--------|-------|--------|-----------------|
| `feature/simulation-engine` | Agent 1 | See progress-agent1.md | `SimulationEngine`, all domain types |
| `feature/llm-layer` | Agent 2 | ✅ Complete | `AnthropicLLMClient`, `LLMTriggerGuard`, `ExplainerService` |
| `feature/backend-api` | Agent 3 | ✅ Complete | FastAPI server, WebSocket, REST routes |
| `feature/frontend-ui` | Agent 4 | See progress-agent4.md | React canvas UI |

**Merge order is mandatory** — each step builds on the previous.

```
feature/simulation-engine  ─┐
feature/llm-layer          ─┼─→  main  ←─  feature/backend-api  ←─  feature/frontend-ui
                             │          (wire together in main.py)
```

---

## Pre-Merge Checklist

Before touching git, verify each branch passes its own tests:

```bash
# Agent 1 — simulation engine standalone test
git checkout feature/simulation-engine
cd backend
python -m simulation.engine          # should run 20 ticks, print output, exit clean

# Agent 2 — LLM layer unit tests (no API key needed)
git checkout feature/llm-layer
cd backend
python3 -m pytest tests/test_llm_standalone.py -v    # must be 62 passed, 0 failed

# Agent 3 — backend API health check
git checkout feature/backend-api
cd backend
uvicorn api.main:app --port 8000 &
curl http://localhost:8000/api/health    # expect {"status": "ok", ...}
kill %1
```

Do not merge a branch that fails its own tests.

---

## Step 1 — Merge `feature/simulation-engine` → `main`

Agent 1 is foundational. Everything else depends on its types.

```bash
git checkout main
git merge --no-ff feature/simulation-engine -m "feat: merge simulation engine (Agent 1)"
```

### Expected conflicts
These files exist on both `main` and `feature/simulation-engine`. In each case, **Agent 1's version wins**:

| File | Resolution |
|------|-----------|
| `backend/simulation/types.py` | Use Agent 1's version — it is the authoritative source copied from `data-contracts.md §1` |
| `backend/config.py` | Use Agent 1's version |
| `backend/requirements.txt` | **Merge both** — combine all dependency lines, remove duplicates |
| `backend/.env.example` | Use Agent 1's version (same content, just in case) |

### Post-merge verification
```bash
cd backend
python -m simulation.engine     # 20-tick run, no errors
python -c "from simulation.engine import SimulationEngine; print('OK')"
python -c "from simulation.types import SimulationState, ScenarioConfig; print('OK')"
```

---

## Step 2 — Merge `feature/backend-api` → `main`

Agent 3 builds on the simulation types. Merge it after Agent 1.

```bash
git checkout main
git merge --no-ff feature/backend-api -m "feat: merge backend API layer (Agent 3)"
```

### Expected conflicts

| File | Resolution |
|------|-----------|
| `backend/simulation/types.py` | **Discard Agent 3's stub** — Agent 1's real implementation already on `main` |
| `backend/config.py` | **Discard Agent 3's stub** — Agent 1's real implementation already on `main` |
| `backend/requirements.txt` | **Merge both** — combine all dependency lines |
| `backend/.env.example` | Keep whichever is more complete, or merge both |

### Critical check: replace MockSimulationEngine with real engine
After the merge, `backend/api/main.py` still uses `MockSimulationEngine`.
**Do not ship this.** See Step 4 for the wiring.

### Post-merge verification
```bash
cd backend
uvicorn api.main:app --reload --port 8000 &
sleep 2
curl http://localhost:8000/api/health
# Expect: {"status": "ok", "engine": "paused"} (mock engine)
kill %1
```

---

## Step 3 — Merge `feature/llm-layer` → `main`

Agent 2 is self-contained. It can merge at any point after Step 1 since it only
depends on `simulation/types.py` (now on `main` from Step 1).

```bash
git checkout main
git merge --no-ff feature/llm-layer -m "feat: merge LLM integration layer (Agent 2)"
```

### Expected conflicts

| File | Resolution |
|------|-----------|
| `backend/simulation/types.py` | **Discard Agent 2's stub** — use Agent 1's real version already on `main` |
| `backend/simulation/__init__.py` | **Discard Agent 2's stub** — use Agent 1's real version |
| `backend/config.py` | **Discard Agent 2's stub** — use Agent 1's real version |
| `backend/requirements.txt` | **Merge both** — combine `anthropic>=0.40.0` with Agent 1 deps |
| `backend/.env.example` | Merge — Agent 2 adds `ANTHROPIC_API_KEY` and `LLM_MODEL` |

### Post-merge verification
```bash
cd backend
python -c "from llm import AnthropicLLMClient, LLMTriggerGuard, ExplainerService; print('OK')"
python3 -m pytest tests/test_llm_standalone.py -v     # all 62 should still pass
```

---

## Step 4 — Wire the System in `main.py` (CRITICAL)

This is the key integration step. After Steps 1–3 are merged, edit
`backend/api/main.py` to replace the mock engine with the real engine + LLM.

### Current state of `main.py` after merge (uses mocks):
```python
from api.mock_engine import MockSimulationEngine
engine = MockSimulationEngine()
```

### Replace with this wiring block:
```python
import os
from config import load_config
from simulation.engine import SimulationEngine
from llm import AnthropicLLMClient, ExplainerService

config = load_config()
llm_client = AnthropicLLMClient(
    api_key=config.anthropic_api_key,
    model=config.llm_model,
)
explainer = ExplainerService(llm_client)
engine = SimulationEngine(config, llm_callback=llm_client)
engine.explainer = explainer     # consumed by websocket.py _get_explanation()
```

Remove or comment out:
```python
# from api.mock_engine import MockSimulationEngine   # no longer needed
```

### Verify the wire format
Agent 3's `state_serializer.py` calls `dataclasses.asdict()` on the real
`SimulationState`. Confirm it produces the expected shape:

```python
from simulation.engine import SimulationEngine
from api.state_serializer import serialize_state
from config import load_config

config = load_config()
engine = SimulationEngine(config)
engine.start()
import asyncio
state = asyncio.run(engine.tick())
serialised = serialize_state(state)
import json
print(json.dumps(serialised, indent=2))
# Verify all keys from data-contracts.md §2 are present:
assert "type" in serialised
assert "tick" in serialised
assert "patients" in serialised
assert "doctors" in serialised
assert "wards" in serialised
assert "metrics" in serialised
assert "events" in serialised
```

---

## Step 5 — Merge `feature/frontend-ui` → `main`

Frontend is independent of all backend branches. Merge last to avoid noise.

```bash
git checkout main
git merge --no-ff feature/frontend-ui -m "feat: merge frontend UI (Agent 4)"
```

### Expected conflicts
Minimal — frontend lives entirely in `frontend/` which no other branch touches.
The only possible conflict is root-level files (`.gitignore`, `README.md`).
Merge manually; keep both sets of entries.

### Post-merge verification
```bash
cd frontend
npm install
npm run build     # must complete without errors
```

---

## Step 6 — Full System Smoke Test

With all branches merged and `main.py` wired, run the full system:

```bash
# Terminal 1 — backend
cd backend
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev     # starts on http://localhost:5173
```

Then open `http://localhost:5173` and run through the demo script from `CLAUDE.md`:

1. Hospital loads with idle state — patients visible in waiting area
2. Send `trigger_surge` command → patients flood in
3. ICU fills → queue backs up → doctor LLM decisions start firing
4. Click **Explain** on a doctor → LLM explanation panel appears
5. Send `trigger_shortage` → cascade effect visible
6. Check browser console — no WebSocket errors, state arriving ~1/second

---

## File Conflict Resolution Reference

This table summarises every file that exists on multiple branches.
The **Winner** column says which version to keep; the **Action** column says what to do.

| File | Branches | Winner | Action |
|------|----------|--------|--------|
| `backend/simulation/types.py` | Agent 1, 2, 3 | **Agent 1** | Agent 1 owns this per the spec. Agents 2 and 3 created stubs. Discard stubs, keep Agent 1's full implementation. |
| `backend/simulation/__init__.py` | Agent 1, 2 | **Agent 1** | Agent 2's stub is minimal; Agent 1 exports the real classes. |
| `backend/config.py` | Agent 1, 2, 3 | **Agent 1** | Agent 1 owns `config.py`. Agent 2 and 3 created stubs. Keep Agent 1's. Verify it has `arrival_rate_per_tick` field (Agent 1 spec adds this; Agents 2/3 stubs may not). |
| `backend/requirements.txt` | Agent 1, 2, 3 | **Merge all** | Combine all lines from every branch. Deduplicate. Final file must include `anthropic>=0.40.0`, `fastapi>=0.111.0`, `uvicorn[standard]>=0.29.0`, `websockets>=12.0`, `python-dotenv>=1.0.0`, `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`. |
| `backend/.env.example` | Agent 1, 2, 3 | **Merge all** | Final file needs all variables from all agents: `ANTHROPIC_API_KEY`, `LLM_MODEL`, `TICK_INTERVAL_SECONDS`, `MAX_BEDS_GENERAL`, `MAX_BEDS_ICU`, `INITIAL_DOCTORS`, `LOG_LEVEL`, `ARRIVAL_RATE_PER_TICK`. |
| `backend/.gitignore` | Agent 2 | Keep | No conflict expected. |

---

## Post-Merge Config Reconciliation

After merging all three backend branches, `backend/config.py` must expose
**all** fields used by the full system. Check it includes:

```python
@dataclass(frozen=True)
class Config:
    anthropic_api_key: str          # used by: llm/client.py
    llm_model: str                  # used by: llm/client.py
    tick_interval_seconds: float    # used by: api/main.py simulation_loop
    max_beds_general: int           # used by: simulation/engine.py
    max_beds_icu: int               # used by: simulation/engine.py
    initial_doctors: int            # used by: simulation/engine.py
    log_level: str                  # used by: all
    arrival_rate_per_tick: float    # used by: simulation/engine.py (Agent 1 adds this)
```

If Agent 1's `config.py` does not raise on a missing `ANTHROPIC_API_KEY`,
patch `load_config()` to only raise if the key is empty AND an LLM call is
actually attempted (Agent 2's client handles this). A simpler fix: make
`anthropic_api_key` default to `""` in the dataclass so the server starts
without a key, but LLM calls fall back gracefully.

---

## LLM Trigger Guard — Ownership After Merge

The `LLMTriggerGuard` in `backend/llm/triggers.py` was written by Agent 2
for use by the simulation engine agents (patient.py, doctor.py).

**Post-merge decision required:**
Agent 1's `patient.py` and `doctor.py` each contain their own
`_should_call_llm_for_*` methods per the spec. These may duplicate
`LLMTriggerGuard` logic.

**Recommended resolution:**
1. Import `LLMTriggerGuard` in `backend/simulation/engine.py` (or `doctor.py`)
2. Pass a single shared guard instance to all `DoctorAgent` and `PatientAgent` instances
3. Remove Agent 1's standalone `_should_call_llm_for_*` methods — they are superseded

This ensures the global per-tick limit (`GLOBAL_CALLS_PER_TICK_LIMIT = 3`) is
enforced across all agents, not per-agent.

Shared guard init in `engine.py`:
```python
from llm.triggers import LLMTriggerGuard

class SimulationEngine:
    def __init__(self, config, llm_callback=None):
        ...
        self._llm_guard = LLMTriggerGuard() if llm_callback else None
        # Pass to agents:
        # DoctorAgent(doctor, llm_callback=llm_callback, llm_guard=self._llm_guard)
        # PatientAgent(patient, llm_callback=llm_callback, llm_guard=self._llm_guard)

    async def tick(self) -> SimulationState:
        if self._llm_guard:
            self._llm_guard.new_tick(self._tick)
        ...
```

---

## ExplainerService — Attachment Point

Agent 3's `websocket.py` calls `engine.explainer.explain_patient(...)` via:
```python
if hasattr(engine, 'explainer') and engine.explainer:
    return await engine.explainer.explain_patient(entity_id, state)
```

After wiring (Step 4), `engine.explainer` must be set on the `SimulationEngine`
instance. The `ExplainerService` is not part of the engine — it's set as an
attribute by the API layer:

```python
engine.explainer = ExplainerService(llm_client)
```

`SimulationEngine` does not need to know `ExplainerService` exists. The
attribute is duck-typed and only accessed from `websocket.py`.

---

## Common Failure Modes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ImportError: cannot import 'SimulationEngine'` | Merge order wrong; Agent 1 not merged first | Merge Agent 1 before Agent 3 |
| `ImportError: cannot import 'AnthropicLLMClient'` | Agent 2 not merged or `backend/` not in `PYTHONPATH` | Run from `backend/` directory |
| WebSocket connects but no state messages | `engine.is_running` is False — forgot to call `engine.start()` | Send `{"command": "start"}` via WS, or call `engine.start()` at init |
| LLM calls never fire during surge | `LLMTriggerGuard` not being called with `new_tick()` | Ensure `guard.new_tick(tick)` is called at the top of `engine.tick()` |
| `explain_patient` returns fallback text even with API key | `engine.explainer` not set | Add `engine.explainer = ExplainerService(llm_client)` to main.py |
| `ValueError: ANTHROPIC_API_KEY is not set` on startup | Agent 2's strict `load_config()` is active | Either set the key or patch config to allow empty key with warning |
| `serialize_state` raises `TypeError` | Agent 1's `SimulationState` has a field that isn't a standard type | Check for `Enum` subclasses or custom types in Agent 1's dataclasses; add handling to `_to_dict()` |
| `Ward` not serialising `beds` list | `dataclasses.asdict()` drops computed properties (`is_full`, `occupancy_pct`) | Agent 3's serialiser must explicitly compute and add these to the ward dict |

---

## Final Integration Commit

Once all four branches are merged and the system runs end-to-end:

```bash
git checkout main
# Make the main.py wiring changes described in Step 4
git add backend/api/main.py backend/requirements.txt backend/.env.example
git commit -m "feat: wire simulation engine + LLM layer into backend API

Replaces MockSimulationEngine with real SimulationEngine.
Injects AnthropicLLMClient as llm_callback.
Attaches ExplainerService to engine for on-demand explain commands.
All four feature branches now integrated on main."
```

---

## Integration Verification Checklist

Run through this before demo:

- [ ] `python -m simulation.engine` runs 20 ticks clean (Agent 1 standalone)
- [ ] `pytest tests/test_llm_standalone.py` → 62 passed (Agent 2 standalone)
- [ ] `uvicorn api.main:app --port 8000` starts without errors
- [ ] `curl localhost:8000/api/health` → `{"status": "ok", "engine": "running"}`
- [ ] WebSocket connects and receives `sim_state` messages at ~1Hz
- [ ] `trigger_surge` command triggers surge scenario
- [ ] LLM explanations appear in `events[].llm_explanation` after surge (check Network tab)
- [ ] `explain_patient` command returns multi-sentence LLM text
- [ ] Frontend loads at `http://localhost:5173`, hospital map renders
- [ ] Patient icons move/update as state changes
- [ ] No errors in backend logs or browser console during 5-minute run

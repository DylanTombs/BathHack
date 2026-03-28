# Merge Integration Guide — All Branches → `main`

**For:** Merging agent / integration lead
**Branch this doc describes:** `feature/frontend-ui` (Agent 4) + all others
**Goal:** Bring all four feature branches together into a working full-stack demo on `main`

---

## Branch Overview

| Branch | Agent | Owns | Status |
|--------|-------|------|--------|
| `feature/simulation-engine` | Agent 1 | `backend/simulation/` | Merge first |
| `feature/backend-api`       | Agent 3 | `backend/api/`        | Merge second |
| `feature/llm-layer`         | Agent 2 | `backend/llm/`        | Merge third |
| `feature/frontend-ui`       | Agent 4 | `frontend/`           | Merge last |

Each branch was developed in isolation against the shared data contracts in `.claude/data-contracts.md`. There should be **no file-level conflicts** between branches — each owns a non-overlapping directory — but integration wiring must be done after merging.

---

## Merge Order (must follow exactly)

```bash
# 1. Start from main
git checkout main

# 2. Merge simulation engine first (no dependencies)
git merge feature/simulation-engine --no-ff -m "merge: simulation engine"

# 3. Merge backend API (wires into engine)
git merge feature/backend-api --no-ff -m "merge: backend API"

# 4. Merge LLM layer (injects into engine callback)
git merge feature/llm-layer --no-ff -m "merge: LLM layer"

# 5. Merge frontend UI last
git merge feature/frontend-ui --no-ff -m "merge: frontend UI"
```

---

## Expected File Tree After All Merges

```
BathHack/
├── .claude/
├── backend/
│   ├── simulation/          ← Agent 1
│   │   ├── engine.py
│   │   ├── patient.py
│   │   ├── doctor.py
│   │   ├── hospital.py
│   │   ├── queue_manager.py
│   │   └── metrics.py
│   ├── llm/                 ← Agent 2
│   │   ├── client.py
│   │   ├── triggers.py
│   │   ├── prompts.py
│   │   └── explainer.py
│   ├── api/                 ← Agent 3
│   │   ├── main.py
│   │   ├── websocket.py
│   │   ├── routes.py
│   │   └── state_serializer.py
│   ├── requirements.txt
│   └── config.py
└── frontend/                ← Agent 4
    ├── src/
    │   ├── types/simulation.ts
    │   ├── store/
    │   ├── hooks/
    │   └── components/
    ├── mock_ws_server.py
    ├── package.json
    └── vite.config.ts
```

If any of these directories are missing after a merge, the corresponding branch has not been merged or did not produce files.

---

## Post-Merge Integration Wiring

The four branches were built to spec but the glue code between them needs to be verified / wired up. Work through each integration point below.

---

### 1. Engine ↔ API (Agent 1 ↔ Agent 3)

**What to verify:** `backend/api/main.py` (or `websocket.py`) must import and call `SimulationEngine` from `backend/simulation/engine.py`.

**Expected pattern in `backend/api/main.py`:**
```python
from simulation.engine import SimulationEngine

engine = SimulationEngine()

# Called on a timer (asyncio) — every TICK_INTERVAL_SECONDS
async def tick_loop():
    while True:
        state = await engine.tick()
        await broadcast(state)
        await asyncio.sleep(config.TICK_INTERVAL_SECONDS)
```

**Check:** If Agent 3 used a mock engine stub during development, replace it with the real `SimulationEngine` import now.

---

### 2. LLM Layer ↔ Engine (Agent 2 → Agent 1 callback)

**What to verify:** `SimulationEngine.__init__` accepts an optional `llm_callback: LLMInterface` parameter. Agent 2's `LLMClient` (or equivalent) must implement the `LLMInterface` protocol.

**Expected wiring in `backend/api/main.py`:**
```python
from simulation.engine import SimulationEngine
from llm.client import LLMClient          # Agent 2
from simulation.types import LLMInterface  # protocol definition

llm = LLMClient()                          # uses ANTHROPIC_API_KEY from env
engine = SimulationEngine(llm_callback=llm)
```

**Check the protocol is satisfied:**
```python
# Agent 2's LLMClient must have these methods:
class LLMClient:
    async def doctor_decide(self, context: DoctorContext) -> DoctorDecision: ...
    async def patient_reevaluate(self, context: PatientContext) -> PatientUpdate: ...
    async def explain_event(self, event: SimEvent) -> str: ...
```

If `LLMClient` doesn't implement all three, the engine will fail at runtime when the callback is invoked. Either add the missing methods or pass `llm_callback=None` to fall back to rule-based logic.

---

### 3. API ↔ Frontend WebSocket (Agent 3 ↔ Agent 4)

**What to verify:** The backend WebSocket endpoint is at `ws://localhost:8000/ws` and emits JSON that matches the wire format in `data-contracts.md §2`.

**Frontend expects these message types:**
| `msg.type` | Handler |
|------------|---------|
| `sim_state` | `useSimulationStore.applyState()` |
| `explanation` | `useUIStore.setExplanation()` |
| `metrics_history` | `useSimulationStore.seedHistory()` |
| `error` | (currently logged to console only) |

**Frontend sends these commands:**
```json
{ "command": "start" }
{ "command": "pause" }
{ "command": "reset" }
{ "command": "trigger_surge" }
{ "command": "trigger_shortage" }
{ "command": "trigger_recovery" }
{ "command": "explain_patient", "target_id": 12 }
{ "command": "explain_doctor",  "target_id": 2 }
{ "command": "update_config", "config": { ... } }
```

**Check:** Verify Agent 3's WebSocket handler reads `msg["command"]` (not `msg["type"]`) for inbound messages. The frontend sends a bare `command` field without a `type` wrapper for outbound commands.

**Check:** Verify the `sim_state` payload includes `type: "sim_state"` as the top-level discriminator field. The frontend uses this to route messages.

---

### 4. Explanation Response Flow

**What to verify:** When the frontend sends `explain_patient` or `explain_doctor`, Agent 3 calls Agent 2's LLM explainer and sends back:
```json
{
  "type": "explanation",
  "target_id": 12,
  "target_type": "patient",
  "explanation": "...",
  "tick": 42
}
```

The frontend's `useWebSocket.ts` will route `msg.type === 'explanation'` to `setExplanation(msg.explanation)`, which populates the EntityDetailPanel.

**Check:** The `explanation` field — not `llm_explanation` — is the key the frontend reads from this response object. Confirm Agent 3's response serialisation uses `explanation`.

---

## Environment Setup

Create `backend/.env` (or copy from the template in `CLAUDE.md`):

```env
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5-20251001
TICK_INTERVAL_SECONDS=1.0
MAX_BEDS_GENERAL=20
MAX_BEDS_ICU=5
INITIAL_DOCTORS=4
LOG_LEVEL=INFO
```

Create `frontend/.env`:
```env
VITE_WS_URL=ws://localhost:8000/ws
```

---

## Running the Full Stack

### Terminal 1 — Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — Frontend
```bash
cd frontend
npm install
npm run dev
# Opens http://localhost:5173
```

### Verify connection
- Open `http://localhost:5173`
- Top-right connection dot should turn **green** within 2 seconds
- Tick counter in header should increment every second
- Patients and doctors should appear on the map

---

## Smoke Tests After Integration

Run through these manually in the browser:

| # | Action | Expected |
|---|--------|----------|
| 1 | Page load | Green "Live" dot, tick increments |
| 2 | Patient icons visible | Coloured circles in correct ward zones |
| 3 | Doctor icons visible | Diamond icons with correct workload colour |
| 4 | Click a patient | Detail panel opens on right with name/severity/diagnosis |
| 5 | Click "Explain (AI)" | Loading spinner → explanation text appears (may take 1-3s for LLM) |
| 6 | Click 🚨 Surge | Scenario banner shows "Mass Casualty Event Active", patients flood in |
| 7 | ICU chart spikes | Occupancy chart shows ICU line rising |
| 8 | Click 👨‍⚕️ Shortage | Staff Shortage banner appears |
| 9 | Click ✅ Normal | Banner clears, system stabilises |
| 10 | Kill backend process | "Disconnected" dot goes red |
| 11 | Restart backend | Dot returns to green within 3s (auto-reconnect) |
| 12 | Drag Arrival Rate slider | Config command sent; arrival rate visible in queue chart |

---

## Known Integration Risks

### Grid coordinate range
Agent 1's engine emits `grid_x` / `grid_y` values. If these are out of range for their ward zone, icons will render in the wrong area or off-screen.

**Fix:** Check that Agent 1 places:
- Waiting patients at `grid_x ∈ [0, 7.5]`, `grid_y ∈ [0, 5.5]`
- General ward patients at `grid_x ∈ [0, 11.5]`, `grid_y ∈ [6, 12.5]`
- ICU patients at `grid_x ∈ [12, 19.5]`, `grid_y ∈ [6, 12.5]`

If the values are out of range, adjust `CELL_SIZE` in [frontend/src/components/map/HospitalMap.tsx](../frontend/src/components/map/HospitalMap.tsx) or add clamping.

### LLM latency
The `explain_patient` / `explain_doctor` commands trigger a real LLM call. The UI shows a loading spinner indefinitely until a response arrives. If the LLM call takes > 10s or fails silently, the spinner never clears.

**Fix:** Agent 3 should always send an `explanation` response, even on error. Add a timeout fallback:
```python
# In Agent 3's explanation handler:
try:
    text = await asyncio.wait_for(llm.explain_event(event), timeout=8.0)
except asyncio.TimeoutError:
    text = "LLM timed out — falling back to rule-based summary."
await ws.send_json({"type": "explanation", "target_id": target_id, "target_type": entity_type, "explanation": text, "tick": engine.tick})
```

### `sim_state` fields
If Agent 3's serialiser omits any field the frontend expects (e.g. `beds`, `wards`, or `metrics`), the store will receive `undefined` and charts/badges will show 0/NaN.

**Fix:** Use `data-contracts.md §2` as the canonical wire format. All fields must be present on every tick; use empty arrays/dicts as defaults, never `null` for collection fields.

### CORS / proxy
The Vite dev server proxies `/api` → `http://localhost:8000` but WebSocket (`/ws`) connects directly. If the backend binds only to `127.0.0.1` but the frontend tries `localhost`, this should be fine on most systems. If connections fail, check the backend binding address.

---

## What Agent 4's Branch Does NOT Include

The frontend intentionally has no backend code. These must come from other branches:

- `backend/` directory entirely
- `backend/requirements.txt`
- Any Python startup script
- The real `SimulationEngine` with `grid_x`/`grid_y` assignment logic

The `frontend/mock_ws_server.py` is a **development-only** mock. It should not be used in the integrated system — use Agent 3's real FastAPI server instead.

---

## Final Checklist Before Demo

- [ ] All four branches merged into `main` in order
- [ ] `backend/.env` has valid `ANTHROPIC_API_KEY`
- [ ] Backend starts with `uvicorn api.main:app --port 8000`
- [ ] Frontend starts with `npm run dev` (port 5173)
- [ ] WebSocket connects (green dot)
- [ ] Patients appear on map within 5 ticks
- [ ] LLM explanation returns for at least one entity click
- [ ] Surge scenario visually noticeable
- [ ] `npm run build` still passes (no regressions from merge)

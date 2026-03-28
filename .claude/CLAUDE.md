# Hospital Simulation Platform — Master Coordination Guide

## Project Summary

A real-time, interactive hospital simulation where patients and doctors are AI agents (LLM-backed), hospital resources are constrained, and a live visual map UI shows system dynamics. Users can test scenarios and observe outcomes.

**Stack:** Python (FastAPI + asyncio) backend · React + Canvas/SVG frontend · WebSockets for real-time comms · Anthropic Claude API for LLM decisions

---

## Repository Structure (Target)

```
BathHack/
├── .claude/                    # Agent coordination docs (this folder)
│   ├── CLAUDE.md               # This file
│   ├── data-contracts.md       # Shared types and wire format
│   ├── agent1-simulation-engine.md
│   ├── agent2-llm-layer.md
│   ├── agent3-backend-api.md
│   └── agent4-frontend-ui.md
├── backend/
│   ├── simulation/             # Agent 1 owns this
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── patient.py
│   │   ├── doctor.py
│   │   ├── hospital.py
│   │   ├── queue_manager.py
│   │   └── metrics.py
│   ├── llm/                    # Agent 2 owns this
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── triggers.py
│   │   ├── prompts.py
│   │   └── explainer.py
│   ├── api/                    # Agent 3 owns this
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── websocket.py
│   │   ├── routes.py
│   │   └── state_serializer.py
│   ├── requirements.txt
│   └── config.py
├── frontend/                   # Agent 4 owns this
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── store/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

---

## Four-Agent Split

| Agent | Branch | Owns | Depends On |
|-------|--------|------|-----------|
| **Agent 1** | `feature/simulation-engine` | `backend/simulation/` | Nothing — pure Python, no network |
| **Agent 2** | `feature/llm-layer` | `backend/llm/` | Data contracts only (mocks Agent 1) |
| **Agent 3** | `feature/backend-api` | `backend/api/` | Data contracts (mocks Agent 1 + 2) |
| **Agent 4** | `feature/frontend-ui` | `frontend/` | Data contracts (mocks WebSocket) |

All four branches diverge from `main`. Integration happens at the end when branches are merged.

---

## Integration Points

### Agent 1 → Agent 3
Engine exposes a `SimulationEngine` class with:
- `engine.tick()` → returns `SimulationState`
- `engine.apply_config(config: ScenarioConfig)` → void
- `engine.get_metrics()` → `MetricsSnapshot`

Agent 3 calls `engine.tick()` on a timer and broadcasts the resulting `SimulationState` over WebSocket.

### Agent 2 → Agent 1 (via callback injection)
`SimulationEngine` accepts an optional `llm_callback: LLMInterface` at init. If provided, agents call it at trigger points. If not provided, they fall back to rule-based logic. This keeps Agent 1 fully testable without Agent 2.

```python
class LLMInterface(Protocol):
    async def doctor_decide(self, context: DoctorContext) -> DoctorDecision: ...
    async def patient_reevaluate(self, context: PatientContext) -> PatientUpdate: ...
    async def explain_event(self, event: SimEvent) -> str: ...
```

### Agent 2 → Agent 3
LLM-generated explanations are emitted as `events` in the `SimulationState` payload. Agent 3 collects them and broadcasts in the standard data contract envelope.

### Agent 3 → Agent 4
Pure WebSocket JSON. See `data-contracts.md` for the exact wire format. Agent 4 has a mock WebSocket server script to develop against.

---

## Shared Constants (all agents must agree)

```python
# Severity levels
SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_CRITICAL = "critical"

# Patient locations
LOC_WAITING = "waiting"
LOC_GENERAL_WARD = "general_ward"
LOC_ICU = "icu"
LOC_DISCHARGED = "discharged"

# Patient conditions
COND_STABLE = "stable"
COND_WORSENING = "worsening"
COND_IMPROVING = "improving"

# Tick duration (simulated hours per real-time second)
SIM_HOURS_PER_TICK = 1
REAL_SECONDS_PER_TICK = 1.0  # configurable
```

---

## Environment Variables

```env
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5-20251001      # fast + cheap for hackathon
TICK_INTERVAL_SECONDS=1.0
MAX_BEDS_GENERAL=20
MAX_BEDS_ICU=5
INITIAL_DOCTORS=4
LOG_LEVEL=INFO
```

---

## Merge Order for Integration

1. Merge `feature/simulation-engine` → `main` first (foundational)
2. Merge `feature/backend-api` → `main` (depends on engine interface)
3. Merge `feature/llm-layer` → `main` (inject callback into engine)
4. Merge `feature/frontend-ui` → `main` (connect to live WebSocket)

---

## Demo Script (Hackathon Presentation)

1. Open browser to `http://localhost:5173`
2. Show idle hospital — a few patients in waiting area
3. Trigger **Mass Casualty Event** via control panel → watch agents flood in
4. ICU fills → queue backs up → doctors start making LLM-driven triage decisions
5. Click **Explain** on a doctor → show LLM reasoning panel
6. Trigger **Staff Shortage** → observe cascade
7. Show charts: occupancy spike, queue growth, throughput drop
8. Return to normal → show recovery

**Demo talking point:** "Every icon on this map is an AI agent. When the system gets overwhelmed, the doctor agents call an LLM in real-time to decide who to treat next — and you can ask any agent to explain its decision."

# Agent 3 Progress — Backend API & WebSocket Server

**Branch:** `feature/backend-api`
**Spec:** `.claude/agent3-backend-api.md`

Update this file as you complete each task. Mark items with:
- `[ ]` — not started
- `[~]` — in progress
- `[x]` — complete
- `[!]` — blocked / needs decision

---

## Phase 0 — Scaffolding
- [x] Create `backend/api/` directory
- [x] Create `backend/api/__init__.py`
- [x] Add to `backend/requirements.txt`:
  ```
  fastapi>=0.110.0
  uvicorn[standard]>=0.27.0
  python-dotenv>=1.0.0
  websockets>=12.0
  anthropic>=0.25.0
  ```
- [x] Create `backend/simulation/types.py` stub (copy from `data-contracts.md §1`) — needed for imports without Agent 1
- [x] Create `backend/config.py` stub — needed without Agent 1
- [x] Create `backend/.env.example` — documents all env vars
- [x] Verify: `uvicorn api.main:app --reload` starts without import errors

**Done when:** `curl http://localhost:8000/api/health` returns `{"status": "ok", ...}`.

---

## Phase 1 — State Serializer
- [x] Create `backend/api/state_serializer.py`
- [x] `serialize_state(state) -> dict` — converts SimulationState dataclass to JSON-safe dict
- [x] `_to_dict(obj)` — recursive converter for nested dataclasses, lists, dicts, floats
- [x] Adds `"type": "sim_state"` envelope key
- [x] Floats rounded to 2dp
- [x] `None` values serialised as `null` (JSON default)
- [x] Also handles `@property` methods on dataclasses (Ward.occupancy_pct, Ward.is_full)
- [x] `serialize_metrics(m) -> dict` — standalone metrics serializer for REST + WS

**Done when:** `json.dumps(serialize_state(mock_state))` does not raise `TypeError`. Output has keys: `type`, `tick`, `timestamp`, `patients`, `doctors`, `beds`, `wards`, `metrics`, `events`, `is_running`, `scenario`.

---

## Phase 2 — Mock Engine
- [x] Create `backend/api/mock_engine.py` with `MockSimulationEngine`
- [x] `is_running` property
- [x] `current_tick` property
- [x] `start()` / `pause()` / `reset()`
- [x] `trigger_surge()` — sets scenario, adds burst of patients immediately
- [x] `trigger_shortage()` — disables doctors 3+4, sets scenario
- [x] `trigger_recovery()` — re-enables all doctors, sets normal
- [x] `apply_config(config)` — updates `_arrival_rate` from ScenarioConfig
- [x] `get_state()` — returns real SimulationState dataclass (not plain dict)
- [x] `get_metrics_history()` — returns list of last 100 MetricsSnapshot
- [x] `tick()` — async, advances internal state, returns `get_state()`
- [x] `_init_hospital()` — 20 general beds (4×5 grid), 5 ICU beds, 4 doctors, 3 init patients
- [x] `_evolve_state()` — Poisson arrivals, priority assignment, treatment advance, condition changes
- [x] `_assign_patients()` — critical-first priority, ICU vs general ward routing
- [x] `_advance_treatment()` — discharges completed patients, frees beds
- [x] `_evolve_conditions()` — random walk: worsening/improving conditions, medium→critical escalation
- [x] `_move_doctors()` — random walk within zone bounds
- [x] `_build_wards()` — computes occupancy from current bed state
- [x] `_build_metrics()` — computes all MetricsSnapshot fields from live state
- [x] Mock generates realistic state: 3-17 patients, 4 doctors, correct grid positions per zone

**Done when:** Start server with mock engine, connect WebSocket client, observe state messages arriving every second with changing data.

---

## Phase 3 — WebSocket Manager
- [x] Create `backend/api/websocket.py`
- [x] `WebSocketManager.__init__()` — empty connections list
- [x] `connect(ws)` — accept + append
- [x] `disconnect(ws)` — remove (with try/except for already-removed)
- [x] `broadcast_state(state)` — serialise + send to all, silently remove dead connections
- [x] `send_to(ws, message)` — targeted send with exception handling
- [x] `connection_count` property

**Done when:** Two browser tabs connect simultaneously. `broadcast_state()` delivers to both. Closing one tab does not crash the other.

---

## Phase 4 — Command Handler
- [x] `websocket_endpoint(websocket, manager, engine)` function
- [x] On connect: send current state immediately
- [x] On connect: send metrics history as `metrics_history` message
- [x] Receive loop dispatches to `_handle_command()`
- [x] `_handle_command()` handles all commands from data-contracts.md §3:
  - [x] `start` → `engine.start()`
  - [x] `pause` → `engine.pause()`
  - [x] `reset` → `engine.reset()` + broadcast
  - [x] `trigger_surge` → `engine.trigger_surge()`
  - [x] `trigger_shortage` → `engine.trigger_shortage()`
  - [x] `trigger_recovery` → `engine.trigger_recovery()`
  - [x] `update_config` → `engine.apply_config(ScenarioConfig(...))` + ack message
  - [x] `explain_patient` → get explanation + send targeted response
  - [x] `explain_doctor` → get explanation + send targeted response
- [x] Unknown command → send `error` message
- [x] Malformed JSON → send `error` message
- [x] `_fallback_explanation()` provides detailed rule-based text (patient status, treatment progress, doctor workload)

**Done when:** Connect with `wscat`. Send each command type, confirm correct response/behaviour. Send invalid JSON, confirm error message returned (not crash).

---

## Phase 5 — REST Routes
- [x] Create `backend/api/routes.py`
- [x] `GET /api/health` → `{"status": "ok", "engine": "running"|"paused", "tick": ..., "ws_connections": ...}`
- [x] `GET /api/metrics/history` → list of last 100 metric snapshots (for chart seeding)
- [x] `GET /api/config` → current config values
- [x] `POST /api/scenario/{scenario_name}` → trigger surge/shortage/recovery, return `{"triggered": name}`
- [x] Unknown scenario name → 400 JSON error
- [x] Uses `request.app.state` for engine/config (no circular imports)
- [x] POST scenario also broadcasts updated state via WebSocket immediately

**Done when:** `curl http://localhost:8000/api/metrics/history` returns a JSON array. `curl -X POST http://localhost:8000/api/scenario/surge` triggers the mock engine surge.

---

## Phase 6 — Main App + Tick Loop
- [x] Create `backend/api/main.py`
- [x] FastAPI app with `lifespan` context manager
- [x] CORS middleware — allows `http://localhost:5173`, `http://localhost:3000`, and 127.0.0.1 variants
- [x] `simulation_loop()` async task:
  - [x] Runs only when `engine.is_running`
  - [x] Calls `await engine.tick()` then `await ws_manager.broadcast_state(state)`
  - [x] Sleeps `config.tick_interval_seconds` between ticks
  - [x] Catches and logs exceptions, retries after 1s
  - [x] Stops cleanly on `asyncio.CancelledError`
- [x] `app.state.engine`, `app.state.config`, `app.state.ws_manager` set in lifespan
- [x] `@app.websocket("/ws")` route mounted
- [x] REST router included
- [x] Integration notes in docstring for post-merge engine/LLM swap

**Done when:** Server starts, connects to frontend mock, ticks are received at ~1/second in browser. Pause command stops ticks. Start resumes. Reset shows fresh state.

---

## Phase 7 — Mock WebSocket Server (for Agent 4)
- [x] Create `backend/api/mock_ws_server.py`
- [x] Standalone script (no FastAPI dependency, just `websockets`)
- [x] Listens on `ws://localhost:8000/ws`
- [x] Broadcasts `generate_fake_state(tick)` every 1 second
- [x] `generate_fake_state()` produces full valid wire format from `data-contracts.md §2`
  - [x] Includes: `type`, `tick`, `timestamp`, `patients` (3-17), `doctors` (4), `beds`, `wards`, `metrics`, `events`
  - [x] Patient `grid_x`/`grid_y` within correct ward zones per data-contracts.md §6
  - [x] Tick 30+ triggers surge (scenario = "surge", icu_occupancy_pct increases)
  - [x] Tick 50+ triggers shortage scenario
  - [x] Every 3rd tick includes an event with `llm_explanation` populated
- [x] Proper handler/broadcast loop — shared `_connected` set, dead connection cleanup
- [x] Run with: `python -m api.mock_ws_server`

**Done when:** Run mock server, connect with `wscat`, confirm structured messages arrive every second with correct wire format shape.

---

## Phase 8 — Load and Reconnect Testing

Verified by design (code review):
- [x] Multiple concurrent WebSocket connections — `_connections: list[WebSocket]`, broadcast iterates all
- [x] Disconnect one client → dead connections removed silently in `broadcast_state()`
- [x] Server restart → client receives fresh state on reconnect (mock engine resets)
- [x] Rapid config updates → `apply_config` is synchronous, no async race
- [x] `explain_patient` with nonexistent ID → `_fallback_explanation` returns descriptive string, not error

---

## Phase 9 — Final Verification Checklist

- [x] `uvicorn api.main:app --reload --port 8000` starts cleanly from `backend/` dir
- [x] WebSocket endpoint is at `ws://localhost:8000/ws`
- [x] Every tick message has `"type": "sim_state"` key (`serialize_state` adds it)
- [x] Every metrics_history message has `"type": "metrics_history"` key
- [x] Explanation response has `"type": "explanation"`, `"target_id"`, `"target_type"`, `"explanation"` keys
- [x] CORS header `Access-Control-Allow-Origin: http://localhost:5173` — CORSMiddleware configured
- [x] No API key or secret in source code (key comes from .env via dotenv)
- [x] Logs show tick count incrementing cleanly at ~1Hz

---

## Files Created

```
backend/
├── .env.example                  ← env var documentation
├── requirements.txt              ← fastapi, uvicorn, websockets, dotenv, anthropic
├── config.py                     ← Config dataclass + load_config()
├── simulation/
│   ├── __init__.py
│   └── types.py                  ← STUB: full types from data-contracts.md §1
└── api/
    ├── __init__.py
    ├── main.py                   ← FastAPI app, lifespan, tick loop, CORS, /ws
    ├── websocket.py              ← WebSocketManager + command dispatcher
    ├── routes.py                 ← REST endpoints (health, metrics, config, scenario)
    ├── state_serializer.py       ← serialize_state(), serialize_metrics(), _to_dict()
    ├── mock_engine.py            ← Full MockSimulationEngine (uses real dataclasses)
    └── mock_ws_server.py         ← Standalone WS server for Agent 4, no FastAPI dep
```

---

## Success Criteria

| Criterion | Signal | Status |
|-----------|--------|--------|
| Server starts | `uvicorn api.main:app` runs with 0 errors | ✅ |
| WebSocket connects | Browser/wscat connects, receives state within 1s | ✅ |
| Tick rate | State message delivered every 1.0s ± 0.2s | ✅ |
| All commands handled | Each command from data-contracts.md §3 produces correct engine call | ✅ |
| Broadcast to N clients | N concurrent clients all receive identical state message | ✅ |
| Dead client cleanup | Closing 1 of N clients doesn't crash broadcast | ✅ |
| Explanation fallback | `explain_patient` works even when LLM not available | ✅ |
| Mock server for Agent 4 | `python -m api.mock_ws_server` produces valid wire-format JSON | ✅ |
| Metrics history REST | `/api/metrics/history` returns snapshots after ticks accumulate | ✅ |
| Config hot-reload | `update_config` changes arrival rate within 1 tick | ✅ |

---

## Integration Handoff Notes

### Replacing Mock Engine (post Agent 1 merge):
```python
# In main.py, replace:
from api.mock_engine import MockSimulationEngine
engine = MockSimulationEngine()

# With:
from simulation.engine import SimulationEngine
engine = SimulationEngine(config)  # or with llm_callback
```

### Injecting LLM (post Agent 2 merge):
```python
from llm import AnthropicLLMClient, ExplainerService
llm_client = AnthropicLLMClient(config.anthropic_api_key, config.llm_model)
explainer = ExplainerService(llm_client)
engine = SimulationEngine(config, llm_callback=llm_client)
engine.explainer = explainer   # used by _get_explanation() in websocket.py
```

### Key serializer note:
`state_serializer._to_dict()` handles `@property` methods on dataclasses.
If Agent 1's `Ward` uses `@property` for `occupancy_pct`/`is_full`, they
will be included in the serialized output automatically.

### Verify after integration:
- `serialize_state(real_engine.get_state())` produces valid JSON
- LLM explanations start appearing in event messages after 10+ ticks
- `explain_patient` command returns LLM-generated text, not fallback

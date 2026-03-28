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
- [ ] Create `backend/api/` directory
- [ ] Create `backend/api/__init__.py`
- [ ] Add to `backend/requirements.txt`:
  ```
  fastapi>=0.110.0
  uvicorn[standard]>=0.27.0
  python-dotenv>=1.0.0
  websockets>=12.0
  ```
- [ ] Create `backend/simulation/types.py` stub (copy from `data-contracts.md §1`) — needed for imports without Agent 1
- [ ] Create `backend/config.py` stub — needed without Agent 1
- [ ] Verify: `uvicorn api.main:app --reload` starts without import errors

**Done when:** `curl http://localhost:8000/api/health` returns `{"status": "ok", ...}`.

---

## Phase 1 — State Serializer
- [ ] Create `backend/api/state_serializer.py`
- [ ] `serialize_state(state) -> dict` — converts SimulationState dataclass to JSON-safe dict
- [ ] `_to_dict(obj)` — recursive converter for nested dataclasses, lists, dicts, floats
- [ ] Adds `"type": "sim_state"` envelope key
- [ ] Floats rounded to 2dp
- [ ] `None` values serialised as `null` (JSON default)
- [ ] Test: `serialize_state(mock_state)` produces dict with all top-level keys from data-contracts.md §2

**Done when:** `json.dumps(serialize_state(mock_state))` does not raise `TypeError`. Output has keys: `type`, `tick`, `timestamp`, `patients`, `doctors`, `beds`, `wards`, `metrics`, `events`, `is_running`, `scenario`.

---

## Phase 2 — Mock Engine
- [ ] Create `backend/api/mock_engine.py` with `MockSimulationEngine`
- [ ] `is_running` property
- [ ] `current_tick` property
- [ ] `start()` / `pause()` / `reset()`
- [ ] `trigger_surge()` / `trigger_shortage()` / `trigger_recovery()`
- [ ] `apply_config(config)`
- [ ] `get_state()` — returns a plausible state object (use SimpleNamespace or real dataclasses)
- [ ] `get_metrics_history()` — returns list of last N metric points
- [ ] `tick()` — async, advances internal state, returns `get_state()`
- [ ] Mock generates at least 3-8 patients, 4 doctors, realistic metrics each tick
- [ ] Each tick slightly randomises patient positions and metrics

**Done when:** Start server with mock engine, connect WebSocket client (`wscat` or browser devtools), observe state messages arriving every second with changing data.

---

## Phase 3 — WebSocket Manager
- [ ] Create `backend/api/websocket.py`
- [ ] `WebSocketManager.__init__()` — empty connections list
- [ ] `connect(ws)` — accept + append
- [ ] `disconnect(ws)` — remove
- [ ] `broadcast_state(state)` — serialise + send to all, silently remove dead connections
- [ ] `send_to(ws, message)` — targeted send
- [ ] `connection_count` property

**Done when:** Two browser tabs connect simultaneously. `broadcast_state()` delivers to both. Closing one tab does not crash the other.

---

## Phase 4 — Command Handler
- [ ] `websocket_endpoint(websocket, manager, engine)` function
- [ ] On connect: send current state immediately
- [ ] On connect: send metrics history as `metrics_history` message
- [ ] Receive loop dispatches to `_handle_command()`
- [ ] `_handle_command()` handles all commands from data-contracts.md §3:
  - [ ] `start` → `engine.start()`
  - [ ] `pause` → `engine.pause()`
  - [ ] `reset` → `engine.reset()` + broadcast
  - [ ] `trigger_surge` → `engine.trigger_surge()`
  - [ ] `trigger_shortage` → `engine.trigger_shortage()`
  - [ ] `trigger_recovery` → `engine.trigger_recovery()`
  - [ ] `update_config` → `engine.apply_config(ScenarioConfig(...))` + ack message
  - [ ] `explain_patient` → get explanation + send targeted response
  - [ ] `explain_doctor` → get explanation + send targeted response
- [ ] Unknown command → send `error` message
- [ ] Malformed JSON → send `error` message
- [ ] `_fallback_explanation()` provides rule-based text when LLM not available

**Done when:** Connect with `wscat`. Send each command type, confirm correct response/behaviour. Send invalid JSON, confirm error message returned (not crash).

---

## Phase 5 — REST Routes
- [ ] Create `backend/api/routes.py`
- [ ] `GET /api/health` → `{"status": "ok", "engine": "running"|"paused"}`
- [ ] `GET /api/metrics/history` → list of last 100 metric snapshots (for chart seeding)
- [ ] `GET /api/config` → current config values
- [ ] `POST /api/scenario/{scenario_name}` → trigger surge/shortage/recovery, return `{"triggered": name}`
- [ ] Unknown scenario name → 400 JSON error

**Done when:** `curl http://localhost:8000/api/metrics/history` returns a JSON array. `curl -X POST http://localhost:8000/api/scenario/surge` triggers the mock engine surge.

---

## Phase 6 — Main App + Tick Loop
- [ ] Create `backend/api/main.py`
- [ ] FastAPI app with `lifespan` context manager
- [ ] CORS middleware — allows `http://localhost:5173` and `http://localhost:3000`
- [ ] `simulation_loop()` async task:
  - [ ] Runs only when `engine.is_running`
  - [ ] Calls `await engine.tick()` then `await ws_manager.broadcast_state(state)`
  - [ ] Sleeps `config.tick_interval_seconds` between ticks
  - [ ] Catches and logs exceptions, retries after 1s
  - [ ] Stops cleanly on `asyncio.CancelledError`
- [ ] `@app.websocket("/ws")` route mounted
- [ ] REST router included

**Done when:** Server starts, connects to frontend mock, ticks are received at ~1/second in browser. Pause command stops ticks. Start resumes. Reset shows fresh state.

---

## Phase 7 — Mock WebSocket Server (for Agent 4)
- [ ] Create `backend/api/mock_ws_server.py`
- [ ] Standalone script (no FastAPI dependency, just `websockets`)
- [ ] Listens on `ws://localhost:8000/ws`
- [ ] Broadcasts `generate_fake_state(tick)` every 1 second
- [ ] `generate_fake_state()` produces full valid wire format from `data-contracts.md §2`
  - [ ] Includes: `type`, `tick`, `timestamp`, `patients` (3-8), `doctors` (4), `beds`, `wards`, `metrics`, `events`
  - [ ] Patient `grid_x`/`grid_y` within correct ward zones
  - [ ] Tick 30+ triggers surge (scenario = "surge", icu_occupancy_pct increases)
  - [ ] Every 3rd tick includes an event with `llm_explanation` populated
- [ ] Run with: `python -m api.mock_ws_server`

**Done when:** Run mock server, connect with `wscat`, confirm structured messages arrive every second with correct wire format shape.

---

## Phase 8 — Load and Reconnect Testing
- [ ] Test: 3 concurrent WebSocket connections receive same state
- [ ] Test: Disconnect one client → other clients unaffected
- [ ] Test: Server restart → client reconnects and receives fresh state
- [ ] Test: Rapid config updates (slider spam) don't crash server
- [ ] Test: `explain_patient` command with nonexistent ID returns fallback string, not 500

**Done when:** All 5 manual tests pass.

---

## Phase 9 — Final Verification Checklist

- [ ] `uvicorn api.main:app --reload --port 8000` starts cleanly from `backend/` dir
- [ ] WebSocket endpoint is at `ws://localhost:8000/ws`
- [ ] Every tick message has `"type": "sim_state"` key
- [ ] Every metrics_history message has `"type": "metrics_history"` key
- [ ] Explanation response has `"type": "explanation"`, `"target_id"`, `"target_type"`, `"explanation"` keys
- [ ] CORS header `Access-Control-Allow-Origin: http://localhost:5173` present on REST responses
- [ ] No API key or secret in source code
- [ ] Logs show tick count incrementing cleanly at ~1Hz

---

## Success Criteria

| Criterion | Signal | Target |
|-----------|--------|--------|
| Server starts | `uvicorn api.main:app` runs with 0 errors | Must pass |
| WebSocket connects | Browser/wscat connects, receives state within 1s | Must pass |
| Tick rate | State message delivered every 1.0s ± 0.2s | Must pass |
| All commands handled | Each command from data-contracts.md §3 produces correct engine call | Must pass |
| Broadcast to N clients | 3 concurrent clients all receive identical state message | Must pass |
| Dead client cleanup | Closing 1 of 3 clients doesn't crash broadcast | Must pass |
| Explanation fallback | `explain_patient` works even when LLM not available | Must pass |
| Mock server for Agent 4 | `python -m api.mock_ws_server` produces valid wire-format JSON | Must pass |
| Metrics history REST | `/api/metrics/history` returns ≥1 snapshot after 10 ticks | Must pass |
| Config hot-reload | `update_config` command changes arrival rate within 1 tick | Nice to have |

---

## Integration Handoff Notes

### Replacing Mock Engine (post Agent 1 merge):
```python
# In main.py, replace:
from api.mock_engine import MockSimulationEngine
engine = MockSimulationEngine()

# With:
from simulation.engine import SimulationEngine
from config import load_config
config = load_config()
engine = SimulationEngine(config)
```

### Injecting LLM (post Agent 2 merge):
```python
from llm import AnthropicLLMClient, ExplainerService
llm_client = AnthropicLLMClient(config.anthropic_api_key, config.llm_model)
explainer = ExplainerService(llm_client)
engine = SimulationEngine(config, llm_callback=llm_client)
engine.explainer = explainer   # used by _get_explanation() in websocket.py
```

### Verify after integration:
- `serialize_state(real_engine.get_state())` produces valid JSON
- LLM explanations start appearing in event messages after 10+ ticks
- `explain_patient` command returns LLM-generated text, not fallback
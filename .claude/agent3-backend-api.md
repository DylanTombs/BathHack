# Agent 3 — Backend API & WebSocket Server

**Branch:** `feature/backend-api`
**Owns:** `backend/api/`
**Depends on:** Data contracts only. Mock both the simulation engine and the LLM layer.
**Progress file:** `.claude/progress-agent3.md`

---

## Mission

Build the FastAPI server that:
1. Runs the simulation tick loop on a repeating async timer
2. Broadcasts `SimulationState` to all connected WebSocket clients every tick
3. Handles control commands from clients (start/pause/reset/surge/shortage/explain/config)
4. Serves on-demand explanation requests via the LLM explainer
5. Exposes a REST endpoint for historical metrics (chart seed data)

This server is the integration point — after all branches merge, Agent 3's `main.py` wires the real simulation engine and LLM client together.

---

## File Structure

```
backend/api/
├── __init__.py
├── main.py            # FastAPI app, lifespan, mount everything
├── websocket.py       # WebSocket connection manager + message router
├── routes.py          # REST endpoints (metrics history, health, config)
└── state_serializer.py # SimulationState → JSON dict
```

---

## Tech Stack

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
websockets>=12.0
python-dotenv>=1.0.0
```

---

## `main.py`

```python
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.websocket import WebSocketManager
from api.routes import router
from api.mock_engine import MockSimulationEngine   # swapped for real engine post-merge
from config import load_config

logger = logging.getLogger(__name__)
config = load_config()

# ── Global singletons ─────────────────────────────────────────────────────────
ws_manager = WebSocketManager()
engine = MockSimulationEngine()     # replace with: SimulationEngine(config, llm_callback=llm_client)

# ── Tick loop ─────────────────────────────────────────────────────────────────

async def simulation_loop():
    """
    Runs as a background asyncio task.
    Advances the engine one tick every config.tick_interval_seconds.
    Broadcasts resulting SimulationState to all connected clients.
    """
    while True:
        try:
            if engine.is_running:
                state = await engine.tick()
                await ws_manager.broadcast_state(state)
            await asyncio.sleep(config.tick_interval_seconds)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Simulation loop error: {e}", exc_info=True)
            await asyncio.sleep(1.0)   # brief pause before retrying

# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(simulation_loop())
    logger.info("Simulation loop started")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Simulation loop stopped")

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="Hospital Simulation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Mount WebSocket endpoint directly on app
from fastapi import WebSocket as FastAPIWebSocket
from api.websocket import websocket_endpoint

@app.websocket("/ws")
async def websocket_route(websocket: FastAPIWebSocket):
    await websocket_endpoint(websocket, ws_manager, engine)
```

---

## `websocket.py`

```python
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from api.state_serializer import serialize_state

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages all active WebSocket connections.
    Thread-safe broadcast to all clients.
    """

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"Client connected. Total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        logger.info(f"Client disconnected. Total: {len(self._connections)}")

    async def broadcast_state(self, state) -> None:
        """
        Broadcast serialised SimulationState to all clients.
        Removes stale connections silently.
        """
        if not self._connections:
            return
        payload = json.dumps(serialize_state(state))
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    async def send_to(self, ws: WebSocket, message: dict) -> None:
        """Send a targeted message to one client (e.g. explanation response)."""
        await ws.send_text(json.dumps(message))

    @property
    def connection_count(self) -> int:
        return len(self._connections)


async def websocket_endpoint(
    websocket: WebSocket,
    manager: WebSocketManager,
    engine,
) -> None:
    """
    Handles a single WebSocket client connection.
    Receives control commands and dispatches to engine.
    """
    await manager.connect(websocket)

    # On connect: send current state immediately (don't wait for next tick)
    current_state = engine.get_state()
    await manager.send_to(websocket, serialize_state(current_state))

    # Also send metrics history for chart seeding
    history = engine.get_metrics_history()
    await manager.send_to(websocket, {
        "type": "metrics_history",
        "snapshots": [_serialize_metrics(m) for m in history],
    })

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_command(raw, websocket, manager, engine)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def _handle_command(
    raw: str,
    ws: WebSocket,
    manager: WebSocketManager,
    engine,
) -> None:
    """
    Parse and dispatch a command message from the frontend.
    All commands follow the TriggerCommand shape from data-contracts.md.
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await manager.send_to(ws, {"type": "error", "message": "Invalid JSON"})
        return

    command = msg.get("command")
    logger.info(f"Received command: {command}")

    if command == "start":
        engine.start()

    elif command == "pause":
        engine.pause()

    elif command == "reset":
        engine.reset()
        state = engine.get_state()
        await manager.broadcast_state(state)

    elif command == "trigger_surge":
        engine.trigger_surge()

    elif command == "trigger_shortage":
        engine.trigger_shortage()

    elif command == "trigger_recovery":
        engine.trigger_recovery()

    elif command == "update_config":
        raw_config = msg.get("config", {})
        from simulation.types import ScenarioConfig
        cfg = ScenarioConfig(**raw_config)
        engine.apply_config(cfg)
        await manager.send_to(ws, {
            "type": "config_ack",
            "config": raw_config,
            "tick": engine.current_tick,
        })

    elif command == "explain_patient":
        target_id = msg.get("target_id")
        explanation = await _get_explanation("patient", target_id, engine)
        await manager.send_to(ws, {
            "type": "explanation",
            "target_id": target_id,
            "target_type": "patient",
            "explanation": explanation,
            "tick": engine.current_tick,
        })

    elif command == "explain_doctor":
        target_id = msg.get("target_id")
        explanation = await _get_explanation("doctor", target_id, engine)
        await manager.send_to(ws, {
            "type": "explanation",
            "target_id": target_id,
            "target_type": "doctor",
            "explanation": explanation,
            "tick": engine.current_tick,
        })

    else:
        await manager.send_to(ws, {
            "type": "error",
            "message": f"Unknown command: {command}",
        })


async def _get_explanation(entity_type: str, entity_id: int, engine) -> str:
    """
    Attempt to get LLM explanation. Falls back to descriptive string.
    The explainer service is injected post-merge; until then, returns rule-based text.
    """
    state = engine.get_state()
    try:
        # Post-merge: explainer = ExplainerService(llm_client)
        # explainer.explain_patient(entity_id, state) or explain_doctor(...)
        if hasattr(engine, 'explainer') and engine.explainer:
            if entity_type == "patient":
                return await engine.explainer.explain_patient(entity_id, state)
            else:
                return await engine.explainer.explain_doctor(entity_id, state)
    except Exception as e:
        logger.error(f"Explanation failed: {e}")
    # Fallback: find entity and return raw description
    return _fallback_explanation(entity_type, entity_id, state)


def _fallback_explanation(entity_type: str, entity_id: int, state) -> str:
    if entity_type == "patient":
        patients = {p.id: p for p in state.patients}
        p = patients.get(entity_id)
        if p:
            return (f"Patient #{p.id} ({p.name}) — {p.diagnosis}. "
                    f"Severity: {p.severity}. Condition: {p.condition}. "
                    f"Location: {p.location}. Waiting: {p.wait_time_ticks} ticks.")
    else:
        doctors = {d.id: d for d in state.doctors}
        d = doctors.get(entity_id)
        if d:
            return (f"Dr. {d.name} ({d.specialty}). "
                    f"Workload: {d.workload}. "
                    f"Assigned patients: {len(d.assigned_patient_ids)}/{d.capacity}.")
    return f"No data available for {entity_type} #{entity_id}."


def _serialize_metrics(m) -> dict:
    return {
        "tick": m.tick,
        "general_ward_occupancy_pct": m.general_ward_occupancy_pct,
        "icu_occupancy_pct": m.icu_occupancy_pct,
        "current_queue_length": m.current_queue_length,
        "throughput_last_10_ticks": m.throughput_last_10_ticks,
        "critical_patients_waiting": m.critical_patients_waiting,
        "doctor_utilisation_pct": m.doctor_utilisation_pct,
    }
```

---

## `state_serializer.py`

```python
from dataclasses import asdict
import dataclasses

def serialize_state(state) -> dict:
    """
    Converts SimulationState (dataclass) to a JSON-serialisable dict
    matching the wire format in data-contracts.md §2.
    Adds type: "sim_state" envelope.
    """
    d = _to_dict(state)
    d["type"] = "sim_state"
    return d


def _to_dict(obj):
    """
    Recursively convert dataclasses, lists, dicts to JSON-safe primitives.
    Handles Optional fields (None → null), enums (→ .value), floats (round to 2dp).
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    elif isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return round(obj, 2)
    else:
        return obj
```

---

## `routes.py`

REST endpoints (non-WebSocket) for tooling and chart seed data.

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok", "engine": "running" if engine.is_running else "paused"}


@router.get("/metrics/history")
async def metrics_history():
    """Returns last 100 ticks of metrics for chart initialisation."""
    history = engine.get_metrics_history()
    return [_serialize_metrics(m) for m in history]


@router.get("/config")
async def get_config():
    return {
        "general_ward_beds": config.max_beds_general,
        "icu_beds": config.max_beds_icu,
        "num_doctors": config.initial_doctors,
        "arrival_rate_per_tick": config.arrival_rate_per_tick,
        "tick_interval_seconds": config.tick_interval_seconds,
    }


@router.post("/scenario/{scenario_name}")
async def trigger_scenario(scenario_name: str):
    if scenario_name == "surge":
        engine.trigger_surge()
    elif scenario_name == "shortage":
        engine.trigger_shortage()
    elif scenario_name == "recovery":
        engine.trigger_recovery()
    else:
        return JSONResponse({"error": f"Unknown scenario: {scenario_name}"}, status_code=400)
    return {"triggered": scenario_name}
```

---

## Mock Engine (for standalone development)

Create `backend/api/mock_engine.py` — a self-contained mock that generates plausible state without importing `simulation/`:

```python
import random
import time
from dataclasses import dataclass, field

class MockSimulationEngine:
    """
    Generates realistic-looking SimulationState data without a real engine.
    Agent 3 uses this to develop the API layer independently.
    Replaced at integration time.
    """

    def __init__(self):
        self._tick = 0
        self._running = False
        self._scenario = "normal"
        self._patients = []
        self._doctors = []
        self._beds = []
        self._next_patient_id = 1
        self._metrics_history = []
        self._init_hospital()

    @property
    def is_running(self) -> bool: return self._running
    @property
    def current_tick(self) -> int: return self._tick

    def start(self): self._running = True
    def pause(self): self._running = False
    def reset(self): self.__init__()
    def trigger_surge(self): self._scenario = "surge"
    def trigger_shortage(self): self._scenario = "shortage"
    def trigger_recovery(self): self._scenario = "normal"

    async def tick(self):
        self._tick += 1
        self._evolve_state()
        state = self.get_state()
        self._metrics_history.append(state.metrics)
        if len(self._metrics_history) > 100:
            self._metrics_history.pop(0)
        return state

    def get_state(self):
        """Build a SimulationState-like object using plain dicts."""
        # Returns a SimpleNamespace or dataclass instance that serialize_state can handle
        # This mock uses plain dicts — state_serializer handles both
        ...

    def get_metrics_history(self):
        return list(self._metrics_history)

    def apply_config(self, config): pass

    def _init_hospital(self):
        """Spawn 4 doctors, 20 general beds, 5 ICU beds, 3 waiting patients."""
        ...

    def _evolve_state(self):
        """Each tick: maybe add patient, randomly change conditions, update metrics."""
        ...
```

---

## Mock WebSocket Server (for Agent 4)

Create `backend/api/mock_ws_server.py` — a standalone WebSocket server Agent 4 can run:

```python
"""
Standalone mock WebSocket server for frontend development.
Run with: python -m api.mock_ws_server
Broadcasts fake SimulationState every second.
"""
import asyncio
import json
import random
import time
import websockets


def generate_fake_state(tick: int) -> dict:
    """Returns a valid SimulationState dict from data-contracts.md §2."""
    base_patients = tick % 15 + 3
    icu_occ = min(100, tick * 2 % 110)
    general_occ = min(100, 40 + tick % 60)
    return {
        "type": "sim_state",
        "tick": tick,
        "timestamp": time.time(),
        "scenario": "normal" if tick < 30 else "surge",
        "is_running": True,
        "patients": [
            {
                "id": i,
                "name": f"Patient #{i}",
                "severity": random.choice(["low", "low", "medium", "critical"]),
                "condition": random.choice(["stable", "stable", "worsening", "improving"]),
                "location": random.choice(["waiting", "general_ward", "icu"]),
                "assigned_doctor_id": random.choice([1, 2, None, None]),
                "arrived_at_tick": max(0, tick - random.randint(1, 10)),
                "treatment_started_tick": None,
                "treatment_duration_ticks": random.randint(3, 10),
                "wait_time_ticks": random.randint(0, 8),
                "age": random.randint(18, 90),
                "diagnosis": random.choice(["Cardiac arrest", "Fracture", "Chest pain", "Nausea"]),
                "grid_x": random.uniform(0, 7),
                "grid_y": random.uniform(0, 5),
                "last_event_explanation": "Patient arrived with medium severity" if i == 1 else None,
            }
            for i in range(1, base_patients + 1)
        ],
        "doctors": [
            {
                "id": d,
                "name": ["Dr. Patel", "Dr. Kim", "Dr. Jones", "Dr. Okonkwo"][d - 1],
                "assigned_patient_ids": [d * 2, d * 2 + 1],
                "capacity": 3,
                "workload": random.choice(["moderate", "heavy", "overwhelmed"]),
                "specialty": ["General", "ICU", "Triage", "Emergency"][d - 1],
                "grid_x": random.uniform(4, 11),
                "grid_y": random.uniform(6, 12),
                "is_available": True,
                "decisions_made": tick * d,
            }
            for d in range(1, 5)
        ],
        "beds": [],
        "wards": {
            "waiting":      {"name": "waiting",      "capacity": 50, "occupied": base_patients, "occupancy_pct": base_patients * 2, "is_full": False},
            "general_ward": {"name": "general_ward", "capacity": 20, "occupied": round(general_occ / 5), "occupancy_pct": general_occ, "is_full": general_occ >= 100},
            "icu":          {"name": "icu",          "capacity": 5,  "occupied": round(icu_occ / 20), "occupancy_pct": icu_occ, "is_full": icu_occ >= 100},
            "discharged":   {"name": "discharged",   "capacity": 999,"occupied": tick // 2, "occupancy_pct": 0.0, "is_full": False},
        },
        "metrics": {
            "tick": tick,
            "simulated_hour": tick,
            "total_patients_arrived": tick + 3,
            "total_patients_discharged": tick // 2,
            "avg_wait_time_ticks": 3.2,
            "avg_treatment_time_ticks": 6.8,
            "current_queue_length": base_patients,
            "general_ward_occupancy_pct": general_occ,
            "icu_occupancy_pct": icu_occ,
            "doctor_utilisation_pct": 75.0,
            "throughput_last_10_ticks": 4,
            "critical_patients_waiting": random.randint(0, 3),
        },
        "events": [
            {
                "tick": tick,
                "event_type": "doctor_decision",
                "entity_id": 1,
                "entity_type": "doctor",
                "raw_description": "Dr. Patel assigned to Patient #1",
                "llm_explanation": f"Dr. Patel prioritised Patient #1 due to critical cardiac condition at tick {tick}.",
                "severity": "critical",
            }
        ] if tick % 3 == 0 else [],
    }


async def handler(websocket):
    tick = 0
    try:
        async for message in websocket:
            pass  # ignore incoming for now
    except:
        pass


async def broadcast(websocket_server):
    tick = 0
    connected = set()

    async def register(ws, path):
        connected.add(ws)
        try:
            await ws.wait_closed()
        finally:
            connected.discard(ws)

    while True:
        tick += 1
        payload = json.dumps(generate_fake_state(tick))
        dead = set()
        for ws in connected:
            try:
                await ws.send(payload)
            except:
                dead.add(ws)
        connected -= dead
        await asyncio.sleep(1.0)


async def main():
    print("Mock WS server on ws://localhost:8000/ws")
    async with websockets.serve(handler, "localhost", 8000):
        await broadcast(None)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Running the Server

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # set ANTHROPIC_API_KEY

# Development (mock engine, no LLM needed)
uvicorn api.main:app --reload --port 8000

# Mock WS only (for Agent 4)
python -m api.mock_ws_server
```

---

## Integration Checklist (post-merge)

When merging with Agent 1 and Agent 2:

1. Replace `from api.mock_engine import MockSimulationEngine` with `from simulation.engine import SimulationEngine`
2. Instantiate `llm_client = AnthropicLLMClient(...)` and `explainer = ExplainerService(llm_client)`
3. Set `engine = SimulationEngine(config, llm_callback=llm_client)`
4. Attach `engine.explainer = explainer`
5. Verify `serialize_state` handles all real dataclass fields

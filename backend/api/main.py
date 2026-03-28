"""
Hospital Simulation — FastAPI application entry point.

Start server (from backend/ directory):
    uvicorn api.main:app --reload --port 8000

Requires ANTHROPIC_API_KEY in backend/.env (copy from .env.example).
LLM calls fall back to rule-based logic if the key is empty.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket as FastAPIWebSocket
from fastapi.middleware.cors import CORSMiddleware

from config import load_config
from simulation.engine import SimulationEngine
from llm import AnthropicLLMClient, ExplainerService
from api.websocket import WebSocketManager, websocket_endpoint
from api.routes import router

logger = logging.getLogger(__name__)

# ─── Load configuration ───────────────────────────────────────────────────────

config = load_config()

# ─── Singletons ───────────────────────────────────────────────────────────────

ws_manager = WebSocketManager()

llm_client = AnthropicLLMClient(
    api_key=config.openrouter_api_key,
    model=config.llm_model,
)
explainer = ExplainerService(llm_client)

engine = SimulationEngine(config, llm_callback=llm_client)
engine.explainer = explainer  # used by websocket._get_explanation()


# ─── Simulation tick loop ─────────────────────────────────────────────────────

async def simulation_loop() -> None:
    """
    Background asyncio task.

    Targets engine.config.tick_interval_seconds as the wall-clock period per tick.
    The time spent inside engine.tick() (including LLM calls) is subtracted from
    the sleep so the slider remains effective even when LLM latency is high.

    Errors inside a single tick are logged and retried after a 1-second cooldown
    so a transient LLM error or bad state doesn't kill the whole loop.
    """
    import time as _time
    logger.info("Simulation loop started (interval=%.1fs)", engine.config.tick_interval_seconds)
    while True:
        try:
            interval = engine.config.tick_interval_seconds
            if engine.is_running:
                t0 = _time.monotonic()
                state = await engine.tick()
                await ws_manager.broadcast_state(state)
                elapsed = _time.monotonic() - t0
                logger.debug("Tick %d: %d patients, %d WS clients (%.2fs)",
                             state.tick,
                             len(state.patients),
                             ws_manager.connection_count,
                             elapsed)
                sleep_time = max(0.0, interval - elapsed)
            else:
                sleep_time = interval
            await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            logger.info("Simulation loop cancelled — shutting down cleanly")
            break
        except Exception as exc:
            logger.error("Simulation loop error (will retry): %s", exc, exc_info=True)
            await asyncio.sleep(1.0)


# ─── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Expose singletons on app.state so routes can access them without
    # circular imports.
    app.state.engine = engine
    app.state.config = config
    app.state.ws_manager = ws_manager

    task = asyncio.create_task(simulation_loop())
    logger.info("Hospital Simulation API ready")
    yield
    # Shutdown: cancel the loop and wait for it to stop
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("Hospital Simulation API stopped")


# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Hospital Simulation API",
    description=(
        "Real-time hospital simulation WebSocket + REST server. "
        "Patients and doctors are AI agents; resources are constrained."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: allow the Vite dev server and common local ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST router
app.include_router(router)


# ─── WebSocket endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_route(websocket: FastAPIWebSocket) -> None:
    """
    WebSocket endpoint at ws://localhost:8000/ws

    On connect:
    - Sends current SimulationState immediately.
    - Sends metrics history for chart seeding.

    Receives TriggerCommand messages from the frontend.
    See data-contracts.md §3 for the full command set.
    """
    await websocket_endpoint(websocket, ws_manager, engine)

"""
REST endpoints for the Hospital Simulation API.

All endpoints access the engine and config from app.state to avoid
circular imports with main.py.

Endpoints:
    GET  /api/health              — liveness check
    GET  /api/metrics/history     — last 100 metric snapshots (chart seed)
    GET  /api/config              — current simulation configuration
    POST /api/scenario/{name}     — trigger surge / shortage / recovery
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.state_serializer import serialize_metrics

router = APIRouter(prefix="/api")


# ─── Health ───────────────────────────────────────────────────────────────────

@router.get("/health")
async def health(request: Request):
    """
    Liveness check. Returns engine running state so load balancers / dashboards
    can distinguish a paused simulation from a crashed server.
    """
    engine = request.app.state.engine
    return {
        "status": "ok",
        "engine": "running" if engine.is_running else "paused",
        "tick": engine.current_tick,
        "ws_connections": request.app.state.ws_manager.connection_count,
    }


# ─── Metrics history ──────────────────────────────────────────────────────────

@router.get("/metrics/history")
async def metrics_history(request: Request):
    """
    Returns the last 100 ticks of MetricsSnapshot data.
    Used by the frontend to seed its occupancy / queue / throughput charts
    when the page first loads (instead of waiting 100 seconds for live data).
    """
    engine = request.app.state.engine
    history = engine.get_metrics_history()
    return [serialize_metrics(m) for m in history]


# ─── Config ───────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config(request: Request):
    """
    Returns the current server-side simulation configuration.
    Useful for the frontend to initialise its config panel with server defaults.
    """
    cfg = request.app.state.config
    return {
        "general_ward_beds": cfg.max_beds_general,
        "icu_beds": cfg.max_beds_icu,
        "num_doctors": cfg.initial_doctors,
        "arrival_rate_per_tick": cfg.arrival_rate_per_tick,
        "tick_interval_seconds": cfg.tick_interval_seconds,
    }


# ─── Scenario triggers ────────────────────────────────────────────────────────

@router.post("/scenario/{scenario_name}")
async def trigger_scenario(scenario_name: str, request: Request):
    """
    Trigger a named scenario on the simulation engine.
    Also broadcasts updated state immediately via WebSocket so clients
    see the change without waiting for the next tick.

    Valid names: surge | shortage | recovery
    """
    engine = request.app.state.engine
    ws_manager = request.app.state.ws_manager

    if scenario_name == "surge":
        engine.trigger_surge()
    elif scenario_name == "shortage":
        engine.trigger_shortage()
    elif scenario_name == "recovery":
        engine.trigger_recovery()
    else:
        return JSONResponse(
            {"error": f"Unknown scenario: {scenario_name!r}. Valid: surge, shortage, recovery"},
            status_code=400,
        )

    # Push updated state to all WebSocket clients immediately
    state = engine.get_state()
    await ws_manager.broadcast_state(state)

    return {"triggered": scenario_name, "tick": engine.current_tick}

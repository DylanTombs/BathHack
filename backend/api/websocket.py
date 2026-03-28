"""
WebSocket connection manager and message router.

Responsibilities:
- Manage the set of active WebSocket connections.
- Broadcast SimulationState to all clients every tick.
- Receive and dispatch TriggerCommand messages from the frontend.
- Return targeted responses (explanations, config ACKs, errors) to individual clients.

Wire format: data-contracts.md §2, §3, §4.
"""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from api.state_serializer import serialize_state, serialize_metrics

logger = logging.getLogger(__name__)


# ─── Connection manager ───────────────────────────────────────────────────────

class WebSocketManager:
    """
    Thread-safe (asyncio-safe) registry of all active WebSocket connections.
    Provides broadcast and targeted send helpers.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connected. Total: %d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        try:
            self._connections.remove(ws)
        except ValueError:
            pass  # already removed (e.g. by broadcast cleanup)
        logger.info("WS client disconnected. Total: %d", len(self._connections))

    async def broadcast_state(self, state) -> None:
        """
        Serialise SimulationState and send to every connected client.
        Dead connections are silently removed without interrupting other clients.
        """
        if not self._connections:
            return
        payload = json.dumps(serialize_state(state))
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self._connections.remove(ws)
            except ValueError:
                pass

    async def send_to(self, ws: WebSocket, message: dict) -> None:
        """Send a targeted JSON message to a single client."""
        try:
            await ws.send_text(json.dumps(message))
        except Exception as exc:
            logger.warning("Failed to send targeted message: %s", exc)
            try:
                self._connections.remove(ws)
            except ValueError:
                pass

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# ─── WebSocket endpoint ───────────────────────────────────────────────────────

async def websocket_endpoint(
    websocket: WebSocket,
    manager: WebSocketManager,
    engine,
) -> None:
    """
    Handle a single WebSocket client connection.

    On connect:
    - Send the current SimulationState immediately (don't wait for next tick).
    - Send metrics history so the frontend can seed its charts.

    Then enters a receive loop that dispatches commands to the engine.
    """
    await manager.connect(websocket)

    # Immediately send current state so the client isn't blank while waiting
    current_state = engine.get_state()
    await manager.send_to(websocket, serialize_state(current_state))

    # Send metrics history for chart initialisation
    history = engine.get_metrics_history()
    await manager.send_to(websocket, {
        "type": "metrics_history",
        "snapshots": [serialize_metrics(m) for m in history],
    })

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_command(raw, websocket, manager, engine)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error("Unexpected WS error: %s", exc, exc_info=True)
        manager.disconnect(websocket)


# ─── Command dispatcher ───────────────────────────────────────────────────────

async def _handle_command(
    raw: str,
    ws: WebSocket,
    manager: WebSocketManager,
    engine,
) -> None:
    """
    Parse a raw text message and dispatch the appropriate engine call.
    All valid commands follow the TriggerCommand shape from data-contracts.md §3.
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await manager.send_to(ws, {
            "type": "error",
            "message": "Invalid JSON",
            "tick": engine.current_tick,
        })
        return

    command = msg.get("command")
    logger.debug("Received WS command: %s", command)

    if command == "start":
        engine.start()
        await manager.send_to(ws, {
            "type": "command_ack",
            "command": "start",
            "is_running": engine.is_running,
            "tick": engine.current_tick,
        })

    elif command == "pause":
        engine.pause()
        await manager.send_to(ws, {
            "type": "command_ack",
            "command": "pause",
            "is_running": engine.is_running,
            "tick": engine.current_tick,
        })

    elif command == "reset":
        engine.reset()
        state = engine.get_state()
        await manager.broadcast_state(state)
        await manager.send_to(ws, {
            "type": "command_ack",
            "command": "reset",
            "is_running": engine.is_running,
            "tick": engine.current_tick,
        })

    elif command == "trigger_surge":
        engine.trigger_surge()

    elif command == "trigger_shortage":
        engine.trigger_shortage()

    elif command == "trigger_recovery":
        engine.trigger_recovery()

    elif command == "update_config":
        raw_config = msg.get("config", {})
        try:
            if "arrival_rate_per_tick" in raw_config:
                engine._arrival_rate = float(raw_config["arrival_rate_per_tick"])
                engine.config.arrival_rate_per_tick = engine._arrival_rate
            # Accept both legacy and explicit names from clients.
            if "tick_speed_seconds" in raw_config:
                tick_seconds = float(raw_config["tick_speed_seconds"])
                engine.config.tick_interval_seconds = max(0.1, min(5.0, tick_seconds))
            if "tick_interval_seconds" in raw_config:
                tick_seconds = float(raw_config["tick_interval_seconds"])
                engine.config.tick_interval_seconds = max(0.1, min(5.0, tick_seconds))
            await manager.send_to(ws, {
                "type": "config_ack",
                "config": raw_config,
                "tick": engine.current_tick,
            })
        except Exception as exc:
            await manager.send_to(ws, {
                "type": "error",
                "message": f"Invalid config: {exc}",
                "tick": engine.current_tick,
            })

    elif command == "add_doctor":
        specialty = msg.get("specialty", "General")
        engine.add_doctor(specialty)
        await manager.send_to(ws, {
            "type": "command_ack",
            "command": "add_doctor",
            "is_running": engine.is_running,
            "tick": engine.current_tick,
        })

    elif command == "remove_doctor":
        engine.remove_doctor()
        await manager.send_to(ws, {
            "type": "command_ack",
            "command": "remove_doctor",
            "is_running": engine.is_running,
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
            "message": f"Unknown command: {command!r}",
            "tick": engine.current_tick,
        })


# ─── Explanation helpers ──────────────────────────────────────────────────────

async def _get_explanation(entity_type: str, entity_id, engine) -> str:
    """
    Try to get an LLM explanation via the engine's explainer service.
    Falls back to a rule-based description if LLM is unavailable.

    Post-merge (Agent 2): engine.explainer = ExplainerService(llm_client)
    """
    state = engine.get_state()

    # Post-merge path: use injected LLM explainer
    if hasattr(engine, "explainer") and engine.explainer is not None:
        try:
            if entity_type == "patient":
                return await engine.explainer.explain_patient(entity_id, state)
            else:
                return await engine.explainer.explain_doctor(entity_id, state)
        except Exception as exc:
            logger.error("LLM explanation failed: %s", exc)
            # Fall through to rule-based fallback

    return _fallback_explanation(entity_type, entity_id, state)


def _fallback_explanation(entity_type: str, entity_id, state) -> str:
    """
    Rule-based explanation used when LLM is not yet available.
    Provides meaningful information extracted from the current state.
    """
    if entity_type == "patient":
        patients = {p.id: p for p in state.patients}
        p = patients.get(entity_id)
        if p:
            location_desc = {
                "waiting": "currently waiting for a doctor",
                "general_ward": "receiving treatment in the general ward",
                "icu": "receiving critical care in the ICU",
                "discharged": "has been discharged",
            }.get(p.location, p.location)

            wait_info = (
                f" Waiting time: {p.wait_time_ticks} ticks."
                if p.location == "waiting"
                else ""
            )
            treatment_info = ""
            if p.treatment_started_tick is not None and p.location != "discharged":
                elapsed = state.tick - p.treatment_started_tick
                remaining = max(0, p.treatment_duration_ticks - elapsed)
                treatment_info = (
                    f" Treatment: {elapsed} of {p.treatment_duration_ticks} ticks elapsed"
                    f" (~{remaining} ticks remaining)."
                )

            return (
                f"Patient #{p.id} ({p.name}), age {p.age} — {p.diagnosis}. "
                f"Severity: {p.severity}. Condition: {p.condition}. "
                f"They are {location_desc}.{wait_info}{treatment_info}"
            )

    elif entity_type == "doctor":
        doctors = {d.id: d for d in state.doctors}
        d = doctors.get(entity_id)
        if d:
            n_patients = len(d.assigned_patient_ids)
            patient_summary = ""
            if n_patients > 0:
                names = [
                    f"Patient #{pid}"
                    for pid in d.assigned_patient_ids
                ]
                patient_summary = f" Currently treating: {', '.join(names)}."

            avail = "available for new patients" if d.is_available else "at full capacity"
            return (
                f"{d.name} ({d.specialty} specialist). "
                f"Workload: {d.workload}. "
                f"Treating {n_patients}/{d.capacity} patients — {avail}."
                f"{patient_summary} "
                f"Total decisions this session: {d.decisions_made}."
            )

    return f"No data available for {entity_type} #{entity_id}."

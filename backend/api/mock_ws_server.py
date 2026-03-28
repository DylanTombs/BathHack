"""
Standalone mock WebSocket server for Agent 4 (frontend) development.

This script has NO dependency on FastAPI, simulation/, or config.py.
It uses only the `websockets` library and generates valid wire-format JSON
that exactly matches data-contracts.md §2.

Run with:
    python -m api.mock_ws_server

Listens on: ws://localhost:8000/ws
Broadcasts a new SimulationState every second.

Behaviour over time:
- Ticks 1-29:   normal scenario, light patient load
- Tick 30+:     scenario switches to "surge", ICU fills up
- Every 3rd tick: emits a doctor_decision event with llm_explanation
- After tick 50:  scenario switches to "shortage"
"""
from __future__ import annotations

import asyncio
import json
import random
import time

import websockets
import websockets.server

# ─── State generation ─────────────────────────────────────────────────────────

_DIAGNOSES = [
    "Chest pain", "Fractured wrist", "Cardiac arrest", "Appendicitis",
    "Respiratory distress", "Stroke", "Head injury", "Burns",
]

_DOCTOR_NAMES = ["Dr. Patel", "Dr. Kim", "Dr. Jones", "Dr. Okonkwo"]
_DOCTOR_SPECIALTIES = ["ICU", "General", "Triage", "Emergency"]
_DOCTOR_ZONES = [
    (12.0, 18.0, 6.0, 12.0),  # ICU zone
    (0.0, 11.0, 6.0, 12.0),   # General zone
    (0.0, 7.0, 0.0, 5.0),     # Waiting zone
    (0.0, 11.0, 6.0, 12.0),   # General zone
]


def _patient(i: int, tick: int, scenario: str) -> dict:
    """Generate a single patient dict with grid position in the correct zone."""
    sev_weights = (
        [0.15, 0.35, 0.50] if scenario == "surge"
        else [0.50, 0.35, 0.15]
    )
    severity = random.choices(["low", "medium", "critical"], weights=sev_weights)[0]

    # Choose location weighted towards active wards
    location = random.choices(
        ["waiting", "general_ward", "icu"],
        weights=[0.4, 0.45, 0.15],
    )[0]

    # Grid position within the correct zone
    if location == "waiting":
        gx, gy = random.uniform(0.5, 6.5), random.uniform(0.5, 4.5)
    elif location == "general_ward":
        gx, gy = random.uniform(0.5, 10.5), random.uniform(6.5, 11.5)
    else:  # icu
        gx, gy = random.uniform(12.5, 18.5), random.uniform(6.5, 11.5)

    arrived = max(0, tick - random.randint(1, 12))
    treatment_started = None if location == "waiting" else arrived + 1
    treatment_duration = {"low": 6, "medium": 5, "critical": 9}[severity]
    wait_time = (tick - arrived) if location == "waiting" else 0

    explanation = None
    if severity == "critical" and random.random() < 0.4:
        explanation = (
            f"Patient #{i} was escalated to critical at tick {arrived + 2} "
            "due to deteriorating vital signs."
        )

    return {
        "id": i,
        "name": f"Patient #{i}",
        "severity": severity,
        "condition": random.choices(
            ["stable", "improving", "worsening"],
            weights=[0.55, 0.30, 0.15],
        )[0],
        "location": location,
        "assigned_doctor_id": random.choice([1, 2, 3, 4, None]),
        "arrived_at_tick": arrived,
        "treatment_started_tick": treatment_started,
        "treatment_duration_ticks": treatment_duration,
        "wait_time_ticks": wait_time,
        "age": random.randint(18, 90),
        "diagnosis": random.choice(_DIAGNOSES),
        "grid_x": round(gx, 2),
        "grid_y": round(gy, 2),
        "last_event_explanation": explanation,
    }


def _doctor(d_idx: int, tick: int) -> dict:
    """Generate a doctor dict with grid position inside their ward zone."""
    x0, x1, y0, y1 = _DOCTOR_ZONES[d_idx]
    n_patients = random.randint(0, 3)
    return {
        "id": d_idx + 1,
        "name": _DOCTOR_NAMES[d_idx],
        "assigned_patient_ids": list(range(d_idx * 3 + 1, d_idx * 3 + 1 + n_patients)),
        "capacity": 3,
        "workload": ["light", "moderate", "heavy", "overwhelmed"][n_patients],
        "specialty": _DOCTOR_SPECIALTIES[d_idx],
        "grid_x": round(random.uniform(x0, x1), 2),
        "grid_y": round(random.uniform(y0, y1), 2),
        "is_available": n_patients < 3,
        "decisions_made": tick * (d_idx + 1),
    }


def generate_fake_state(tick: int) -> dict:
    """
    Returns a complete, valid SimulationState dict matching data-contracts.md §2.

    Scenario timeline:
      ticks  1-29 → "normal"  (light load)
      ticks 30-49 → "surge"   (heavy load, ICU fills)
      ticks 50+   → "shortage" (staff shortage + surge load)
    """
    if tick < 30:
        scenario = "normal"
        n_patients = tick % 10 + 3          # 3-12 patients
        icu_occ = min(100.0, tick * 2.0)    # slowly fills
        gen_occ = min(100.0, 30.0 + tick * 1.5)
    elif tick < 50:
        scenario = "surge"
        n_patients = 10 + tick % 8           # 10-17 patients
        icu_occ = min(100.0, 40.0 + (tick - 30) * 3.0)
        gen_occ = min(100.0, 60.0 + (tick - 30) * 2.0)
    else:
        scenario = "shortage"
        n_patients = 12 + tick % 6           # 12-17 patients
        icu_occ = min(100.0, 80.0 + (tick - 50) * 1.0)
        gen_occ = min(100.0, 85.0 + (tick - 50) * 0.5)

    patients = [_patient(i, tick, scenario) for i in range(1, n_patients + 1)]
    doctors = [_doctor(d, tick) for d in range(4)]

    # Beds: list a subset for visual rendering
    beds = []
    bed_id = 1
    for row in range(4):
        for col in range(5):
            occupied_by = None
            if gen_occ > 0 and random.random() < gen_occ / 100.0:
                # Pick a random patient id from general ward patients
                gw_patients = [p["id"] for p in patients if p["location"] == "general_ward"]
                if gw_patients:
                    occupied_by = random.choice(gw_patients)
            beds.append({
                "id": bed_id,
                "ward": "general_ward",
                "occupied_by_patient_id": occupied_by,
                "grid_x": round(1.0 + col * 2.0, 1),
                "grid_y": round(7.0 + row * 1.5, 1),
            })
            bed_id += 1

    icu_positions = [(13.0, 7.0), (15.0, 7.0), (17.0, 7.0), (13.0, 9.5), (15.0, 9.5)]
    icu_patients = [p["id"] for p in patients if p["location"] == "icu"]
    for pos_x, pos_y in icu_positions:
        occupied_by = None
        if icu_patients and random.random() < icu_occ / 100.0:
            occupied_by = random.choice(icu_patients)
        beds.append({
            "id": bed_id,
            "ward": "icu",
            "occupied_by_patient_id": occupied_by,
            "grid_x": pos_x,
            "grid_y": pos_y,
        })
        bed_id += 1

    waiting_count = sum(1 for p in patients if p["location"] == "waiting")
    gen_count = round(gen_occ / 5)
    icu_count = round(icu_occ / 20)

    wards = {
        "waiting": {
            "name": "waiting",
            "capacity": 50,
            "occupied": waiting_count,
            "occupancy_pct": round(waiting_count * 2.0, 1),
            "is_full": waiting_count >= 50,
        },
        "general_ward": {
            "name": "general_ward",
            "capacity": 20,
            "occupied": min(20, gen_count),
            "occupancy_pct": round(gen_occ, 1),
            "is_full": gen_occ >= 100.0,
        },
        "icu": {
            "name": "icu",
            "capacity": 5,
            "occupied": min(5, icu_count),
            "occupancy_pct": round(icu_occ, 1),
            "is_full": icu_occ >= 100.0,
        },
        "discharged": {
            "name": "discharged",
            "capacity": 999,
            "occupied": tick // 2,
            "occupancy_pct": 0.0,
            "is_full": False,
        },
    }

    metrics = {
        "tick": tick,
        "simulated_hour": tick,
        "total_patients_arrived": tick + 3,
        "total_patients_discharged": tick // 2,
        "avg_wait_time_ticks": round(2.5 + random.uniform(-0.5, 1.5), 2),
        "avg_treatment_time_ticks": round(6.0 + random.uniform(-1.0, 2.0), 2),
        "current_queue_length": waiting_count,
        "general_ward_occupancy_pct": round(gen_occ, 2),
        "icu_occupancy_pct": round(icu_occ, 2),
        "doctor_utilisation_pct": round(
            min(100.0, 40.0 + (tick * 1.2 if scenario == "surge" else tick * 0.8) % 60.0), 2
        ),
        "throughput_last_10_ticks": random.randint(2, 8),
        "critical_patients_waiting": sum(
            1 for p in patients
            if p["location"] == "waiting" and p["severity"] == "critical"
        ),
    }

    # Events: doctor decision every 3rd tick
    events = []
    if tick % 3 == 0:
        doc = random.choice(doctors)
        patient = random.choice(patients) if patients else None
        if patient:
            events.append({
                "tick": tick,
                "event_type": "doctor_decision",
                "entity_id": doc["id"],
                "entity_type": "doctor",
                "raw_description": (
                    f"{doc['name']} assigned to Patient #{patient['id']}"
                ),
                "llm_explanation": (
                    f"{doc['name']} prioritised Patient #{patient['id']} "
                    f"({patient['diagnosis']}, {patient['severity']}) at tick {tick}. "
                    f"ICU occupancy is {round(icu_occ)}% — "
                    + (
                        "immediate intervention needed."
                        if patient["severity"] == "critical"
                        else "treatment can proceed in general ward."
                    )
                ),
                "severity": "critical" if patient["severity"] == "critical" else "info",
            })

    return {
        "type": "sim_state",
        "tick": tick,
        "timestamp": round(time.time(), 3),
        "scenario": scenario,
        "is_running": True,
        "patients": patients,
        "doctors": doctors,
        "beds": beds,
        "wards": wards,
        "metrics": metrics,
        "events": events,
    }


# ─── WebSocket server ─────────────────────────────────────────────────────────

_connected: set[websockets.server.WebSocketServerProtocol] = set()


async def handler(websocket) -> None:
    """
    Registers the client, drains any incoming messages (commands are ignored
    in the standalone mock), and de-registers on disconnect.
    """
    _connected.add(websocket)
    try:
        async for _ in websocket:
            pass  # discard incoming — mock server doesn't process commands
    except Exception:
        pass
    finally:
        _connected.discard(websocket)


async def broadcast_loop() -> None:
    """Broadcasts a new SimulationState to every connected client each second."""
    tick = 0
    while True:
        tick += 1
        payload = json.dumps(generate_fake_state(tick))
        dead: set = set()
        for ws in set(_connected):
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
        _connected.difference_update(dead)
        await asyncio.sleep(1.0)


async def main() -> None:
    print("Mock WS server running on  ws://localhost:8000/ws")
    print("Broadcasts SimulationState every 1 second.")
    print("Press Ctrl+C to stop.\n")

    async with websockets.serve(handler, "localhost", 8000):
        await broadcast_loop()


if __name__ == "__main__":
    asyncio.run(main())

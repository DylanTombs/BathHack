#!/usr/bin/env python3
"""
Mock WebSocket server for Agent 4 frontend development.
Streams simulated hospital state every second.
Run: python mock_ws_server.py
"""
import asyncio
import json
import random
import time
import math
import websockets

# Grid layout constants
GRID_W, GRID_H = 20, 15

# Ward zone boundaries (x_start, y_start, x_end, y_end)
WARD_ZONES = {
    "waiting":      (0, 0, 8, 6),
    "general_ward": (0, 6, 12, 13),
    "icu":          (12, 6, 20, 13),
    "discharged":   (8, 0, 20, 6),
}

def rand_pos_in_ward(ward: str) -> tuple[float, float]:
    x0, y0, x1, y1 = WARD_ZONES[ward]
    return (
        round(random.uniform(x0 + 0.3, x1 - 0.7), 1),
        round(random.uniform(y0 + 0.3, y1 - 0.7), 1),
    )

DIAGNOSES = [
    "Chest pain", "Fracture", "Cardiac arrest", "Appendicitis",
    "Stroke", "Pneumonia", "Sepsis", "Head trauma", "Burns",
    "Allergic reaction", "Respiratory distress", "Abdominal pain"
]

DOCTOR_NAMES = ["Dr. Patel", "Dr. Smith", "Dr. Chen", "Dr. Okafor",
                "Dr. Martinez", "Dr. Kim", "Dr. Johnson", "Dr. Lee",
                "Dr. Brown", "Dr. Wilson"]

SPECIALTIES = ["General", "ICU", "Triage", "Surgery", "Emergency"]

SEVERITIES = ["low", "medium", "critical"]
CONDITIONS = ["stable", "worsening", "improving"]
WORKLOADS = ["light", "moderate", "heavy", "overwhelmed"]

EVENT_TYPES = [
    "patient_arrived", "patient_assigned", "patient_escalated",
    "patient_improved", "patient_discharged", "doctor_decision",
]

LLM_EXPLANATIONS = [
    "Dr. Patel prioritised this patient due to critical vitals and ICU capacity constraints.",
    "Patient escalated after 3 consecutive ticks of worsening condition — protocol requires ICU transfer.",
    "Doctor decided to assign this medium-severity case immediately due to fast queue buildup.",
    "Patient improved following treatment — condition stabilised, ready for general ward discharge.",
    "Triage decision: critical patient bypass waiting queue per emergency protocol.",
    None, None, None,  # Most events have no LLM explanation
]

class SimulationState:
    def __init__(self):
        self.tick = 0
        self.is_running = True
        self.scenario = "normal"
        self.next_patient_id = 1
        self.patients: list[dict] = []
        self.doctors: list[dict] = []
        self._init_doctors(4)
        self._spawn_initial_patients(5)

    def _init_doctors(self, count: int):
        for i in range(count):
            ward = "general_ward" if i % 2 == 0 else "icu"
            gx, gy = rand_pos_in_ward(ward)
            self.doctors.append({
                "id": i + 1,
                "name": DOCTOR_NAMES[i % len(DOCTOR_NAMES)],
                "assigned_patient_ids": [],
                "capacity": random.choice([2, 3]),
                "workload": "light",
                "specialty": SPECIALTIES[i % len(SPECIALTIES)],
                "grid_x": gx,
                "grid_y": gy,
                "is_available": True,
                "decisions_made": 0,
            })

    def _spawn_initial_patients(self, count: int):
        for _ in range(count):
            self._spawn_patient()

    def _spawn_patient(self):
        severity = random.choices(SEVERITIES, weights=[50, 35, 15])[0]
        ward = "waiting"
        gx, gy = rand_pos_in_ward(ward)
        self.patients.append({
            "id": self.next_patient_id,
            "name": f"Patient #{self.next_patient_id}",
            "severity": severity,
            "condition": random.choice(CONDITIONS),
            "location": ward,
            "assigned_doctor_id": None,
            "arrived_at_tick": self.tick,
            "treatment_started_tick": None,
            "treatment_duration_ticks": random.randint(3, 12),
            "wait_time_ticks": 0,
            "age": random.randint(18, 90),
            "diagnosis": random.choice(DIAGNOSES),
            "grid_x": gx,
            "grid_y": gy,
            "last_event_explanation": None,
        })
        self.next_patient_id += 1

    def tick_step(self) -> dict:
        if not self.is_running:
            return self._build_state([])

        events = []

        # Arrival: Poisson-ish arrivals
        rate = 2.5 if self.scenario == "surge" else (0.5 if self.scenario == "shortage" else 1.5)
        num_arrivals = max(0, int(random.gauss(rate, 0.5)))
        for _ in range(num_arrivals):
            self._spawn_patient()
            p = self.patients[-1]
            events.append({
                "tick": self.tick,
                "event_type": "patient_arrived",
                "entity_id": p["id"],
                "entity_type": "patient",
                "raw_description": f"{p['name']} arrived ({p['severity']}, {p['diagnosis']})",
                "llm_explanation": None,
                "severity": "critical" if p["severity"] == "critical" else "info",
            })

        # Move doctors around their ward
        num_doctors = 2 if self.scenario == "shortage" else len(self.doctors)
        for i, doc in enumerate(self.doctors[:num_doctors]):
            if random.random() < 0.3:
                ward = "general_ward" if doc["specialty"] != "ICU" else "icu"
                doc["grid_x"], doc["grid_y"] = rand_pos_in_ward(ward)

        # Assign patients to doctors
        waiting = [p for p in self.patients if p["location"] == "waiting" and p["assigned_doctor_id"] is None]
        waiting.sort(key=lambda p: (0 if p["severity"] == "critical" else 1 if p["severity"] == "medium" else 2))
        for doc in self.doctors[:num_doctors]:
            if len(doc["assigned_patient_ids"]) < doc["capacity"] and waiting:
                patient = waiting.pop(0)
                patient["assigned_doctor_id"] = doc["id"]
                patient["treatment_started_tick"] = self.tick
                ward = "icu" if patient["severity"] == "critical" else "general_ward"
                patient["location"] = ward
                patient["grid_x"], patient["grid_y"] = rand_pos_in_ward(ward)
                doc["assigned_patient_ids"].append(patient["id"])
                doc["decisions_made"] += 1
                llm = random.choice(LLM_EXPLANATIONS)
                events.append({
                    "tick": self.tick,
                    "event_type": "doctor_decision",
                    "entity_id": doc["id"],
                    "entity_type": "doctor",
                    "raw_description": f"{doc['name']} assigned to {patient['name']}",
                    "llm_explanation": llm,
                    "severity": "warning" if patient["severity"] == "critical" else "info",
                })

        # Update waiting times
        for p in self.patients:
            if p["location"] == "waiting":
                p["wait_time_ticks"] += 1

        # Simulate treatment progress
        to_discharge = []
        for p in self.patients:
            if p["treatment_started_tick"] is not None:
                elapsed = self.tick - p["treatment_started_tick"]
                if elapsed >= p["treatment_duration_ticks"]:
                    to_discharge.append(p)
                elif elapsed > p["treatment_duration_ticks"] * 0.5:
                    p["condition"] = "improving"
                elif random.random() < 0.05:
                    p["condition"] = "worsening"

        for p in to_discharge:
            p["location"] = "discharged"
            for doc in self.doctors:
                if p["id"] in doc["assigned_patient_ids"]:
                    doc["assigned_patient_ids"].remove(p["id"])
            events.append({
                "tick": self.tick,
                "event_type": "patient_discharged",
                "entity_id": p["id"],
                "entity_type": "patient",
                "raw_description": f"{p['name']} discharged",
                "llm_explanation": None,
                "severity": "info",
            })

        # Remove discharged patients from active list (keep last 10 for history)
        self.patients = [p for p in self.patients if p["location"] != "discharged"]

        # Update doctor workloads
        for doc in self.doctors:
            n = len(doc["assigned_patient_ids"])
            cap = doc["capacity"]
            doc["is_available"] = n < cap
            if n == 0:
                doc["workload"] = "light"
            elif n <= cap * 0.5:
                doc["workload"] = "moderate"
            elif n < cap:
                doc["workload"] = "heavy"
            else:
                doc["workload"] = "overwhelmed"

        self.tick += 1
        return self._build_state(events)

    def _build_state(self, events: list) -> dict:
        active = [p for p in self.patients if p["location"] != "discharged"]
        waiting_count = sum(1 for p in active if p["location"] == "waiting")
        general_count = sum(1 for p in active if p["location"] == "general_ward")
        icu_count = sum(1 for p in active if p["location"] == "icu")
        critical_waiting = sum(1 for p in active if p["location"] == "waiting" and p["severity"] == "critical")
        total_discharged = self.next_patient_id - 1 - len(self.patients)
        doctors_busy = sum(1 for d in self.doctors if not d["is_available"])

        return {
            "type": "sim_state",
            "tick": self.tick,
            "timestamp": time.time(),
            "scenario": self.scenario,
            "is_running": self.is_running,
            "patients": self.patients,
            "doctors": self.doctors,
            "beds": [],
            "wards": {
                "waiting": {
                    "name": "waiting", "capacity": 50,
                    "occupied": waiting_count,
                    "occupancy_pct": waiting_count / 50 * 100,
                    "is_full": waiting_count >= 50,
                },
                "general_ward": {
                    "name": "general_ward", "capacity": 20,
                    "occupied": general_count,
                    "occupancy_pct": general_count / 20 * 100,
                    "is_full": general_count >= 20,
                },
                "icu": {
                    "name": "icu", "capacity": 5,
                    "occupied": icu_count,
                    "occupancy_pct": icu_count / 5 * 100,
                    "is_full": icu_count >= 5,
                },
                "discharged": {
                    "name": "discharged", "capacity": 999,
                    "occupied": total_discharged,
                    "occupancy_pct": 0.0,
                    "is_full": False,
                },
            },
            "metrics": {
                "tick": self.tick,
                "simulated_hour": self.tick,
                "total_patients_arrived": self.next_patient_id - 1,
                "total_patients_discharged": max(0, total_discharged),
                "avg_wait_time_ticks": sum(p["wait_time_ticks"] for p in active) / max(1, len(active)),
                "avg_treatment_time_ticks": 6.5,
                "current_queue_length": waiting_count,
                "general_ward_occupancy_pct": min(100, general_count / 20 * 100),
                "icu_occupancy_pct": min(100, icu_count / 5 * 100),
                "doctor_utilisation_pct": doctors_busy / max(1, len(self.doctors)) * 100,
                "throughput_last_10_ticks": max(0, int(random.gauss(3, 1))),
                "critical_patients_waiting": critical_waiting,
            },
            "events": events,
        }

    def handle_command(self, msg: dict) -> dict | None:
        cmd = msg.get("command")
        if cmd == "start":
            self.is_running = True
        elif cmd == "pause":
            self.is_running = False
        elif cmd == "reset":
            self.__init__()
        elif cmd == "trigger_surge":
            self.scenario = "surge"
        elif cmd == "trigger_shortage":
            self.scenario = "shortage"
        elif cmd == "trigger_recovery":
            self.scenario = "normal"
        elif cmd in ("explain_patient", "explain_doctor"):
            target_id = msg.get("target_id", 0)
            entity_type = "patient" if cmd == "explain_patient" else "doctor"
            return {
                "type": "explanation",
                "target_id": target_id,
                "target_type": entity_type,
                "explanation": f"[Mock LLM] This {entity_type} (ID #{target_id}) is being managed according to triage protocols. "
                               f"At tick {self.tick}, the system assessed their severity and condition to determine optimal care pathway. "
                               f"The decision was made based on current ward capacity, doctor availability, and patient acuity score.",
                "tick": self.tick,
            }
        elif cmd == "update_config":
            config = msg.get("config", {})
            if "num_doctors" in config:
                target = int(config["num_doctors"])
                current = len(self.doctors)
                if target > current:
                    for i in range(target - current):
                        idx = current + i
                        ward = "general_ward"
                        gx, gy = rand_pos_in_ward(ward)
                        self.doctors.append({
                            "id": idx + 1,
                            "name": DOCTOR_NAMES[idx % len(DOCTOR_NAMES)],
                            "assigned_patient_ids": [],
                            "capacity": 3,
                            "workload": "light",
                            "specialty": "General",
                            "grid_x": gx,
                            "grid_y": gy,
                            "is_available": True,
                            "decisions_made": 0,
                        })
                elif target < current:
                    self.doctors = self.doctors[:target]
        return None


CLIENTS: set = set()

async def handler(websocket):
    CLIENTS.add(websocket)
    sim = SimulationState()
    print(f"[WS] Client connected: {websocket.remote_address}")
    try:
        async def send_loop():
            while True:
                state = sim.tick_step()
                await websocket.send(json.dumps(state))
                await asyncio.sleep(1.0)

        send_task = asyncio.create_task(send_loop())

        async for raw_msg in websocket:
            try:
                msg = json.loads(raw_msg)
                response = sim.handle_command(msg)
                if response:
                    await websocket.send(json.dumps(response))
            except json.JSONDecodeError:
                pass

        send_task.cancel()
    except websockets.exceptions.ConnectionClosed:
        print(f"[WS] Client disconnected")
    finally:
        CLIENTS.discard(websocket)


async def main():
    print("[WS] Mock hospital WebSocket server starting on ws://localhost:8000/ws")
    async with websockets.serve(handler, "localhost", 8000, path="/ws"):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())

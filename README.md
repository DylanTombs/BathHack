<div align="center">

# 🏥 Hospital AI Simulation

### *Every icon on this map is an AI agent making real decisions in real time.*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Claude](https://img.shields.io/badge/Powered%20by-Claude%20AI-D97706?style=for-the-badge&logo=anthropic&logoColor=white)](https://anthropic.com)

<br/>

> A real-time hospital simulation where patients and doctors are **LLM-backed AI agents**, hospital resources are constrained, and a live visual map shows the system under pressure. Trigger a mass casualty event, watch the ICU fill up, and ask any doctor to explain their triage decision — in plain English, in real time.

<br/>

[**Live Demo**](#-quick-start) · [**How It Works**](#-how-it-works) · [**API Docs**](#-api-reference)

</div>

---

## ✨ What Makes This Cool

| | |
|---|---|
| 🤖 **AI Agents** | Every patient and doctor is a live agent. Doctors call Claude when deciding who to treat next — and show their reasoning. |
| 🗺️ **Live Map** | Watch agents move between Waiting Room, General Ward, and ICU zones in real time over WebSocket. |
| 🧠 **Explainable AI** | Click any doctor or patient to get an on-demand LLM explanation of their current situation and last decision. |
| 📊 **Live Metrics** | Occupancy, queue depth, and throughput charts update every tick. Seed from history on page load. |
| 🎛️ **Full Control** | Adjust arrival rate, tick speed, severity level, doctor count, and bed count while the simulation is running — no restart needed. |
| 🚨 **Stress Scenarios** | Trigger a **Mass Casualty Surge** or **Staff Shortage** with one click and watch the cascade unfold. |

---

## 🎬 Demo Walkthrough

```
1. Open http://localhost:5173 — see a calm hospital, a few patients in the waiting area
2. Hit 🚨 Surge   →  patient flood, ICU fills, queue backs up
3. Doctors start making LLM-driven triage decisions — confidence % shown live
4. Click any doctor  →  see their last decision + "🤖 Get AI Summary"
5. Hit 👨‍⚕️ Shortage  →  half the staff disappears, watch the cascade
6. Charts spike: occupancy ↑  queue ↑  throughput ↓
7. Hit ✅ Normal  →  observe the recovery
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Browser                            │
│  React + Zustand + Recharts + Tailwind CSS              │
│  ┌──────────┐ ┌────────────┐ ┌──────────────────────┐   │
│  │ Hospital │ │   Charts   │ │  Entity Detail Panel  │   │
│  │   Map    │ │ (3 types)  │ │  + AI Explanation     │   │
│  └──────────┘ └────────────┘ └──────────────────────┘   │
└────────────────────────┬────────────────────────────────┘
                    WebSocket (JSON)
┌────────────────────────▼────────────────────────────────┐
│                   FastAPI Backend                        │
│  ┌──────────────────┐   ┌──────────────────────────┐    │
│  │ Simulation Engine│──▶│     LLM Layer (Claude)   │    │
│  │ patients doctors │   │  triage · explain · audit │   │
│  │ hospital queues  │   └──────────────────────────┘    │
│  └──────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
```

The simulation engine runs a tick loop (configurable speed). Each tick:
1. New patients arrive stochastically
2. Doctors evaluate their queue, optionally calling Claude for triage
3. Patients move between wards based on severity and bed availability
4. `SimulationState` broadcasts over WebSocket to all connected clients

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- Anthropic API key *(LLM falls back to rule-based logic without one)*

### 1. Clone & configure

```bash
git clone https://github.com/DylanTombs/BathHack.git
cd BathHack
cp .env.example backend/.env
# Open backend/.env and set ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

> API running at **http://localhost:8000** · Swagger docs at **http://localhost:8000/docs**

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

> Open **http://localhost:5173** 🎉

---

## ⚙️ Configuration

All settings live in `backend/.env` (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Your Anthropic key; omit to use rule-based fallback |
| `LLM_MODEL` | `claude-haiku-4-5-20251001` | Model for triage & explanations |
| `TICK_INTERVAL_SECONDS` | `1.0` | Real-time seconds per simulation tick |
| `MAX_BEDS_GENERAL` | `20` | General ward capacity |
| `MAX_BEDS_ICU` | `5` | ICU capacity |
| `INITIAL_DOCTORS` | `4` | Doctors on duty at startup |
| `ARRIVAL_RATE_PER_TICK` | `1.5` | Mean new patients per tick |
| `LOG_LEVEL` | `INFO` | Server log verbosity |

Everything except `ANTHROPIC_API_KEY` can also be changed live via the frontend control panel.

---

## 🌐 API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Liveness check — engine state + active WS connections |
| `GET` | `/api/config` | Current simulation configuration |
| `GET` | `/api/metrics/history` | Last 100 ticks of metrics (seeds charts on page load) |
| `POST` | `/api/scenario/surge` | Trigger mass casualty event |
| `POST` | `/api/scenario/shortage` | Trigger staff shortage |
| `POST` | `/api/scenario/recovery` | Return to normal |

### WebSocket — `ws://localhost:8000/ws`

**Server → Client** (every tick): full `SimulationState` — patients, doctors, ward occupancy, events, metrics.

**Client → Server** (`TriggerCommand`): `start` · `pause` · `reset` · `update_config` · `add_doctor` · `remove_doctor` · `add_bed` · `remove_bed` · `explain_entity`

---

## 📂 Project Structure

```
BathHack/
├── backend/
│   ├── simulation/        # Core engine — patients, doctors, hospital, queues, metrics
│   ├── llm/               # Anthropic client, triage triggers, explainer service
│   ├── api/               # FastAPI app, WebSocket manager, REST routes, serializers
│   ├── config.py          # Pydantic settings loaded from .env
│   └── requirements.txt
└── frontend/
    └── src/
        ├── components/
        │   ├── map/       # HospitalMap, PatientIcon, DoctorIcon, WardZone
        │   ├── charts/    # OccupancyChart, QueueChart, ThroughputChart
        │   ├── controls/  # ControlPanel (sliders, scenario buttons)
        │   ├── layout/    # EntityDetailPanel, MetricsBanner, AISummary
        │   └── event-log/ # EventLog, EventItem
        ├── hooks/         # useWebSocket
        ├── store/         # Zustand stores (simulation state + UI state)
        └── types/         # Shared TypeScript types
```

---

## 🛠️ Tech Stack

<div align="center">

| Backend | Frontend | AI |
|---------|----------|----|
| Python 3.11 | React 19 | Claude Haiku |
| FastAPI | TypeScript 5.9 | Anthropic SDK |
| asyncio + WebSockets | Vite 8 | |
| Uvicorn | Tailwind CSS v4 | |
| python-dotenv | Zustand 5 | |
| | Recharts 3 | |
| | Framer Motion 12 | |

</div>

---

## 📄 License

[MIT](LICENSE)

---

<div align="center">

Built with ❤️ at **BathHack**

</div>

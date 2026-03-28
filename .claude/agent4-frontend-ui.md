# Agent 4 — Frontend React UI

**Branch:** `feature/frontend-ui`
**Owns:** `frontend/`
**Depends on:** Data contracts only. Connect to mock WebSocket server from Agent 3.
**Progress file:** `.claude/progress-agent4.md`

---

## Mission

Build a real-time interactive hospital map UI in React. The simulation state streams in over WebSocket every second. The UI must:
1. Render a live hospital floorplan with animated patient/doctor agents
2. Show per-agent detail on hover/click
3. Display live charts: occupancy, queue length, throughput
4. Show an event log with LLM-generated explanations
5. Provide scenario controls (surge, shortage, config sliders)
6. Request on-demand entity explanations from the backend

This is the **demo face** of the project — make it look impressive.

---

## Tech Stack

```
React 18 + TypeScript
Vite
Zustand (state management)
Recharts (charts)
Framer Motion (animations)
Tailwind CSS (styling)
WebSocket (native browser API)
```

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install zustand recharts framer-motion
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

---

## File Structure

```
frontend/src/
├── types/
│   └── simulation.ts        # TypeScript types from data-contracts.md §5
├── store/
│   ├── simulationStore.ts   # Zustand store for sim state
│   └── uiStore.ts           # UI state (selected entity, panel open, etc.)
├── hooks/
│   ├── useWebSocket.ts      # WebSocket connection + reconnect
│   └── useAnimatedPositions.ts  # Smooth position interpolation
├── components/
│   ├── App.tsx
│   ├── layout/
│   │   ├── Layout.tsx
│   │   ├── LeftPanel.tsx    # Metrics + charts
│   │   └── RightPanel.tsx   # Event log + entity detail
│   ├── map/
│   │   ├── HospitalMap.tsx  # Main canvas/SVG container
│   │   ├── WardZone.tsx     # Renders a named zone (waiting/icu/etc)
│   │   ├── PatientIcon.tsx  # Animated patient dot
│   │   ├── DoctorIcon.tsx   # Animated doctor icon
│   │   ├── BedIcon.tsx      # Static bed marker
│   │   └── Tooltip.tsx      # Hover tooltip
│   ├── charts/
│   │   ├── OccupancyChart.tsx
│   │   ├── QueueChart.tsx
│   │   └── ThroughputChart.tsx
│   ├── controls/
│   │   ├── ControlPanel.tsx
│   │   ├── ScenarioButtons.tsx
│   │   └── ConfigSliders.tsx
│   └── event-log/
│       ├── EventLog.tsx
│       └── EventItem.tsx
└── main.tsx
```

---

## `types/simulation.ts`

Copy verbatim from `data-contracts.md §5`.

---

## `store/simulationStore.ts`

```typescript
import { create } from 'zustand';
import type {
  SimulationState, Patient, Doctor, Metrics,
  SimEvent, ScenarioConfig, WardName, WardState
} from '../types/simulation';

interface MetricsHistoryPoint {
  tick: number;
  general_ward_occupancy_pct: number;
  icu_occupancy_pct: number;
  current_queue_length: number;
  throughput_last_10_ticks: number;
  critical_patients_waiting: number;
  doctor_utilisation_pct: number;
}

interface SimulationStore {
  // Core state
  tick: number;
  isRunning: boolean;
  scenario: string;
  patients: Patient[];
  doctors: Doctor[];
  metrics: Metrics | null;
  wards: Record<WardName, WardState>;
  events: SimEvent[];

  // History for charts (last 100 ticks)
  metricsHistory: MetricsHistoryPoint[];

  // WebSocket status
  connected: boolean;

  // Actions
  applyState: (state: SimulationState) => void;
  appendEvents: (events: SimEvent[]) => void;
  setConnected: (v: boolean) => void;
  seedHistory: (history: MetricsHistoryPoint[]) => void;
}

export const useSimulationStore = create<SimulationStore>((set, get) => ({
  tick: 0,
  isRunning: false,
  scenario: 'normal',
  patients: [],
  doctors: [],
  metrics: null,
  wards: {} as Record<WardName, WardState>,
  events: [],
  metricsHistory: [],
  connected: false,

  applyState: (state: SimulationState) => {
    set({
      tick: state.tick,
      isRunning: state.is_running,
      scenario: state.scenario,
      patients: state.patients,
      doctors: state.doctors,
      metrics: state.metrics,
      wards: state.wards,
    });
    // Append new events, keep last 50
    const prev = get().events;
    const combined = [...prev, ...state.events].slice(-50);
    set({ events: combined });
    // Append to history
    if (state.metrics) {
      const { metrics } = state;
      const point: MetricsHistoryPoint = {
        tick: metrics.tick,
        general_ward_occupancy_pct: metrics.general_ward_occupancy_pct,
        icu_occupancy_pct: metrics.icu_occupancy_pct,
        current_queue_length: metrics.current_queue_length,
        throughput_last_10_ticks: metrics.throughput_last_10_ticks,
        critical_patients_waiting: metrics.critical_patients_waiting,
        doctor_utilisation_pct: metrics.doctor_utilisation_pct,
      };
      const hist = [...get().metricsHistory, point].slice(-100);
      set({ metricsHistory: hist });
    }
  },

  appendEvents: (events) => {
    const prev = get().events;
    set({ events: [...prev, ...events].slice(-50) });
  },

  setConnected: (v) => set({ connected: v }),
  seedHistory: (history) => set({ metricsHistory: history }),
}));
```

---

## `store/uiStore.ts`

```typescript
import { create } from 'zustand';

interface UIStore {
  selectedEntityId: number | null;
  selectedEntityType: 'patient' | 'doctor' | null;
  explanationText: string | null;
  explanationLoading: boolean;
  isPanelOpen: boolean;
  isSurgeActive: boolean;

  selectEntity: (id: number, type: 'patient' | 'doctor') => void;
  clearSelection: () => void;
  setExplanation: (text: string | null) => void;
  setExplanationLoading: (v: boolean) => void;
  setSurgeActive: (v: boolean) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  selectedEntityId: null,
  selectedEntityType: null,
  explanationText: null,
  explanationLoading: false,
  isPanelOpen: false,
  isSurgeActive: false,

  selectEntity: (id, type) => set({
    selectedEntityId: id,
    selectedEntityType: type,
    isPanelOpen: true,
    explanationText: null,
  }),
  clearSelection: () => set({
    selectedEntityId: null,
    selectedEntityType: null,
    isPanelOpen: false,
    explanationText: null,
  }),
  setExplanation: (text) => set({ explanationText: text, explanationLoading: false }),
  setExplanationLoading: (v) => set({ explanationLoading: v }),
  setSurgeActive: (v) => set({ isSurgeActive: v }),
}));
```

---

## `hooks/useWebSocket.ts`

```typescript
import { useEffect, useRef, useCallback } from 'react';
import { useSimulationStore } from '../store/simulationStore';
import { useUIStore } from '../store/uiStore';
import type { SimulationState, ExplanationResponse, ScenarioConfig } from '../types/simulation';

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';
const RECONNECT_DELAY_MS = 2000;

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { applyState, setConnected, seedHistory } = useSimulationStore();
  const { setExplanation, setExplanationLoading } = useUIStore();

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    ws.current = new WebSocket(WS_URL);

    ws.current.onopen = () => {
      setConnected(true);
      console.log('[WS] Connected');
    };

    ws.current.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'sim_state') {
          applyState(msg as SimulationState);
        } else if (msg.type === 'explanation') {
          setExplanation((msg as ExplanationResponse).explanation);
        } else if (msg.type === 'metrics_history') {
          seedHistory(msg.snapshots);
        }
      } catch (e) {
        console.error('[WS] Parse error', e);
      }
    };

    ws.current.onclose = () => {
      setConnected(false);
      console.log('[WS] Disconnected — reconnecting...');
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.current.onerror = (err) => {
      console.error('[WS] Error', err);
      ws.current?.close();
    };
  }, [applyState, setConnected, seedHistory, setExplanation]);

  useEffect(() => {
    connect();
    return () => {
      reconnectTimer.current && clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  const sendCommand = useCallback((payload: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    }
  }, []);

  const requestExplanation = useCallback((entityType: 'patient' | 'doctor', id: number) => {
    setExplanationLoading(true);
    sendCommand({
      command: entityType === 'patient' ? 'explain_patient' : 'explain_doctor',
      target_id: id,
    });
  }, [sendCommand, setExplanationLoading]);

  const triggerSurge = useCallback(() => sendCommand({ command: 'trigger_surge' }), [sendCommand]);
  const triggerShortage = useCallback(() => sendCommand({ command: 'trigger_shortage' }), [sendCommand]);
  const triggerRecovery = useCallback(() => sendCommand({ command: 'trigger_recovery' }), [sendCommand]);
  const startSim = useCallback(() => sendCommand({ command: 'start' }), [sendCommand]);
  const pauseSim = useCallback(() => sendCommand({ command: 'pause' }), [sendCommand]);
  const resetSim = useCallback(() => sendCommand({ command: 'reset' }), [sendCommand]);

  const updateConfig = useCallback((config: Partial<ScenarioConfig>) => {
    sendCommand({ command: 'update_config', config });
  }, [sendCommand]);

  return {
    triggerSurge,
    triggerShortage,
    triggerRecovery,
    startSim,
    pauseSim,
    resetSim,
    updateConfig,
    requestExplanation,
  };
}
```

---

## `components/map/HospitalMap.tsx`

The centrepiece component. Uses SVG so animations, tooltips, and click handlers are simple.

```tsx
import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';
import { WardZone } from './WardZone';
import { PatientIcon } from './PatientIcon';
import { DoctorIcon } from './DoctorIcon';
import { useWebSocket } from '../../hooks/useWebSocket';

// Grid: 20 cols × 15 rows. Each cell = CELL_SIZE px
const CELL_SIZE = 44;
const GRID_W = 20;
const GRID_H = 15;
const SVG_W = GRID_W * CELL_SIZE;  // 880px
const SVG_H = GRID_H * CELL_SIZE;  // 660px

// Ward zones (from data-contracts.md §6)
const WARDS = [
  { name: 'waiting',      label: 'Waiting Area',   x: 0,  y: 0,  w: 8,  h: 6,  color: '#e0f2fe' },
  { name: 'general_ward', label: 'General Ward',    x: 0,  y: 6,  w: 12, h: 7,  color: '#dcfce7' },
  { name: 'icu',          label: 'ICU',             x: 12, y: 6,  w: 8,  h: 7,  color: '#fef3c7' },
  { name: 'discharged',   label: 'Discharge',       x: 0,  y: 13, w: 20, h: 2,  color: '#f1f5f9' },
] as const;

export const HospitalMap: React.FC = () => {
  const { patients, doctors } = useSimulationStore();
  const { selectEntity, selectedEntityId } = useUIStore();
  const { requestExplanation } = useWebSocket();

  return (
    <div className="relative w-full overflow-auto bg-gray-50 rounded-xl border border-gray-200 shadow-inner">
      <svg
        width={SVG_W}
        height={SVG_H}
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        className="block"
      >
        {/* Ward backgrounds */}
        {WARDS.map(zone => (
          <WardZone key={zone.name} zone={zone} cellSize={CELL_SIZE} />
        ))}

        {/* Grid lines (subtle) */}
        <GridLines w={SVG_W} h={SVG_H} cellSize={CELL_SIZE} />

        {/* Beds */}
        {/* Agent 1 provides bed positions — render as small rect */}

        {/* Patients */}
        {patients.filter(p => p.location !== 'discharged').map(patient => (
          <PatientIcon
            key={patient.id}
            patient={patient}
            cellSize={CELL_SIZE}
            isSelected={selectedEntityId === patient.id}
            onClick={() => {
              selectEntity(patient.id, 'patient');
              requestExplanation('patient', patient.id);
            }}
          />
        ))}

        {/* Doctors */}
        {doctors.map(doctor => (
          <DoctorIcon
            key={doctor.id}
            doctor={doctor}
            cellSize={CELL_SIZE}
            isSelected={selectedEntityId === doctor.id}
            onClick={() => {
              selectEntity(doctor.id, 'doctor');
              requestExplanation('doctor', doctor.id);
            }}
          />
        ))}
      </svg>
    </div>
  );
};

const GridLines: React.FC<{ w: number; h: number; cellSize: number }> = ({ w, h, cellSize }) => (
  <g opacity={0.08}>
    {Array.from({ length: Math.floor(w / cellSize) }).map((_, i) => (
      <line key={`v${i}`} x1={i * cellSize} y1={0} x2={i * cellSize} y2={h} stroke="#94a3b8" />
    ))}
    {Array.from({ length: Math.floor(h / cellSize) }).map((_, i) => (
      <line key={`h${i}`} x1={0} y1={i * cellSize} x2={w} y2={i * cellSize} stroke="#94a3b8" />
    ))}
  </g>
);
```

---

## `components/map/PatientIcon.tsx`

```tsx
import React from 'react';
import { motion } from 'framer-motion';
import type { Patient, Severity } from '../../types/simulation';

const SEVERITY_COLOR: Record<Severity, string> = {
  low: '#22c55e',       // green
  medium: '#f59e0b',    // amber
  critical: '#ef4444',  // red
};

const CONDITION_STROKE: Record<string, string> = {
  stable: '#6b7280',
  improving: '#22c55e',
  worsening: '#ef4444',
};

interface Props {
  patient: Patient;
  cellSize: number;
  isSelected: boolean;
  onClick: () => void;
}

export const PatientIcon: React.FC<Props> = ({ patient, cellSize, isSelected, onClick }) => {
  const cx = (patient.grid_x + 0.5) * cellSize;
  const cy = (patient.grid_y + 0.5) * cellSize;
  const r = isSelected ? 12 : 9;

  return (
    <motion.g
      key={patient.id}
      animate={{ cx, cy }}          // Framer Motion animates SVG transforms
      initial={false}
      transition={{ type: 'spring', stiffness: 120, damping: 20 }}
      onClick={onClick}
      style={{ cursor: 'pointer' }}
    >
      {/* Pulsing ring for critical patients */}
      {patient.severity === 'critical' && (
        <motion.circle
          cx={cx} cy={cy}
          r={14}
          fill="none"
          stroke="#ef4444"
          strokeWidth={2}
          animate={{ opacity: [1, 0, 1], r: [14, 18, 14] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        />
      )}
      {/* Body */}
      <circle
        cx={cx} cy={cy} r={r}
        fill={SEVERITY_COLOR[patient.severity]}
        stroke={isSelected ? '#1d4ed8' : CONDITION_STROKE[patient.condition]}
        strokeWidth={isSelected ? 3 : 2}
        opacity={0.9}
      />
      {/* Person icon (P) */}
      <text
        x={cx} y={cy + 4}
        textAnchor="middle"
        fontSize={10}
        fontWeight="bold"
        fill="white"
      >
        P
      </text>
    </motion.g>
  );
};
```

---

## `components/map/DoctorIcon.tsx`

```tsx
import React from 'react';
import { motion } from 'framer-motion';
import type { Doctor, WorkloadLevel } from '../../types/simulation';

const WORKLOAD_COLOR: Record<WorkloadLevel, string> = {
  light: '#3b82f6',
  moderate: '#8b5cf6',
  heavy: '#f97316',
  overwhelmed: '#dc2626',
};

interface Props {
  doctor: Doctor;
  cellSize: number;
  isSelected: boolean;
  onClick: () => void;
}

export const DoctorIcon: React.FC<Props> = ({ doctor, cellSize, isSelected, onClick }) => {
  const cx = (doctor.grid_x + 0.5) * cellSize;
  const cy = (doctor.grid_y + 0.5) * cellSize;

  return (
    <motion.g
      animate={{ x: cx - 12, y: cy - 14 }}
      initial={false}
      transition={{ type: 'spring', stiffness: 100, damping: 18 }}
      onClick={onClick}
      style={{ cursor: 'pointer' }}
    >
      {/* Diamond shape for doctors */}
      <rect
        x={0} y={0} width={24} height={24}
        rx={4}
        fill={WORKLOAD_COLOR[doctor.workload]}
        stroke={isSelected ? '#1d4ed8' : 'white'}
        strokeWidth={isSelected ? 3 : 1.5}
        transform="rotate(45 12 12)"
        opacity={0.95}
      />
      <text
        x={12} y={16}
        textAnchor="middle"
        fontSize={9}
        fontWeight="bold"
        fill="white"
      >
        Dr
      </text>
      {/* Workload indicator bar */}
      {doctor.assigned_patient_ids.length > 0 && (
        <g>
          {Array.from({ length: doctor.capacity }).map((_, i) => (
            <rect
              key={i}
              x={i * 7} y={26} width={5} height={3}
              fill={i < doctor.assigned_patient_ids.length ? WORKLOAD_COLOR[doctor.workload] : '#e5e7eb'}
              rx={1}
            />
          ))}
        </g>
      )}
    </motion.g>
  );
};
```

---

## `components/charts/OccupancyChart.tsx`

```tsx
import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useSimulationStore } from '../../store/simulationStore';

export const OccupancyChart: React.FC = () => {
  const { metricsHistory } = useSimulationStore();
  const data = metricsHistory.slice(-60);  // last 60 ticks

  return (
    <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-100">
      <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Ward Occupancy %</h3>
      <ResponsiveContainer width="100%" height={140}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} />
          <Tooltip
            formatter={(val: number) => `${val.toFixed(0)}%`}
            contentStyle={{ fontSize: 11 }}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Area type="monotone" dataKey="general_ward_occupancy_pct" name="General" stroke="#22c55e" fill="#dcfce7" strokeWidth={2} />
          <Area type="monotone" dataKey="icu_occupancy_pct" name="ICU" stroke="#f59e0b" fill="#fef3c7" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
```

---

## `components/controls/ControlPanel.tsx`

```tsx
import React, { useState } from 'react';
import { useWebSocket } from '../../hooks/useWebSocket';
import { useSimulationStore } from '../../store/simulationStore';

export const ControlPanel: React.FC = () => {
  const { isRunning, scenario } = useSimulationStore();
  const { startSim, pauseSim, resetSim, triggerSurge, triggerShortage, triggerRecovery, updateConfig } = useWebSocket();
  const [arrivalRate, setArrivalRate] = useState(1.5);
  const [numDoctors, setNumDoctors] = useState(4);

  const handleConfigChange = (key: string, value: number) => {
    updateConfig({ [key]: value });
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4 shadow-sm">
      {/* Simulation controls */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Simulation</h3>
        <div className="flex gap-2">
          <button
            onClick={isRunning ? pauseSim : startSim}
            className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
              isRunning
                ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                : 'bg-green-100 text-green-700 hover:bg-green-200'
            }`}
          >
            {isRunning ? '⏸ Pause' : '▶ Start'}
          </button>
          <button
            onClick={resetSim}
            className="px-3 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200"
          >
            ↺ Reset
          </button>
        </div>
      </div>

      {/* Scenario buttons */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Scenarios</h3>
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={triggerSurge}
            className="py-2 px-2 rounded-lg text-xs font-medium bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
          >
            🚨 Surge
          </button>
          <button
            onClick={triggerShortage}
            className="py-2 px-2 rounded-lg text-xs font-medium bg-orange-100 text-orange-700 hover:bg-orange-200 transition-colors"
          >
            👨‍⚕️ Shortage
          </button>
          <button
            onClick={triggerRecovery}
            className="py-2 px-2 rounded-lg text-xs font-medium bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors"
          >
            ✅ Normal
          </button>
        </div>
        {scenario !== 'normal' && (
          <div className={`mt-2 text-xs text-center font-medium py-1 rounded ${
            scenario === 'surge' ? 'text-red-600 bg-red-50' : 'text-orange-600 bg-orange-50'
          }`}>
            {scenario === 'surge' ? '🚨 Mass Casualty Event Active' : '⚠️ Staff Shortage Active'}
          </div>
        )}
      </div>

      {/* Config sliders */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Configuration</h3>
        <div className="space-y-3">
          <label className="block">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Arrival Rate</span>
              <span className="font-mono">{arrivalRate.toFixed(1)}/tick</span>
            </div>
            <input
              type="range" min={0.5} max={5} step={0.5}
              value={arrivalRate}
              onChange={e => {
                const v = parseFloat(e.target.value);
                setArrivalRate(v);
                handleConfigChange('arrival_rate_per_tick', v);
              }}
              className="w-full accent-blue-500"
            />
          </label>
          <label className="block">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Doctors</span>
              <span className="font-mono">{numDoctors}</span>
            </div>
            <input
              type="range" min={1} max={10} step={1}
              value={numDoctors}
              onChange={e => {
                const v = parseInt(e.target.value);
                setNumDoctors(v);
                handleConfigChange('num_doctors', v);
              }}
              className="w-full accent-purple-500"
            />
          </label>
        </div>
      </div>
    </div>
  );
};
```

---

## `components/event-log/EventLog.tsx`

```tsx
import React, { useRef, useEffect } from 'react';
import { useSimulationStore } from '../../store/simulationStore';
import { EventItem } from './EventItem';

export const EventLog: React.FC = () => {
  const { events } = useSimulationStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-100">
        <h3 className="text-xs font-semibold text-gray-500 uppercase">Event Log</h3>
      </div>
      <div className="h-64 overflow-y-auto p-2 space-y-1">
        {events.length === 0 ? (
          <p className="text-xs text-gray-400 text-center pt-8">Waiting for events…</p>
        ) : (
          events.map((event, i) => <EventItem key={i} event={event} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
```

---

## `components/event-log/EventItem.tsx`

```tsx
import React, { useState } from 'react';
import type { SimEvent } from '../../types/simulation';

const SEVERITY_STYLE = {
  info: 'border-blue-200 bg-blue-50 text-blue-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
  critical: 'border-red-200 bg-red-50 text-red-800',
};

export const EventItem: React.FC<{ event: SimEvent }> = ({ event }) => {
  const [expanded, setExpanded] = useState(false);
  const hasLLM = !!event.llm_explanation;

  return (
    <div className={`text-xs rounded border px-2 py-1.5 ${SEVERITY_STYLE[event.severity]}`}>
      <div className="flex items-start gap-1">
        <span className="font-mono opacity-60 shrink-0">T{event.tick}</span>
        <span className="flex-1">
          {expanded && hasLLM ? event.llm_explanation : event.raw_description}
        </span>
        {hasLLM && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 font-medium opacity-70 hover:opacity-100 ml-1"
            title="Toggle LLM explanation"
          >
            {expanded ? '▲' : '🤖'}
          </button>
        )}
      </div>
    </div>
  );
};
```

---

## `components/layout/Layout.tsx`

```tsx
import React from 'react';
import { HospitalMap } from '../map/HospitalMap';
import { ControlPanel } from '../controls/ControlPanel';
import { OccupancyChart } from '../charts/OccupancyChart';
import { QueueChart } from '../charts/QueueChart';
import { ThroughputChart } from '../charts/ThroughputChart';
import { EventLog } from '../event-log/EventLog';
import { MetricsBanner } from './MetricsBanner';
import { EntityDetailPanel } from './EntityDetailPanel';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';

export const Layout: React.FC = () => {
  const { connected } = useSimulationStore();
  const { isPanelOpen } = useUIStore();

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-xl">🏥</span>
          <h1 className="text-lg font-bold text-gray-900">Hospital Simulation</h1>
          <span className="text-xs text-gray-400">Agent-Based · LLM-Driven</span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
          <span className="text-xs text-gray-500">{connected ? 'Live' : 'Disconnected'}</span>
        </div>
      </header>

      {/* Metrics banner */}
      <MetricsBanner />

      {/* Main layout: left panel | map | right panel */}
      <div className="flex flex-1 gap-4 p-4 overflow-hidden">
        {/* Left: charts + controls */}
        <div className="w-64 shrink-0 space-y-3 overflow-y-auto">
          <ControlPanel />
          <OccupancyChart />
          <QueueChart />
          <ThroughputChart />
        </div>

        {/* Centre: hospital map */}
        <div className="flex-1 overflow-auto">
          <HospitalMap />
        </div>

        {/* Right: event log + entity detail */}
        <div className="w-72 shrink-0 space-y-3 overflow-y-auto">
          {isPanelOpen && <EntityDetailPanel />}
          <EventLog />
        </div>
      </div>
    </div>
  );
};
```

---

## `vite.config.ts`

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
```

---

## `.env` (frontend)

```
VITE_WS_URL=ws://localhost:8000/ws
```

---

## Visual Design Tokens

```css
/* Tailwind config extends */
colors: {
  severity: {
    low: '#22c55e',
    medium: '#f59e0b',
    critical: '#ef4444',
  },
  workload: {
    light: '#3b82f6',
    moderate: '#8b5cf6',
    heavy: '#f97316',
    overwhelmed: '#dc2626',
  },
  ward: {
    waiting: '#e0f2fe',
    general: '#dcfce7',
    icu: '#fef3c7',
    discharge: '#f1f5f9',
  },
}
```

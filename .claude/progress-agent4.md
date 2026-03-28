# Agent 4 Progress — Frontend React UI

**Branch:** `feature/frontend-ui`
**Spec:** `.claude/agent4-frontend-ui.md`

Update this file as you complete each task. Mark items with:
- `[ ]` — not started
- `[~]` — in progress
- `[x]` — complete
- `[!]` — blocked / needs decision

**WebSocket mock:** Run `python -m api.mock_ws_server` (from Agent 3's branch, or the mock script is self-contained in `backend/api/mock_ws_server.py`). Connect to `ws://localhost:8000/ws`.

---

## Phase 0 — Project Setup
- [ ] `npm create vite@latest frontend -- --template react-ts` in repo root
- [ ] `cd frontend && npm install`
- [ ] Install dependencies:
  ```bash
  npm install zustand recharts framer-motion
  npm install -D tailwindcss postcss autoprefixer @types/node
  npx tailwindcss init -p
  ```
- [ ] Configure `tailwind.config.js` — content paths cover `src/**/*.{ts,tsx}`
- [ ] Add Tailwind directives to `src/index.css`
- [ ] Create `frontend/.env` with `VITE_WS_URL=ws://localhost:8000/ws`
- [ ] Configure `vite.config.ts` with `proxy: { '/api': 'http://localhost:8000' }`
- [ ] Delete boilerplate (App.css, logo, etc.)
- [ ] Verify: `npm run dev` opens blank page at `http://localhost:5173`

**Done when:** `npm run dev` starts with no TypeScript errors, blank white page loads.

---

## Phase 1 — Types
- [ ] Create `frontend/src/types/simulation.ts`
- [ ] Copy all TypeScript types verbatim from `data-contracts.md §5`
- [ ] Verify: `import type { SimulationState } from './types/simulation'` resolves
- [ ] No `any` types — all fields typed

**Done when:** TypeScript compiler accepts all types with `npx tsc --noEmit`.

---

## Phase 2 — Zustand Stores
- [ ] Create `frontend/src/store/simulationStore.ts`
  - [ ] `tick`, `isRunning`, `scenario`, `patients`, `doctors`, `metrics`, `wards` state fields
  - [ ] `metricsHistory: MetricsHistoryPoint[]` (last 100 ticks)
  - [ ] `events: SimEvent[]` (last 50)
  - [ ] `connected: boolean`
  - [ ] `applyState(state: SimulationState)` — updates all fields, appends to history + events
  - [ ] `appendEvents(events)` — append, keep last 50
  - [ ] `setConnected(v)` and `seedHistory(history)`
- [ ] Create `frontend/src/store/uiStore.ts`
  - [ ] `selectedEntityId`, `selectedEntityType`, `explanationText`, `explanationLoading`
  - [ ] `isPanelOpen`, `isSurgeActive`
  - [ ] `selectEntity(id, type)`, `clearSelection()`, `setExplanation(text)`, `setExplanationLoading(v)`

**Done when:** `useSimulationStore.getState().applyState(mockState)` correctly updates all fields. Verified with `console.log` in browser devtools.

---

## Phase 3 — WebSocket Hook
- [ ] Create `frontend/src/hooks/useWebSocket.ts`
- [ ] Connect to `VITE_WS_URL` on mount, reconnect on close (2s delay)
- [ ] `onmessage`: dispatch to store based on `msg.type`:
  - [ ] `sim_state` → `applyState()`
  - [ ] `explanation` → `setExplanation()`
  - [ ] `metrics_history` → `seedHistory()`
- [ ] `setConnected(true/false)` on open/close
- [ ] Exported commands:
  - [ ] `startSim()`, `pauseSim()`, `resetSim()`
  - [ ] `triggerSurge()`, `triggerShortage()`, `triggerRecovery()`
  - [ ] `updateConfig(config: Partial<ScenarioConfig>)`
  - [ ] `requestExplanation(type, id)` — sends command + sets `explanationLoading=true`
- [ ] WebSocket ref correctly cleaned up on unmount (no memory leak)
- [ ] Reconnect timer cleared on unmount

**Done when:** Connect to mock WS server. `useSimulationStore.getState().tick` increments every second in devtools. `connected` is `true`. Disconnect mock server → `connected` becomes `false` → auto-reconnects when server restarts.

---

## Phase 4 — Hospital Map (Static)
- [ ] Create `frontend/src/components/map/WardZone.tsx`
  - [ ] Renders an SVG `<rect>` background for each ward zone
  - [ ] Shows ward label text (top-left corner of zone)
  - [ ] Occupancy badge shows `ward.occupancy_pct.toFixed(0)%` from store
  - [ ] Border colour changes: green < 70%, amber 70-90%, red > 90%
- [ ] Create `frontend/src/components/map/HospitalMap.tsx`
  - [ ] SVG canvas: 880×660px (20×15 grid × 44px cell)
  - [ ] Four ward zones rendered with correct positions (from data-contracts.md §6)
  - [ ] Subtle grid lines rendered
  - [ ] Responsive container — scales to available width

**Done when:** Hospital map renders with 4 clearly delineated zones, labels, and occupancy badges. No patient/doctor icons yet.

---

## Phase 5 — Patient Icons
- [ ] Create `frontend/src/components/map/PatientIcon.tsx`
  - [ ] Circle SVG element positioned at `(grid_x + 0.5) * CELL_SIZE`
  - [ ] Fill colour by severity: green/amber/red
  - [ ] Stroke colour by condition: stable=gray, improving=green, worsening=red
  - [ ] "P" label text inside circle
  - [ ] Selected state: larger radius + blue stroke
  - [ ] Critical patients: pulsing ring animation (framer-motion)
  - [ ] `onClick` handler
- [ ] Wire into `HospitalMap.tsx` — render all patients from store (skip `discharged`)
- [ ] Tooltip on hover: shows `name`, `severity`, `condition`, `diagnosis`, `wait_time_ticks`

**Done when:** With mock WS running, patients appear on map in correct ward zones. Critical patients pulse. Clicking a patient selects it (border changes).

---

## Phase 6 — Doctor Icons
- [ ] Create `frontend/src/components/map/DoctorIcon.tsx`
  - [ ] Diamond/rotated rect SVG element
  - [ ] Fill colour by workload: blue/purple/orange/red
  - [ ] "Dr" label text
  - [ ] Capacity bar: N small rects below icon, filled=assigned, empty=free
  - [ ] Selected state: thick blue border
  - [ ] `onClick` handler
- [ ] Wire into `HospitalMap.tsx`
- [ ] Tooltip on hover: shows `name`, `specialty`, `workload`, `assigned_patient_ids.length/capacity`

**Done when:** 4 doctor icons visible, each showing correct workload colour. Capacity bars reflect assigned patient count.

---

## Phase 7 — Animated Transitions
- [ ] Install / verify `framer-motion` is working
- [ ] `PatientIcon` uses `motion.g` or `motion.circle` with `animate={{ cx, cy }}` (or transforms) to smoothly move when `grid_x`/`grid_y` changes
  - [ ] `transition: { type: 'spring', stiffness: 120, damping: 20 }`
- [ ] `DoctorIcon` similarly animated
- [ ] New patient arrival: fade-in animation (`initial={{ opacity: 0 }}`, `animate={{ opacity: 1 }}`)
- [ ] Patient discharge: fade-out + shrink before removal
- [ ] Test: trigger surge in mock, watch patients flow in and distribute across wards

**Done when:** Patient movements are visually smooth (no instant jumps). New arrivals fade in. Discharged patients fade out.

---

## Phase 8 — Side Panels

### Left Panel — Metrics + Controls
- [ ] Create `frontend/src/components/layout/LeftPanel.tsx`
- [ ] Create `frontend/src/components/controls/ControlPanel.tsx`
  - [ ] Start/Pause button (toggles with `isRunning` state)
  - [ ] Reset button
  - [ ] Surge / Shortage / Recovery buttons with correct colours
  - [ ] Active scenario banner (red for surge, orange for shortage)
  - [ ] Arrival rate slider (0.5 – 5.0, step 0.5) → `updateConfig({ arrival_rate_per_tick: v })`
  - [ ] Doctors slider (1 – 10) → `updateConfig({ num_doctors: v })`
- [ ] Create `frontend/src/components/charts/OccupancyChart.tsx`
  - [ ] `AreaChart` from recharts, two series: general ward + ICU
  - [ ] Last 60 ticks from `metricsHistory`
  - [ ] Y-axis 0–100%
  - [ ] Tooltip shows % values
- [ ] Create `frontend/src/components/charts/QueueChart.tsx`
  - [ ] `LineChart` — queue length + critical patients waiting over last 60 ticks
- [ ] Create `frontend/src/components/charts/ThroughputChart.tsx`
  - [ ] `BarChart` — throughput (discharges per 10 ticks) over time

**Done when:** All three charts update live with data from mock WS. Surge button causes visible spike in ICU chart. Sliders send config commands.

---

## Phase 9 — Right Panel — Event Log + Entity Detail

- [ ] Create `frontend/src/components/event-log/EventItem.tsx`
  - [ ] Shows tick number, raw_description
  - [ ] Border/background colour by severity (blue/amber/red)
  - [ ] If `llm_explanation` present: 🤖 toggle button — click to expand LLM text
- [ ] Create `frontend/src/components/event-log/EventLog.tsx`
  - [ ] Scrollable list of last 50 events
  - [ ] Auto-scrolls to bottom on new event
  - [ ] Empty state message
- [ ] Create `frontend/src/components/layout/EntityDetailPanel.tsx`
  - [ ] Shows when `isPanelOpen` is true
  - [ ] Renders patient or doctor detail based on `selectedEntityType`
  - [ ] Patient detail: name, severity badge, condition, diagnosis, location, wait time, assigned doctor
  - [ ] Doctor detail: name, specialty, workload badge, assigned patients (list names), decisions_made
  - [ ] "Explain (AI)" button → calls `requestExplanation(type, id)`
  - [ ] While loading: spinner
  - [ ] When loaded: explanation text in styled box
  - [ ] Close button → `clearSelection()`

**Done when:** Click a patient icon → detail panel opens with correct data. Click "Explain" → loading spinner appears → explanation text appears (from mock WS or real LLM). Event log populates with events, LLM toggle works.

---

## Phase 10 — Layout Assembly + Metrics Banner

- [ ] Create `frontend/src/components/layout/MetricsBanner.tsx`
  - [ ] Horizontal bar of 6 key metrics:
    - `total_patients_arrived`
    - `total_patients_discharged`
    - `current_queue_length`
    - `icu_occupancy_pct` (with colour indicator)
    - `critical_patients_waiting` (red if > 0)
    - `doctor_utilisation_pct`
  - [ ] Updates live from store
  - [ ] Metrics flash/highlight briefly when value changes significantly
- [ ] Create `frontend/src/components/layout/Layout.tsx`
  - [ ] Three-column layout: left (controls + charts) | centre (map) | right (events + detail)
  - [ ] Header: title + connection status indicator
  - [ ] Metrics banner below header
  - [ ] Mobile: not required (hackathon demo on laptop)
- [ ] Wire everything into `App.tsx` with `useWebSocket()` mounted at app root

**Done when:** Full layout renders correctly. All panels visible. No layout overflow or z-index issues. Header connection dot is green with mock server running.

---

## Phase 11 — Polish and Visual QA

- [ ] Verify colour contrast — all text readable against backgrounds
- [ ] Severity legend somewhere visible on map (low=green, medium=amber, critical=red)
- [ ] Workload legend for doctors (light=blue, moderate=purple, heavy=orange, overwhelmed=red)
- [ ] Ward zone labels clearly visible
- [ ] Charts have titles and axis labels
- [ ] No flicker or jank during rapid state updates
- [ ] `npm run build` completes with 0 TypeScript errors
- [ ] Test in Chrome and Firefox

**Done when:** `npm run build` succeeds. Visual inspection of running demo looks polished. No console errors in browser.

---

## Phase 12 — Final Verification Checklist

- [ ] `npm run dev` starts without errors
- [ ] `npm run build` succeeds with 0 TypeScript errors
- [ ] Connects to `ws://localhost:8000/ws` automatically
- [ ] Reconnects after server restart (within 3 seconds)
- [ ] All patient icons positioned within correct ward zone boundaries
- [ ] Patient movements are animated (spring transitions)
- [ ] Critical patient pulse animation working
- [ ] Surge button → visible increase in patients on map within 5 ticks
- [ ] Event log shows LLM explanations with 🤖 toggle
- [ ] Entity detail panel opens on click, explanation loads
- [ ] Charts show last 60 ticks of data
- [ ] Config sliders immediately send `update_config` command
- [ ] No `any` in TypeScript source

---

## Success Criteria

| Criterion | Signal | Target |
|-----------|--------|--------|
| Live updates | Tick counter increments in UI every second | Must pass |
| Patient icons | Correct zone, severity colour, condition stroke | Must pass |
| Doctor icons | Correct zone, workload colour, capacity bar | Must pass |
| Animations | Patient movements smoothly interpolated | Must pass |
| Critical pulse | Critical-severity patients pulse visually | Must pass |
| Surge visible | Surge trigger causes visible map crowding | Must pass |
| Event log populates | Events appear within 5 ticks of connection | Must pass |
| LLM toggle | Event with `llm_explanation` shows 🤖 toggle that reveals full text | Must pass |
| Entity detail | Click patient → correct name/severity/diagnosis in panel | Must pass |
| Explain button | Clicking explain → explanation text appears (LLM or fallback) | Must pass |
| Charts live | Occupancy chart updates with each tick | Must pass |
| Config sliders | Dragging slider sends WS command within 300ms | Must pass |
| Build clean | `npm run build` zero TypeScript errors | Must pass |
| Reconnect | Auto-reconnects after WS server restart | Must pass |
| Scenario badge | Active scenario shown prominently when surge/shortage active | Nice to have |

---

## Integration Handoff Notes

When connecting to the real backend (post all-branch merge):

1. Verify `VITE_WS_URL=ws://localhost:8000/ws` points to live server
2. Verify event `llm_explanation` fields are populated (they'll be `null` in mock)
3. Verify `explanation` response arrives after clicking "Explain" (timeout = LLM call duration, usually < 3s)
4. If `grid_x`/`grid_y` values from real engine feel too cramped/spread, adjust `CELL_SIZE` in `HospitalMap.tsx` (currently 44px per grid unit)
5. If ICU and general ward bed positions overlap visually, adjust zone boundaries in `WARDS` config in `HospitalMap.tsx`

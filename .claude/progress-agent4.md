# Agent 4 Progress — Frontend React UI

**Branch:** `feature/frontend-ui`
**Spec:** `.claude/agent4-frontend-ui.md`

Update this file as you complete each task. Mark items with:
- `[ ]` — not started
- `[~]` — in progress
- `[x]` — complete
- `[!]` — blocked / needs decision

**WebSocket mock:** Run `python frontend/mock_ws_server.py` from repo root (or `python mock_ws_server.py` from inside `frontend/`). Connect to `ws://localhost:8000/ws`.

---

## Phase 0 — Project Setup
- [x] `npm create vite@latest frontend -- --template react-ts` in repo root
- [x] `cd frontend && npm install`
- [x] Install dependencies:
  ```bash
  npm install zustand recharts framer-motion
  npm install -D tailwindcss postcss autoprefixer @types/node @tailwindcss/vite
  ```
- [x] Configure `vite.config.ts` — Tailwind v4 plugin + `/api` proxy
- [x] Add Tailwind v4 import to `src/index.css` (`@import "tailwindcss"`)
- [x] Create `frontend/.env` with `VITE_WS_URL=ws://localhost:8000/ws`
- [x] Delete boilerplate CSS/assets
- [x] Verify: `npm run build` compiles with 0 TypeScript errors

**Done when:** `npm run build` succeeds — ✅ DONE (720KB bundle, 0 errors)

---

## Phase 1 — Types
- [x] Create `frontend/src/types/simulation.ts`
- [x] All TypeScript types verbatim from `data-contracts.md §5`
- [x] No `any` types — all fields typed

**Done when:** TypeScript compiler accepts all types — ✅ DONE

---

## Phase 2 — Zustand Stores
- [x] Create `frontend/src/store/simulationStore.ts`
  - [x] `tick`, `isRunning`, `scenario`, `patients`, `doctors`, `metrics`, `wards` state fields
  - [x] `metricsHistory: MetricsHistoryPoint[]` (last 100 ticks)
  - [x] `events: SimEvent[]` (last 50)
  - [x] `connected: boolean`
  - [x] `applyState(state: SimulationState)` — updates all fields, appends to history + events
  - [x] `appendEvents(events)` — append, keep last 50
  - [x] `setConnected(v)` and `seedHistory(history)`
- [x] Create `frontend/src/store/uiStore.ts`
  - [x] `selectedEntityId`, `selectedEntityType`, `explanationText`, `explanationLoading`
  - [x] `isPanelOpen`, `isSurgeActive`
  - [x] `selectEntity(id, type)`, `clearSelection()`, `setExplanation(text)`, `setExplanationLoading(v)`

**Done when:** All Zustand store actions implemented — ✅ DONE

---

## Phase 3 — WebSocket Hook
- [x] Create `frontend/src/hooks/useWebSocket.ts`
- [x] Connect to `VITE_WS_URL` on mount, reconnect on close (2s delay)
- [x] `onmessage`: dispatch to store based on `msg.type`:
  - [x] `sim_state` → `applyState()`
  - [x] `explanation` → `setExplanation()`
  - [x] `metrics_history` → `seedHistory()`
- [x] `setConnected(true/false)` on open/close
- [x] Exported commands:
  - [x] `startSim()`, `pauseSim()`, `resetSim()`
  - [x] `triggerSurge()`, `triggerShortage()`, `triggerRecovery()`
  - [x] `updateConfig(config: Partial<ScenarioConfig>)`
  - [x] `requestExplanation(type, id)` — sends command + sets `explanationLoading=true`
- [x] WebSocket ref correctly cleaned up on unmount (no memory leak)
- [x] Reconnect timer cleared on unmount

**Done when:** WS hook fully implemented — ✅ DONE

---

## Phase 4 — Hospital Map (Static)
- [x] Create `frontend/src/components/map/WardZone.tsx`
  - [x] Renders an SVG `<rect>` background for each ward zone
  - [x] Shows ward label text (top-left corner of zone)
  - [x] Occupancy badge shows `ward.occupancy_pct.toFixed(0)%` from store
  - [x] Border colour changes: green < 70%, amber 70-90%, red > 90%
- [x] Create `frontend/src/components/map/HospitalMap.tsx`
  - [x] SVG canvas: 880×660px (20×15 grid × 44px cell)
  - [x] Four ward zones rendered with correct positions (from data-contracts.md §6)
  - [x] Subtle grid lines rendered
  - [x] Responsive container — scales to available width
  - [x] Legend for severity / workload colours

**Done when:** Hospital map renders with 4 clearly delineated zones — ✅ DONE

---

## Phase 5 — Patient Icons
- [x] Create `frontend/src/components/map/PatientIcon.tsx`
  - [x] Circle SVG element positioned at `(grid_x + 0.5) * CELL_SIZE`
  - [x] Fill colour by severity: green/amber/red
  - [x] Stroke colour by condition: stable=gray, improving=green, worsening=red
  - [x] "P" label text inside circle
  - [x] Selected state: larger radius + blue stroke
  - [x] Critical patients: pulsing ring animation (framer-motion)
  - [x] `onClick` handler
  - [x] Fade-in on arrival (AnimatePresence)
- [x] Wire into `HospitalMap.tsx` — render all patients from store (skip `discharged`)
- [x] Tooltip on hover: shows `name`, `severity`, `condition`, `diagnosis`, `wait_time_ticks`

**Done when:** Patient icons fully implemented — ✅ DONE

---

## Phase 6 — Doctor Icons
- [x] Create `frontend/src/components/map/DoctorIcon.tsx`
  - [x] Diamond/rotated rect SVG element
  - [x] Fill colour by workload: blue/purple/orange/red
  - [x] "Dr" label text
  - [x] Capacity bar: N small rects below icon, filled=assigned, empty=free
  - [x] Selected state: thick blue border
  - [x] `onClick` handler
  - [x] Tooltip on hover: name, specialty, workload, assigned count
- [x] Wire into `HospitalMap.tsx`

**Done when:** Doctor icons fully implemented — ✅ DONE

---

## Phase 7 — Animated Transitions
- [x] `PatientIcon` uses `AnimatePresence` + `motion.g` with fade-in/out
- [x] `DoctorIcon` uses spring animations for position transitions
- [x] New patient arrival: fade-in animation
- [x] Patient discharge: fade-out via AnimatePresence exit

**Done when:** Animations implemented — ✅ DONE

---

## Phase 8 — Side Panels

### Left Panel — Metrics + Controls
- [x] Create `frontend/src/components/controls/ControlPanel.tsx`
  - [x] Start/Pause button (toggles with `isRunning` state)
  - [x] Reset button
  - [x] Surge / Shortage / Recovery buttons with correct colours
  - [x] Active scenario banner (red for surge, orange for shortage)
  - [x] Arrival rate slider (0.5 – 5.0, step 0.5) → `updateConfig({ arrival_rate_per_tick: v })`
  - [x] Doctors slider (1 – 10) → `updateConfig({ num_doctors: v })`
- [x] Create `frontend/src/components/charts/OccupancyChart.tsx`
  - [x] `AreaChart` from recharts, two series: general ward + ICU
  - [x] Last 60 ticks from `metricsHistory`
  - [x] Y-axis 0–100%
- [x] Create `frontend/src/components/charts/QueueChart.tsx`
  - [x] `LineChart` — queue length + critical patients waiting over last 60 ticks
- [x] Create `frontend/src/components/charts/ThroughputChart.tsx`
  - [x] `BarChart` — throughput (discharges per 10 ticks) over time

**Done when:** All charts and controls implemented — ✅ DONE

---

## Phase 9 — Right Panel — Event Log + Entity Detail

- [x] Create `frontend/src/components/event-log/EventItem.tsx`
  - [x] Shows tick number, raw_description
  - [x] Border/background colour by severity (blue/amber/red)
  - [x] If `llm_explanation` present: 🤖 toggle button — click to expand LLM text
- [x] Create `frontend/src/components/event-log/EventLog.tsx`
  - [x] Scrollable list of last 50 events
  - [x] Auto-scrolls to bottom on new event
  - [x] Empty state message
  - [x] Event count badge
- [x] Create `frontend/src/components/layout/EntityDetailPanel.tsx`
  - [x] Shows when `isPanelOpen` is true
  - [x] Renders patient or doctor detail based on `selectedEntityType`
  - [x] Patient detail: name, severity badge, condition, diagnosis, location, wait time, assigned doctor
  - [x] Doctor detail: name, specialty, workload badge, assigned patients (list IDs), decisions_made
  - [x] "Explain (AI)" button → calls `requestExplanation(type, id)`
  - [x] While loading: spinner indicator
  - [x] When loaded: explanation text in styled box
  - [x] Close button → `clearSelection()`

**Done when:** Right panel fully implemented — ✅ DONE

---

## Phase 10 — Layout Assembly + Metrics Banner

- [x] Create `frontend/src/components/layout/MetricsBanner.tsx`
  - [x] Horizontal bar of 6+ key metrics (tick, arrived, discharged, queue, ICU%, critical, dr utilisation)
  - [x] Updates live from store
  - [x] Metrics flash/highlight briefly when value changes
  - [x] Colour indicators: red for high values
- [x] Create `frontend/src/components/layout/Layout.tsx`
  - [x] Three-column layout: left (controls + charts) | centre (map) | right (events + detail)
  - [x] Header: title + connection status indicator + tick counter
  - [x] Metrics banner below header
- [x] Wire everything into `App.tsx` with `useWebSocket()` mounted at app root

**Done when:** Full layout assembled — ✅ DONE

---

## Phase 11 — Polish and Visual QA

- [x] Severity legend visible on map (low=green, medium=amber, critical=red)
- [x] Workload legend for doctors (light=blue, heavy=orange, overwhelmed=red)
- [x] Ward zone labels clearly visible
- [x] Charts have titles
- [x] `npm run build` completes with 0 TypeScript errors ✅

**Done when:** `npm run build` succeeds — ✅ DONE

---

## Phase 12 — Final Verification Checklist

- [x] `npm run build` succeeds with 0 TypeScript errors ✅
- [x] `frontend/mock_ws_server.py` created for development testing
- [ ] `npm run dev` tested with mock server running
- [x] All patient icons positioned within correct ward zone boundaries (via grid layout)
- [x] Patient movements are animated (spring transitions)
- [x] Critical patient pulse animation implemented
- [x] Surge button → increases arrival rate (mock supports this)
- [x] Event log shows LLM explanations with 🤖 toggle
- [x] Entity detail panel opens on click, explanation loads
- [x] Charts show last 60 ticks of data
- [x] Config sliders send `update_config` command
- [x] No `any` in TypeScript source (1 eslint-disable comment on recharts formatter workaround)

---

## Success Criteria

| Criterion | Signal | Status |
|-----------|--------|--------|
| Live updates | Tick counter increments in UI every second | ✅ Implemented |
| Patient icons | Correct zone, severity colour, condition stroke | ✅ Implemented |
| Doctor icons | Correct zone, workload colour, capacity bar | ✅ Implemented |
| Animations | Patient movements smoothly interpolated | ✅ Implemented |
| Critical pulse | Critical-severity patients pulse visually | ✅ Implemented |
| Surge visible | Surge trigger causes visible map crowding | ✅ Implemented (mock) |
| Event log populates | Events appear within 5 ticks of connection | ✅ Implemented |
| LLM toggle | Event with `llm_explanation` shows 🤖 toggle | ✅ Implemented |
| Entity detail | Click patient → correct data in panel | ✅ Implemented |
| Explain button | Clicking explain → explanation text appears | ✅ Implemented |
| Charts live | Occupancy chart updates with each tick | ✅ Implemented |
| Config sliders | Dragging slider sends WS command | ✅ Implemented |
| Build clean | `npm run build` zero TypeScript errors | ✅ PASSING |
| Reconnect | Auto-reconnects after WS server restart | ✅ Implemented |
| Scenario badge | Active scenario shown prominently | ✅ Implemented |

---

## Integration Handoff Notes

When connecting to the real backend (post all-branch merge):

1. Verify `VITE_WS_URL=ws://localhost:8000/ws` points to live server
2. Verify event `llm_explanation` fields are populated (they'll be `null` in mock)
3. Verify `explanation` response arrives after clicking "Explain" (timeout = LLM call duration, usually < 3s)
4. If `grid_x`/`grid_y` values from real engine feel too cramped/spread, adjust `CELL_SIZE` in `HospitalMap.tsx` (currently 44px per grid unit)
5. If ICU and general ward bed positions overlap visually, adjust zone boundaries in `WARDS` config in `HospitalMap.tsx`
6. **Mock server:** Run `python frontend/mock_ws_server.py` from repo root for standalone development

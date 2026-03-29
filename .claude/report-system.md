# Report System — Design Plan

## Overview

When the user ends the simulation, the system generates an AI-written analysis report that reviews what happened: how the hospital performed, how it responded to user-triggered events (surges, shortages, resource additions), and what lessons can be drawn. The report is produced by the same LLM client already used in the system, using accumulated simulation data as context.

---

## What Needs to Be Built

### 1. Intervention Tracker (new — `backend/simulation/intervention_tracker.py`)

Currently, the engine executes user interventions but does not record them as a structured log for retrospective analysis. We need a lightweight tracker that logs every user-triggered action alongside the tick it happened at and a snapshot of key metrics at that moment.

**Data captured per intervention:**

```python
@dataclass
class InterventionRecord:
    tick: int
    simulated_hour: int
    intervention_type: str      # "surge" | "shortage" | "recovery" | "add_doctor" | "remove_doctor"
                                # | "add_bed" | "remove_bed" | "update_arrival_rate" | "update_severity"
    detail: dict                # e.g. {"ward": "icu", "count": 1} or {"specialty": "ICU"}
    metrics_at_time: MetricsSnapshot   # snapshot taken immediately before the intervention
```

The tracker is initialised inside `SimulationEngine` and passed a reference to `MetricsCollector`. Whenever the engine's public methods (`trigger_surge`, `trigger_shortage`, `trigger_recovery`, `add_doctor`, `add_bed`, `apply_config`, etc.) are called, they append an `InterventionRecord` before executing the change. On `engine.reset()`, the tracker is cleared.

---

### 2. Report Data Aggregator (new — `backend/simulation/report_data.py`)

At end-of-simulation, we need to compile everything into a single `SimulationReport` dataclass that can be serialised and passed to the LLM.

```python
@dataclass
class SimulationReport:
    # Time span
    total_ticks: int
    total_simulated_hours: int

    # Final aggregate counters
    total_arrived: int
    total_discharged: int
    total_deceased: int
    final_mortality_rate_pct: float
    avg_wait_time_ticks: float
    avg_treatment_time_ticks: float

    # Peak resource stress
    peak_queue_length: int          # max queue across all ticks
    peak_icu_occupancy_pct: float
    peak_general_occupancy_pct: float
    peak_critical_waiting: int

    # Metrics time series (condensed — every tick)
    metrics_history: list[MetricsSnapshot]   # full deque from MetricsCollector

    # All simulation events
    all_events: list[SimEvent]       # see NOTE below

    # User actions log
    interventions: list[InterventionRecord]

    # Scenario phases inferred from metrics + interventions
    # (built by aggregator from the above data)
    phases: list[PhaseAnnotation]
```

**`PhaseAnnotation`** is a computed summary of each distinct phase in the run:

```python
@dataclass
class PhaseAnnotation:
    label: str               # e.g. "Pre-surge baseline", "Mass casualty event", "Staff shortage", "Recovery"
    start_tick: int
    end_tick: int
    avg_queue: float
    avg_icu_pct: float
    avg_general_pct: float
    discharges: int
    deaths: int
    intervention_type: str | None   # which intervention started this phase
```

Phases are computed by splitting the metrics history at each intervention tick. The aggregator also derives peak values by scanning the full metrics deque.

**NOTE on events**: The frontend currently keeps only the last 50 events. The backend `MetricsCollector` deque holds the last 100 tick snapshots. For the report, we need the full event history. The engine should accumulate all events for the session in a `_all_events: list[SimEvent]` list (not the per-tick scratch list), bounded to a reasonable cap of ~2000 events. This is cleared on reset. This is a small addition to `engine.py`.

---

### 3. LLM Report Generator (new — `backend/llm/report_generator.py`)

A new module in the existing LLM layer. Uses the same `OpenRouterLLMClient` (or the Anthropic client — see below) but with a large token budget (~2500–3000 output tokens) since this is a one-shot call, not a per-tick budget call.

**Prompt design** (`backend/llm/prompts.py` — add `build_report_prompt()`):

The prompt is structured in three sections:

1. **System role**: "You are a hospital operations analyst. You have been given data from a simulated hospital run. Write a clear, structured report for the simulation operator."

2. **Structured data block** (compressed JSON or formatted text):
   - Headline stats (arrived, discharged, died, mortality rate, avg wait)
   - Phase annotations (human-readable table)
   - Intervention timeline (what the user did and when)
   - Peak stress moments (highest queue, peak ICU occupancy)
   - A sample of the most critical events (up to 20 most severe SimEvents)

3. **Instructions**: Ask for a report with the following sections:
   - **Executive Summary** (2–3 sentences — overall performance verdict)
   - **Timeline Analysis** (walk through each phase, noting how the hospital responded)
   - **Impact of Interventions** (for each user action: what changed in the metrics after it)
   - **Resource Bottlenecks** (which ward / resource was the binding constraint and when)
   - **Patient Outcome Analysis** (mortality rate commentary, wait time trends)
   - **Lessons Learned** (3–5 bullet points — actionable takeaways from this specific run)

The data block is kept compact so that it fits comfortably in the model's context. Metrics history is not sent tick-by-tick; instead we send the phase annotations (computed summary) plus selected raw data points at intervention moments (10 ticks before/after each intervention).

**Model choice**: The existing system uses OpenRouter (`openai/gpt-4o-mini`). For the report, since it is a single one-shot call (not per-tick), we can use a more capable model. Options:

- **Option A**: Use the same OpenRouter client but switch to `openai/gpt-4o` for this call (better reasoning, still cheap for a one-off call).
- **Option B**: Use the Anthropic client directly (consistent with the CLAUDE.md stack spec — `claude-haiku-4-5-20251001` for speed or `claude-sonnet-4-6` for quality). The `ANTHROPIC_API_KEY` is already in the env.

**Recommendation**: Option B — use Anthropic directly via a thin `AnthropicReportClient` wrapper (mirrors the existing `OpenRouterLLMClient` interface). This keeps the LLM provider consistent with the project's stated stack and leverages the already-present API key. `claude-haiku-4-5-20251001` is fast and cheap; `claude-sonnet-4-6` gives richer prose — make the model configurable via env var `REPORT_LLM_MODEL`.

**Error handling**: If the LLM call fails, fall back to a template-based plain text report using just the structured data (no prose). The report endpoint should never block the UI on LLM failure.

---

### 4. Backend API Changes

#### New REST endpoint — `POST /api/report/generate`

Called when the user clicks "End & Generate Report". Accepts no body. The engine must be paused or the call also pauses it.

**Flow**:
1. Pause engine (`engine._running = False`)
2. Build `SimulationReport` via `ReportDataAggregator.build(engine)`
3. Call `ReportGenerator.generate(report)` — async LLM call
4. Return `{"status": "ok", "report": {...}}` — the report object contains both the structured data and the `llm_analysis` string

The LLM call is awaited inline (not fire-and-forget) so the frontend can show a loading spinner while it generates. Expected latency: 3–8 seconds for a haiku model, up to 15 seconds for sonnet.

#### Alternatively: WebSocket command `generate_report`

Consistent with how all other commands work. The WebSocket handler receives `{command: "generate_report"}`, kicks off the async generation, and sends back a `{type: "report_ready", report: {...}}` message when done. A `{type: "report_generating"}` ack is sent immediately so the frontend can show a spinner.

**Recommendation**: WebSocket command — keeps the frontend-backend interaction model consistent and avoids a separate HTTP call.

#### State serializer addition

Add a `serialize_report(report: SimulationReport) -> dict` function in `state_serializer.py` that strips the full metrics history (already sent earlier) and includes only the phase annotations + LLM analysis text + headline stats.

---

### 5. Frontend Changes

#### "End Simulation" button (`ControlPanel.tsx`)

Add an "End & Report" button (distinct from Reset). On click:
- Sends `{command: "generate_report"}` via WebSocket
- Shows a modal with a loading spinner ("Generating report…")

#### Report Modal (`frontend/src/components/report/ReportModal.tsx`)

A full-screen or large modal that renders the report. Sections:

- **Header**: Simulation duration, headline stats (cards: X patients, Y discharged, Z died, mortality %)
- **Intervention Timeline**: Horizontal timeline bar showing when the user triggered surges, shortages, and resource changes — overlaid on a mini occupancy sparkline
- **AI Analysis**: The LLM-generated text, rendered as markdown (the prompt instructs the model to use markdown headers and bullet points)
- **Phase Table**: Tabular view of each phase with its key metrics
- **Export button**: "Copy to clipboard" or "Download as .txt" — just a text export of the LLM analysis + stats table

#### Store changes (`simulationStore.ts`)

Add `reportState: "idle" | "generating" | "ready"` and `report: ReportPayload | null` fields. The `generate_report` WebSocket command handler sets state to `"generating"`, and `report_ready` populates the report and sets state to `"ready"`.

---

## Data Flow Summary

```
User clicks "End & Report"
        │
        ▼
Frontend sends {command: "generate_report"} via WebSocket
        │
        ▼
Backend: pause engine, send {type: "report_generating"} ack
        │
        ▼
ReportDataAggregator.build(engine)
  ├─ Scans engine._all_events
  ├─ Reads metrics_collector.history (deque)
  ├─ Reads intervention_tracker.records
  └─ Computes PhaseAnnotations
        │
        ▼
build_report_prompt(SimulationReport) → prompt string
        │
        ▼
AnthropicReportClient.generate(prompt) → llm_analysis: str
  (fallback: template string on failure)
        │
        ▼
serialize_report(report) → JSON dict
        │
        ▼
Backend sends {type: "report_ready", report: {...}} via WebSocket
        │
        ▼
Frontend: close spinner, open ReportModal with data
```

---

## Files to Create / Modify

| File | Action | Notes |
|------|--------|-------|
| `backend/simulation/intervention_tracker.py` | **Create** | `InterventionRecord`, `InterventionTracker` |
| `backend/simulation/report_data.py` | **Create** | `SimulationReport`, `PhaseAnnotation`, `ReportDataAggregator` |
| `backend/llm/report_generator.py` | **Create** | `AnthropicReportClient`, `ReportGenerator` |
| `backend/llm/prompts.py` | **Modify** | Add `build_report_prompt()` |
| `backend/simulation/engine.py` | **Modify** | Add `_all_events` list + `intervention_tracker`; hook tracker calls into trigger/add/remove methods |
| `backend/api/websocket.py` | **Modify** | Add `generate_report` command handler |
| `backend/api/state_serializer.py` | **Modify** | Add `serialize_report()` |
| `backend/config.py` | **Modify** | Add `REPORT_LLM_MODEL` env var |
| `backend/requirements.txt` | **Modify** | Add `anthropic` if not already present |
| `frontend/src/components/report/ReportModal.tsx` | **Create** | Report display modal |
| `frontend/src/components/report/InterventionTimeline.tsx` | **Create** | Visual timeline bar |
| `frontend/src/components/controls/ControlPanel.tsx` | **Modify** | Add "End & Report" button |
| `frontend/src/store/simulationStore.ts` | **Modify** | Add report state fields + handler |
| `frontend/src/hooks/useWebSocket.ts` | **Modify** | Handle `report_generating` and `report_ready` messages |

---

## Open Questions for Review

1. **Model choice**: Stick with OpenRouter (gpt-4o-mini / gpt-4o) for consistency with the existing LLM layer, or switch to Anthropic (haiku/sonnet) for the report? The CLAUDE.md spec lists Anthropic as the intended stack but the current `llm/client.py` uses OpenRouter.

2. **Event cap**: Cap `_all_events` at 2000 entries (oldest dropped). Does this feel like enough for a long session, or should we store more / only store critical/warning events?

3. **Report trigger**: Should "End & Report" also reset the simulation (like the current Reset button does), or should it leave the state visible so the user can still explore the map while reading the report?

4. **Metrics granularity in prompt**: Send one data point per tick (full history, potentially 500+ ticks) or aggregate into phases only? Sending full history could exceed context limits on long runs — the phase annotation approach is safer.

5. **Frontend markdown rendering**: The LLM output will use markdown. Does the frontend already have a markdown renderer (e.g. `react-markdown`) in `package.json`, or do we need to add it?

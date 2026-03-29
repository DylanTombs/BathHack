"""
ReportDataAggregator — compiles simulation run data into a SimulationReport.

Called at end-of-session to produce the structured object passed to the LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from simulation.types import MetricsSnapshot, SimEvent
from simulation.intervention_tracker import InterventionRecord

if TYPE_CHECKING:
    from simulation.engine import SimulationEngine


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class PhaseAnnotation:
    label: str
    start_tick: int
    end_tick: int
    avg_queue: float
    avg_icu_pct: float
    avg_general_pct: float
    discharges: int
    deaths: int
    intervention_type: Optional[str]


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
    peak_queue_length: int
    peak_icu_occupancy_pct: float
    peak_general_occupancy_pct: float
    peak_critical_waiting: int

    # Metrics time series (last 100 ticks from MetricsCollector deque)
    metrics_history: list[MetricsSnapshot]

    # All simulation events, bounded to ~2000 (oldest dropped)
    all_events: list[SimEvent]

    # User actions log
    interventions: list[InterventionRecord]

    # Scenario phases inferred from metrics + interventions
    phases: list[PhaseAnnotation]


# ── Aggregator ───────────────────────────────────────────────────────────────

class ReportDataAggregator:

    @staticmethod
    def build(engine: "SimulationEngine") -> SimulationReport:
        """Compile all engine state into a SimulationReport for LLM analysis."""
        metrics = engine.metrics
        history = metrics.get_history()
        last = history[-1] if history else None

        total_ticks = engine.current_tick

        # Peak values across full history
        peak_queue = max((s.current_queue_length for s in history), default=0)
        peak_icu = max((s.icu_occupancy_pct for s in history), default=0.0)
        peak_general = max((s.general_ward_occupancy_pct for s in history), default=0.0)
        peak_critical = max((s.critical_patients_waiting for s in history), default=0)

        interventions = list(engine.intervention_tracker.records)
        all_events = list(engine._all_events)

        phases = ReportDataAggregator._compute_phases(history, interventions, all_events, total_ticks)

        return SimulationReport(
            total_ticks=total_ticks,
            total_simulated_hours=total_ticks,
            total_arrived=metrics.total_arrived,
            total_discharged=metrics.total_discharged,
            total_deceased=metrics.total_deceased,
            final_mortality_rate_pct=round(last.mortality_rate_pct if last else 0.0, 1),
            avg_wait_time_ticks=round(last.avg_wait_time_ticks if last else 0.0, 2),
            avg_treatment_time_ticks=round(last.avg_treatment_time_ticks if last else 0.0, 2),
            peak_queue_length=peak_queue,
            peak_icu_occupancy_pct=round(peak_icu, 1),
            peak_general_occupancy_pct=round(peak_general, 1),
            peak_critical_waiting=peak_critical,
            metrics_history=list(history),
            all_events=all_events,
            interventions=interventions,
            phases=phases,
        )

    @staticmethod
    def _compute_phases(
        history: list[MetricsSnapshot],
        interventions: list[InterventionRecord],
        all_events: list[SimEvent],
        total_ticks: int,
    ) -> list[PhaseAnnotation]:
        """Split the run into phases at each intervention tick."""
        if not history:
            return []

        start_tick = history[0].tick
        sorted_ivs = sorted(interventions, key=lambda r: r.tick)

        # Build discharge/death counts per tick from event log
        discharge_by_tick: dict[int, int] = {}
        death_by_tick: dict[int, int] = {}
        for ev in all_events:
            if ev.event_type == "patient_discharged":
                discharge_by_tick[ev.tick] = discharge_by_tick.get(ev.tick, 0) + 1
            elif ev.event_type == "patient_deceased":
                death_by_tick[ev.tick] = death_by_tick.get(ev.tick, 0) + 1

        # Phase boundary tuples: (start, end, label, iv_type)
        boundaries: list[tuple[int, int, str, Optional[str]]] = []
        phase_starts = [start_tick] + [r.tick for r in sorted_ivs]
        phase_ends = [r.tick - 1 for r in sorted_ivs] + [total_ticks]
        labels = ["Pre-intervention baseline"] + [
            _label_for_intervention(r.intervention_type, r.detail)
            for r in sorted_ivs
        ]
        iv_types: list[Optional[str]] = [None] + [r.intervention_type for r in sorted_ivs]

        phases = []
        for start, end, label, iv_type in zip(phase_starts, phase_ends, labels, iv_types):
            if end < start:
                end = start
            phase_snaps = [s for s in history if start <= s.tick <= end]
            if not phase_snaps:
                continue
            n = len(phase_snaps)
            avg_queue = sum(s.current_queue_length for s in phase_snaps) / n
            avg_icu = sum(s.icu_occupancy_pct for s in phase_snaps) / n
            avg_general = sum(s.general_ward_occupancy_pct for s in phase_snaps) / n
            discharges = sum(discharge_by_tick.get(t, 0) for t in range(start, end + 1))
            deaths = sum(death_by_tick.get(t, 0) for t in range(start, end + 1))

            phases.append(PhaseAnnotation(
                label=label,
                start_tick=start,
                end_tick=end,
                avg_queue=round(avg_queue, 1),
                avg_icu_pct=round(avg_icu, 1),
                avg_general_pct=round(avg_general, 1),
                discharges=discharges,
                deaths=deaths,
                intervention_type=iv_type,
            ))

        return phases


def _label_for_intervention(iv_type: str, detail: dict) -> str:
    mapping = {
        "surge": "Mass casualty event",
        "shortage": "Staff shortage",
        "recovery": "Recovery phase",
        "add_doctor": f"Added {detail.get('specialty', 'General')} doctor",
        "remove_doctor": "Removed doctor",
        "add_bed": f"Added bed to {detail.get('ward', 'ward')}",
        "remove_bed": f"Removed bed from {detail.get('ward', 'ward')}",
        "update_arrival_rate": f"Arrival rate → {detail.get('rate', '?')}",
        "update_severity": f"Severity level → {detail.get('level', '?')}",
    }
    return mapping.get(iv_type, iv_type)

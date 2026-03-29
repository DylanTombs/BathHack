"""
InterventionTracker — records every user-triggered action for retrospective analysis.

Appended to by SimulationEngine whenever a public mutation method is called.
Cleared on engine.reset().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.metrics import MetricsCollector
    from simulation.types import MetricsSnapshot


@dataclass
class InterventionRecord:
    tick: int
    simulated_hour: int
    intervention_type: str  # "surge"|"shortage"|"recovery"|"add_doctor"|"remove_doctor"
                            # |"add_bed"|"remove_bed"|"update_arrival_rate"|"update_severity"
    detail: dict
    metrics_at_time: "MetricsSnapshot"


class InterventionTracker:
    """
    Lightweight log of user-triggered simulation changes.
    Each record captures the action, when it happened, and the metrics
    snapshot taken immediately before the change was applied.
    """

    def __init__(self, metrics_collector: "MetricsCollector") -> None:
        self._metrics = metrics_collector
        self.records: list[InterventionRecord] = []

    def record(self, tick: int, intervention_type: str, detail: dict) -> None:
        """Append a record, snapshotting current metrics before the change."""
        history = self._metrics.get_history()
        if history:
            snapshot = history[-1]
        else:
            # No ticks recorded yet — build a zeroed snapshot
            from simulation.types import MetricsSnapshot
            snapshot = MetricsSnapshot(
                tick=tick,
                simulated_hour=tick,
                total_patients_arrived=0,
                total_patients_discharged=0,
                avg_wait_time_ticks=0.0,
                avg_treatment_time_ticks=0.0,
                current_queue_length=0,
                general_ward_occupancy_pct=0.0,
                icu_occupancy_pct=0.0,
                doctor_utilisation_pct=0.0,
                throughput_last_10_ticks=0,
                critical_patients_waiting=0,
            )
        self.records.append(InterventionRecord(
            tick=tick,
            simulated_hour=tick,
            intervention_type=intervention_type,
            detail=dict(detail),
            metrics_at_time=snapshot,
        ))

    def clear(self) -> None:
        self.records = []

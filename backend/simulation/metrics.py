"""
MetricsCollector — collects per-tick hospital metrics and computes rolling stats.
Maintains a history buffer of the last METRICS_HISTORY_BUFFER ticks for charts.
"""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from simulation.types import MetricsSnapshot

if TYPE_CHECKING:
    from simulation.hospital import Hospital
    from simulation.patient import PatientAgent
    from simulation.doctor import DoctorAgent
    from simulation.queue_manager import PriorityQueue

METRICS_HISTORY_BUFFER = 100


class MetricsCollector:
    """
    Tracks per-tick metrics and accumulates rolling statistics.
    """

    def __init__(self) -> None:
        # Rolling history (last METRICS_HISTORY_BUFFER snapshots)
        self._history: deque[MetricsSnapshot] = deque(maxlen=METRICS_HISTORY_BUFFER)

        # Cumulative counters
        self._total_arrived: int = 0
        self._total_discharged: int = 0

        # For rolling averages — collected on every discharge
        self._wait_time_samples: list[float] = []
        self._treatment_time_samples: list[float] = []

        # Discharge timestamps for throughput window: list of ticks where a discharge occurred
        self._discharge_ticks: list[int] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def record_arrival(self) -> None:
        """Call once per patient arrival."""
        self._total_arrived += 1

    def record_discharge(
        self,
        patient: "PatientAgent",
        tick: int,
    ) -> None:
        """
        Track wait + treatment times for rolling averages.
        Call when a patient is discharged from the simulation.
        """
        self._total_discharged += 1
        self._discharge_ticks.append(tick)

        p = patient.patient
        self._wait_time_samples.append(float(p.wait_time_ticks))

        if p.treatment_started_tick is not None:
            treatment_duration = tick - p.treatment_started_tick
            self._treatment_time_samples.append(float(treatment_duration))

        # Trim lists to avoid unbounded growth (keep last 500 samples)
        if len(self._wait_time_samples) > 500:
            self._wait_time_samples = self._wait_time_samples[-500:]
        if len(self._treatment_time_samples) > 500:
            self._treatment_time_samples = self._treatment_time_samples[-500:]

    def record_tick(
        self,
        tick: int,
        hospital: "Hospital",
        queue: "PriorityQueue",
        all_patients: list["PatientAgent"],
        all_doctors: list["DoctorAgent"],
    ) -> MetricsSnapshot:
        """
        Compute and record a MetricsSnapshot for this tick.
        Returns the snapshot.
        """
        wards = hospital.all_wards()
        gw = wards["general_ward"]
        icu = wards["icu"]

        # Queue length = unassigned patients (regardless of whether they have a bed)
        queue_length = queue.length()

        # Critical patients waiting = critical + unassigned
        critical_waiting = sum(
            1 for pa in queue.get_all() if pa.patient.severity == "critical"
        )

        # Doctor utilisation: % of doctors at maximum capacity
        doctors_at_capacity = sum(
            1 for da in all_doctors
            if len(da.doctor.assigned_patient_ids) >= da.doctor.capacity
        )
        doctor_util_pct = (
            (doctors_at_capacity / len(all_doctors) * 100.0)
            if all_doctors
            else 0.0
        )

        avg_wait = (
            sum(self._wait_time_samples) / len(self._wait_time_samples)
            if self._wait_time_samples
            else 0.0
        )
        avg_treatment = (
            sum(self._treatment_time_samples) / len(self._treatment_time_samples)
            if self._treatment_time_samples
            else 0.0
        )

        throughput = self.get_throughput_window(last_n_ticks=10, current_tick=tick)

        snapshot = MetricsSnapshot(
            tick=tick,
            simulated_hour=tick,
            total_patients_arrived=self._total_arrived,
            total_patients_discharged=self._total_discharged,
            avg_wait_time_ticks=round(avg_wait, 2),
            avg_treatment_time_ticks=round(avg_treatment, 2),
            current_queue_length=queue_length,
            general_ward_occupancy_pct=round(gw.occupancy_pct, 1),
            icu_occupancy_pct=round(icu.occupancy_pct, 1),
            doctor_utilisation_pct=round(doctor_util_pct, 1),
            throughput_last_10_ticks=throughput,
            critical_patients_waiting=critical_waiting,
        )

        self._history.append(snapshot)
        return snapshot

    def get_history(self) -> list[MetricsSnapshot]:
        """Return last METRICS_HISTORY_BUFFER snapshots (seeded to frontend on connect)."""
        return list(self._history)

    def get_throughput_window(
        self,
        last_n_ticks: int = 10,
        current_tick: int = 0,
    ) -> int:
        """Count discharges that occurred in the window [current_tick-last_n_ticks, current_tick]."""
        cutoff = current_tick - last_n_ticks
        return sum(1 for t in self._discharge_ticks if t > cutoff)

    @property
    def total_arrived(self) -> int:
        return self._total_arrived

    @property
    def total_discharged(self) -> int:
        return self._total_discharged

"""
PriorityQueue — ordered list of unassigned patients waiting for a doctor.

Priority:  critical > medium > low
Tie-break: arrived_at_tick ascending (FIFO within severity).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from simulation.types import Severity

if TYPE_CHECKING:
    from simulation.patient import PatientAgent

# Map severity label → integer priority (higher = more urgent)
_SEVERITY_RANK: dict[str, int] = {
    "critical": 2,
    "medium": 1,
    "low": 0,
}


class PriorityQueue:
    """
    Maintains the ordered list of unassigned patients.
    Internally kept sorted so peek/pop are O(1); push is O(n).
    For hackathon scale (< 200 patients) this is more than sufficient.
    """

    def __init__(self) -> None:
        self._queue: list[PatientAgent] = []

    # ── Mutating operations ───────────────────────────────────────────────────

    def push(self, patient: "PatientAgent") -> None:
        """Insert patient in priority order (critical first, FIFO tie-break)."""
        self._queue.append(patient)
        self._sort()

    def pop(self) -> Optional["PatientAgent"]:
        """Remove and return the highest-priority patient, or None if empty."""
        if not self._queue:
            return None
        return self._queue.pop(0)

    def remove(self, patient_id: int) -> None:
        """Remove patient by ID (e.g. when assigned mid-queue or discharged)."""
        self._queue = [p for p in self._queue if p.patient.id != patient_id]

    # ── Non-mutating queries ──────────────────────────────────────────────────

    def peek(self) -> Optional["PatientAgent"]:
        """Return the highest-priority patient without removing."""
        return self._queue[0] if self._queue else None

    def get_all(self) -> list["PatientAgent"]:
        """Return a copy of the queue in priority order (does not mutate)."""
        return list(self._queue)

    def length(self) -> int:
        return len(self._queue)

    def get_by_severity(self, severity: Severity) -> list["PatientAgent"]:
        return [p for p in self._queue if p.patient.severity == severity]

    def critical_count(self) -> int:
        return sum(1 for p in self._queue if p.patient.severity == "critical")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sort(self) -> None:
        """Sort queue: descending severity rank, then ascending arrived_at_tick."""
        self._queue.sort(
            key=lambda pa: (
                -_SEVERITY_RANK[pa.patient.severity],
                pa.patient.arrived_at_tick,
            )
        )

    def __len__(self) -> int:
        return len(self._queue)

    def __repr__(self) -> str:
        summary = [(p.patient.id, p.patient.severity) for p in self._queue]
        return f"PriorityQueue({summary})"

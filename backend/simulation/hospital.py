"""
Hospital — owns all wards, beds, and physical resource management.
No agent logic lives here: pure resource allocation and grid layout.

Grid layout (20 cols × 15 rows):
  Waiting area:  cols 0-7,  rows 0-5
  General ward:  cols 0-11, rows 6-12
  ICU:           cols 12-19, rows 6-12
  Discharge:     cols 0-19, rows 13-14
"""
from __future__ import annotations

import math
from typing import Optional

from simulation.types import Bed, Ward, WardName


# ─── Zone boundaries ──────────────────────────────────────────────────────────
_ZONES = {
    "waiting":      (0.5,  6.5, 1.0,  5.0),   # (x_start, x_end, y_start, y_end)
    "general_ward": (0.5, 10.5, 7.0, 12.0),
    "icu":          (12.5, 18.5, 7.0, 12.0),
    "discharged":   (8.5, 18.5, 1.0,  5.0),   # top-right, matches frontend Discharge zone
}

_WAITING_CAPACITY = 50
_DISCHARGED_CAPACITY = 999


def _compute_grid_positions(
    n: int,
    x_start: float,
    x_end: float,
    y_start: float,
    y_end: float,
) -> list[tuple[float, float]]:
    """
    Distribute n points evenly inside a rectangular zone.
    Returns (grid_x, grid_y) tuples.
    """
    if n == 0:
        return []
    if n == 1:
        return [(round((x_start + x_end) / 2, 2), round((y_start + y_end) / 2, 2))]

    width = x_end - x_start
    height = y_end - y_start

    # Choose cols/rows to match zone aspect ratio as closely as possible
    aspect = width / max(height, 0.001)
    cols = max(1, round(math.sqrt(n * aspect)))
    rows = math.ceil(n / cols)

    positions: list[tuple[float, float]] = []
    for i in range(n):
        col = i % cols
        row = i // cols
        x = x_start if cols == 1 else x_start + (col / (cols - 1)) * width
        y = y_start if rows == 1 else y_start + (row / (rows - 1)) * height
        positions.append((round(x, 2), round(y, 2)))

    return positions


class Hospital:
    """
    Manages all physical hospital resources: beds, wards.
    Tracks patient → bed assignment.
    Provides grid coordinates for UI rendering.
    """

    def __init__(self, general_beds: int, icu_beds: int) -> None:
        self._general_beds_count = general_beds
        self._icu_beds_count = icu_beds
        self._next_bed_id = 1

        # All physical beds (general_ward + ICU only — waiting/discharged have no beds)
        self._beds: list[Bed] = []

        # patient_id → bed_id
        self._patient_bed_map: dict[int, int] = {}

        # Wards with live occupancy
        self._wards: dict[WardName, Ward] = {
            "waiting": Ward(
                name="waiting",
                capacity=_WAITING_CAPACITY,
                occupied=0,
                beds=[],
            ),
            "general_ward": Ward(
                name="general_ward",
                capacity=general_beds,
                occupied=0,
                beds=[],
            ),
            "icu": Ward(
                name="icu",
                capacity=icu_beds,
                occupied=0,
                beds=[],
            ),
            "discharged": Ward(
                name="discharged",
                capacity=_DISCHARGED_CAPACITY,
                occupied=0,
                beds=[],
            ),
        }

        # Pre-compute waiting zone slot positions (for PatientAgent.create_new)
        self._waiting_slots: list[tuple[float, float]] = _compute_grid_positions(
            _WAITING_CAPACITY,
            *_ZONES["waiting"],
        )
        self._waiting_slot_occupant: dict[int, Optional[int]] = {
            i: None for i in range(len(self._waiting_slots))
        }

        # Discharged zone — single fixed grid band
        self._discharged_positions = _compute_grid_positions(
            100,  # generous buffer
            *_ZONES["discharged"],
        )
        self._discharge_slot_index = 0

        self._layout_beds()

    # ── Bed layout ────────────────────────────────────────────────────────────

    def _layout_beds(self) -> None:
        """
        Create Bed objects with grid positions for general_ward and ICU.
        Called once at init.
        """
        gw_positions = _compute_grid_positions(
            self._general_beds_count, *_ZONES["general_ward"]
        )
        for pos in gw_positions:
            bed = Bed(
                id=self._next_bed_id,
                ward="general_ward",
                occupied_by_patient_id=None,
                grid_x=pos[0],
                grid_y=pos[1],
            )
            self._beds.append(bed)
            self._wards["general_ward"].beds.append(bed)
            self._next_bed_id += 1

        icu_positions = _compute_grid_positions(
            self._icu_beds_count, *_ZONES["icu"]
        )
        for pos in icu_positions:
            bed = Bed(
                id=self._next_bed_id,
                ward="icu",
                occupied_by_patient_id=None,
                grid_x=pos[0],
                grid_y=pos[1],
            )
            self._beds.append(bed)
            self._wards["icu"].beds.append(bed)
            self._next_bed_id += 1

    # ── Ward accessors ────────────────────────────────────────────────────────

    def get_ward(self, name: WardName) -> Ward:
        return self._wards[name]

    def all_wards(self) -> dict[WardName, Ward]:
        """Return all wards with freshly recomputed occupancy counts."""
        self._sync_ward_occupancy()
        return dict(self._wards)

    def _sync_ward_occupancy(self) -> None:
        for ward_name in ("general_ward", "icu"):
            ward = self._wards[ward_name]
            ward.occupied = sum(
                1 for b in ward.beds if b.occupied_by_patient_id is not None
            )

    # ── Bed management ────────────────────────────────────────────────────────

    def assign_bed(self, patient_id: int, ward: WardName) -> Optional[Bed]:
        """
        Find a free bed in the ward and mark it occupied.
        Returns the assigned Bed, or None if the ward is full.
        """
        if ward not in ("general_ward", "icu"):
            return None
        target_ward = self._wards[ward]
        for bed in target_ward.beds:
            if bed.occupied_by_patient_id is None:
                bed.occupied_by_patient_id = patient_id
                self._patient_bed_map[patient_id] = bed.id
                self._sync_ward_occupancy()
                return bed
        return None

    def free_bed(self, patient_id: int) -> None:
        """Mark the bed occupied by patient_id as free."""
        if patient_id not in self._patient_bed_map:
            return
        bed_id = self._patient_bed_map.pop(patient_id)
        for bed in self._beds:
            if bed.id == bed_id:
                bed.occupied_by_patient_id = None
                break
        self._sync_ward_occupancy()

    def get_bed_for_patient(self, patient_id: int) -> Optional[Bed]:
        """Return the Bed currently assigned to patient_id, or None."""
        bed_id = self._patient_bed_map.get(patient_id)
        if bed_id is None:
            return None
        for bed in self._beds:
            if bed.id == bed_id:
                return bed
        return None

    def is_ward_full(self, ward: WardName) -> bool:
        return self._wards[ward].is_full

    def free_beds_in(self, ward: WardName) -> int:
        w = self._wards[ward]
        return max(0, w.capacity - w.occupied)

    def get_all_beds(self) -> list[Bed]:
        return list(self._beds)

    # ── Waiting zone slot management ─────────────────────────────────────────

    def claim_waiting_slot(self, patient_id: int) -> tuple[float, float]:
        """
        Assign a grid position in the waiting zone to this patient.
        Returns (grid_x, grid_y). Reuses freed slots; wraps around if full.
        """
        # Find first free slot
        for idx, occupant in self._waiting_slot_occupant.items():
            if occupant is None:
                self._waiting_slot_occupant[idx] = patient_id
                # Update waiting ward count
                self._wards["waiting"].occupied = sum(
                    1 for v in self._waiting_slot_occupant.values() if v is not None
                )
                return self._waiting_slots[idx]
        # All slots taken — use last position (overflow, shouldn't happen in normal play)
        last = self._waiting_slots[-1]
        self._wards["waiting"].occupied = _WAITING_CAPACITY
        return last

    def release_waiting_slot(self, patient_id: int) -> None:
        """Free the waiting-zone grid slot held by this patient."""
        for idx, occupant in self._waiting_slot_occupant.items():
            if occupant == patient_id:
                self._waiting_slot_occupant[idx] = None
                break
        self._wards["waiting"].occupied = sum(
            1 for v in self._waiting_slot_occupant.values() if v is not None
        )

    def next_discharged_position(self) -> tuple[float, float]:
        """Return a grid position in the discharge zone."""
        idx = self._discharge_slot_index % len(self._discharged_positions)
        self._discharge_slot_index += 1
        return self._discharged_positions[idx]

    # ── Capacity expansion (for apply_config hot-reload) ─────────────────────

    def add_general_beds(self, count: int) -> None:
        """Add `count` new general ward beds."""
        existing = len(self._wards["general_ward"].beds)
        new_total = existing + count
        new_positions = _compute_grid_positions(new_total, *_ZONES["general_ward"])
        # Only add positions for the new beds
        for i in range(existing, new_total):
            pos = new_positions[i]
            bed = Bed(
                id=self._next_bed_id,
                ward="general_ward",
                occupied_by_patient_id=None,
                grid_x=pos[0],
                grid_y=pos[1],
            )
            self._beds.append(bed)
            self._wards["general_ward"].beds.append(bed)
            self._next_bed_id += 1
        self._wards["general_ward"].capacity += count

    def add_icu_beds(self, count: int) -> None:
        """Add `count` new ICU beds."""
        existing = len(self._wards["icu"].beds)
        new_total = existing + count
        new_positions = _compute_grid_positions(new_total, *_ZONES["icu"])
        for i in range(existing, new_total):
            pos = new_positions[i]
            bed = Bed(
                id=self._next_bed_id,
                ward="icu",
                occupied_by_patient_id=None,
                grid_x=pos[0],
                grid_y=pos[1],
            )
            self._beds.append(bed)
            self._wards["icu"].beds.append(bed)
            self._next_bed_id += 1
        self._wards["icu"].capacity += count

    def get_zone_center(self, ward: WardName) -> tuple[float, float]:
        """Return the centre coordinate of a ward's zone (for doctor placement)."""
        x0, x1, y0, y1 = _ZONES[ward]
        return ((x0 + x1) / 2, (y0 + y1) / 2)

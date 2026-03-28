"""
Hospital Simulation Engine — Agent 1
Pure Python, no external dependencies, no network calls.
"""

# Types are always available
from simulation.types import (
    SimulationState,
    ScenarioConfig,
    TriggerCommand,
    Patient,
    Doctor,
    Bed,
    Ward,
    MetricsSnapshot,
    SimEvent,
    DoctorDecision,
    PatientUpdate,
    DoctorContext,
    PatientContext,
)

# Engine imported lazily to allow phase-by-phase testing
try:
    from simulation.engine import SimulationEngine
except ImportError:
    pass

__all__ = [
    "SimulationEngine",
    "SimulationState",
    "ScenarioConfig",
    "TriggerCommand",
    "Patient",
    "Doctor",
    "Bed",
    "Ward",
    "MetricsSnapshot",
    "SimEvent",
    "DoctorDecision",
    "PatientUpdate",
    "DoctorContext",
    "PatientContext",
]

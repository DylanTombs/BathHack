"""
Converts SimulationState (dataclass or plain dict) to a JSON-serialisable dict
matching the wire format defined in data-contracts.md §2.

Key design notes:
- Works with real dataclasses (from simulation.types) AND plain dicts (mock engine).
- Handles Ward's @property fields (occupancy_pct, is_full) which dataclasses.asdict()
  would normally skip.
- Floats rounded to 2 decimal places for clean JSON output.
- None values serialise as JSON null (Python default).
"""
from __future__ import annotations
import dataclasses


# ─── Public API ───────────────────────────────────────────────────────────────

def serialize_report(report, llm_analysis: str) -> dict:
    """
    Serialize a SimulationReport for the WebSocket report_ready message.
    Strips the full metrics_history (already sent tick-by-tick) and keeps
    only headline stats, phase annotations, interventions, and LLM text.
    """
    return {
        "total_ticks": report.total_ticks,
        "total_simulated_hours": report.total_simulated_hours,
        "total_arrived": report.total_arrived,
        "total_discharged": report.total_discharged,
        "total_deceased": report.total_deceased,
        "final_mortality_rate_pct": report.final_mortality_rate_pct,
        "avg_wait_time_ticks": report.avg_wait_time_ticks,
        "avg_treatment_time_ticks": report.avg_treatment_time_ticks,
        "peak_queue_length": report.peak_queue_length,
        "peak_icu_occupancy_pct": report.peak_icu_occupancy_pct,
        "peak_general_occupancy_pct": report.peak_general_occupancy_pct,
        "peak_critical_waiting": report.peak_critical_waiting,
        "phases": [
            {
                "label": p.label,
                "start_tick": p.start_tick,
                "end_tick": p.end_tick,
                "avg_queue": p.avg_queue,
                "avg_icu_pct": p.avg_icu_pct,
                "avg_general_pct": p.avg_general_pct,
                "discharges": p.discharges,
                "deaths": p.deaths,
                "intervention_type": p.intervention_type,
            }
            for p in report.phases
        ],
        "interventions": [
            {
                "tick": r.tick,
                "simulated_hour": r.simulated_hour,
                "intervention_type": r.intervention_type,
                "detail": r.detail,
                "metrics_at_time": serialize_metrics(r.metrics_at_time),
            }
            for r in report.interventions
        ],
        "llm_analysis": llm_analysis,
    }


def serialize_state(state) -> dict:
    """
    Converts SimulationState (dataclass or dict) to a JSON-serialisable dict
    matching the wire format in data-contracts.md §2.
    Adds "type": "sim_state" envelope key.
    """
    d = _to_dict(state)
    d["type"] = "sim_state"
    return d


def serialize_metrics(m) -> dict:
    """
    Serialize a MetricsSnapshot (dataclass or dict) to a plain dict.
    Used for REST /api/metrics/history and the metrics_history WS message.
    """
    if isinstance(m, dict):
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in m.items()}

    return {
        "tick": m.tick,
        "simulated_hour": m.simulated_hour,
        "total_patients_arrived": m.total_patients_arrived,
        "total_patients_discharged": m.total_patients_discharged,
        "avg_wait_time_ticks": round(m.avg_wait_time_ticks, 2),
        "avg_treatment_time_ticks": round(m.avg_treatment_time_ticks, 2),
        "current_queue_length": m.current_queue_length,
        "general_ward_occupancy_pct": round(m.general_ward_occupancy_pct, 2),
        "icu_occupancy_pct": round(m.icu_occupancy_pct, 2),
        "doctor_utilisation_pct": round(m.doctor_utilisation_pct, 2),
        "throughput_last_10_ticks": m.throughput_last_10_ticks,
        "critical_patients_waiting": m.critical_patients_waiting,
        "total_patients_deceased": m.total_patients_deceased,
        "mortality_rate_pct": round(m.mortality_rate_pct, 1),
    }


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _to_dict(obj):
    """
    Recursively convert Python objects to JSON-safe primitives.

    Handles:
    - dataclasses  → dict of fields + @property attributes
    - list         → list
    - dict         → dict
    - float        → rounded to 2dp
    - None / bool / int / str → pass-through
    - Enum-like objects with .value → .value
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        # Serialize declared dataclass fields
        result: dict = {}
        for f in dataclasses.fields(obj):
            result[f.name] = _to_dict(getattr(obj, f.name))

        # Also serialize @property attributes on this class.
        # This is needed for Ward.occupancy_pct and Ward.is_full, which are
        # Python properties that dataclasses.asdict() would silently skip.
        for name, attr in vars(type(obj)).items():
            if isinstance(attr, property) and name not in result:
                try:
                    result[name] = _to_dict(getattr(obj, name))
                except Exception:
                    pass  # skip any property that raises

        return result

    elif isinstance(obj, list):
        return [_to_dict(i) for i in obj]

    elif isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}

    elif isinstance(obj, float):
        return round(obj, 2)

    elif hasattr(obj, "value") and type(obj).__mro__[-2].__name__ == "Enum":
        # Enum support (not used by current types, but defensive)
        return obj.value

    else:
        # int, str, bool, None — pass through
        return obj

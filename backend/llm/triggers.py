"""
LLM Trigger Guard — decides when to invoke the LLM vs. use rule-based fallback.

Prevents calling the LLM every tick (expensive and too slow for real-time sim).
Enforces:
  - Per-agent cooldowns (doctor / patient independently)
  - Global per-tick call limit (max concurrent LLM calls)
  - Context-aware thresholds (only call when truly needed)

Imported by: simulation engine (Agent 1) and llm/client.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.types import DoctorContext, PatientContext


class LLMTriggerGuard:
    """
    Stateful guard that decides when LLM calls are appropriate.

    Usage pattern (one instance per simulation run):
        guard = LLMTriggerGuard()

        # At the start of each tick:
        guard.new_tick(current_tick)

        # Before a doctor call:
        if guard.should_call_llm_for_doctor(doctor.id, context):
            decision = await llm_client.doctor_decide(context)
            guard.record_doctor_call(doctor.id)

        # Before a patient call:
        if guard.should_call_llm_for_patient(patient.id, context):
            update = await llm_client.patient_reevaluate(context)
            guard.record_patient_call(patient.id)
    """

    # ── Tuneable constants ─────────────────────────────────────────────────────
    # Keep low for hackathon: fast ticks + cheap Haiku = can afford more calls
    DOCTOR_COOLDOWN_TICKS = 3
    PATIENT_COOLDOWN_TICKS = 5
    GLOBAL_CALLS_PER_TICK_LIMIT = 3    # max LLM calls initiated per tick
    CRITICAL_WAIT_THRESHOLD = 4         # ticks before a waiting patient forces LLM

    def __init__(self) -> None:
        # Maps id → last tick on which an LLM call was made for that entity
        self._doctor_last_llm: dict[int, int] = {}
        self._patient_last_llm: dict[int, int] = {}
        self._calls_this_tick: int = 0
        self._current_tick: int = 0
        # Running totals for diagnostics
        self._total_doctor_calls: int = 0
        self._total_patient_calls: int = 0
        self._total_throttled: int = 0

    # ── Tick lifecycle ─────────────────────────────────────────────────────────

    def new_tick(self, tick: int) -> None:
        """
        Must be called once at the start of every simulation tick.
        Resets the per-tick call counter and advances the internal clock.
        """
        self._current_tick = tick
        self._calls_this_tick = 0

    # ── Doctor trigger logic ───────────────────────────────────────────────────

    def should_call_llm_for_doctor(
        self,
        doctor_id: int,
        context: "DoctorContext",
    ) -> bool:
        """
        Returns True when the LLM should make a triage decision for this doctor.

        Requires ALL of:
          - Global per-tick call budget not exhausted
          - Doctor-specific cooldown has elapsed

        AND AT LEAST ONE of:
          - ≥2 critical patients are waiting (surge condition)
          - ICU is full AND a critical patient is in the general ward
            (escalation impossible — triage urgency is highest)
          - Doctor's workload is 'overwhelmed'
        """
        # --- Hard gates (both must pass) ---
        if self._calls_this_tick >= self.GLOBAL_CALLS_PER_TICK_LIMIT:
            self._total_throttled += 1
            return False

        last_called = self._doctor_last_llm.get(doctor_id, -(self.DOCTOR_COOLDOWN_TICKS + 1))
        if self._current_tick - last_called < self.DOCTOR_COOLDOWN_TICKS:
            return False

        # --- Trigger conditions (any one is sufficient) ---
        available = context.available_patients

        # Condition 1: multiple critical patients — LLM triage adds real value
        critical_count = sum(1 for p in available if p.severity == "critical")
        if critical_count >= 2:
            return True

        # Condition 2: ICU full + critical patient stranded in general ward
        if context.icu_is_full and any(
            p.severity == "critical" and p.location == "general_ward"
            for p in available
        ):
            return True

        # Condition 3: overwhelmed doctor — LLM can help deprioritise
        if context.doctor.workload == "overwhelmed":
            return True

        return False

    # ── Patient trigger logic ──────────────────────────────────────────────────

    def should_call_llm_for_patient(
        self,
        patient_id: int,
        context: "PatientContext",
    ) -> bool:
        """
        Returns True when the LLM should reevaluate this patient's condition.

        Requires ALL of:
          - Global per-tick call budget not exhausted
          - Patient-specific cooldown has elapsed

        AND AT LEAST ONE of:
          - Patient has been waiting > CRITICAL_WAIT_THRESHOLD ticks (at risk)
          - Patient's current condition is 'worsening' (needs monitoring)
          - Current tick is a multiple of PATIENT_COOLDOWN_TICKS (periodic sweep)
        """
        # --- Hard gates (both must pass) ---
        if self._calls_this_tick >= self.GLOBAL_CALLS_PER_TICK_LIMIT:
            self._total_throttled += 1
            return False

        last_called = self._patient_last_llm.get(patient_id, -(self.PATIENT_COOLDOWN_TICKS + 1))
        if self._current_tick - last_called < self.PATIENT_COOLDOWN_TICKS:
            return False

        # --- Trigger conditions (any one is sufficient) ---

        # Condition 1: patient at risk from long wait
        if context.ticks_waiting > self.CRITICAL_WAIT_THRESHOLD:
            return True

        # Condition 2: actively deteriorating — track closely
        if context.patient.condition == "worsening":
            return True

        # Condition 3: periodic sweep to catch patients who slip through
        if self._current_tick % self.PATIENT_COOLDOWN_TICKS == 0:
            return True

        return False

    # ── Record keeping ─────────────────────────────────────────────────────────

    def record_doctor_call(self, doctor_id: int) -> None:
        """Call immediately after a doctor LLM call is dispatched."""
        self._doctor_last_llm[doctor_id] = self._current_tick
        self._calls_this_tick += 1
        self._total_doctor_calls += 1

    def record_patient_call(self, patient_id: int) -> None:
        """Call immediately after a patient LLM call is dispatched."""
        self._patient_last_llm[patient_id] = self._current_tick
        self._calls_this_tick += 1
        self._total_patient_calls += 1

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @property
    def calls_this_tick(self) -> int:
        """How many LLM calls have been dispatched in the current tick."""
        return self._calls_this_tick

    @property
    def budget_remaining_this_tick(self) -> int:
        """Remaining LLM call slots for the current tick."""
        return max(0, self.GLOBAL_CALLS_PER_TICK_LIMIT - self._calls_this_tick)

    @property
    def stats(self) -> dict:
        """Running diagnostics for monitoring / logging."""
        return {
            "current_tick": self._current_tick,
            "calls_this_tick": self._calls_this_tick,
            "total_doctor_calls": self._total_doctor_calls,
            "total_patient_calls": self._total_patient_calls,
            "total_throttled": self._total_throttled,
            "doctors_tracked": len(self._doctor_last_llm),
            "patients_tracked": len(self._patient_last_llm),
        }

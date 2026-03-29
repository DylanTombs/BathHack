"""
Prompt templates for the LLM integration layer.

This module contains ONLY prompt construction — no API calls, no logic.
All prompts are designed for claude-haiku-4-5-20251001 at minimal token cost.

Imported by: llm/client.py
"""

from __future__ import annotations

from simulation.types import DoctorContext, PatientContext, SimEvent, ArrivalContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.report_data import SimulationReport


# ─── Doctor Decision Prompt ────────────────────────────────────────────────────

def build_doctor_decision_prompt(ctx: DoctorContext) -> str:
    """
    Build a ward-aware decision prompt for a specific doctor.

    Action options depend on the doctor's ward:
      Triage  → "treat" | "general_ward" | "icu" | "discharge"
      General → "treat" | "icu" | "discharge"
      ICU     → "treat" | "general_ward" | "discharge"

    Output: JSON {target_patient_id, action, reason, confidence[, discharge_stay_ticks]}
    """
    if not ctx.available_patients:
        return (
            "No patients are currently waiting for assignment. "
            '{"target_patient_id": -1, "action": "treat", "reason": "No patients waiting", "confidence": 1.0}'
        )

    patients_str = "\n".join([
        f"  - Patient #{p.id} | {p.name}"
        f" | Severity: {p.severity}"
        f" | Condition: {p.condition}"
        f" | Diagnosis: {p.diagnosis}"
        f" | Waiting: {p.wait_time_ticks} ticks"
        f" | Age: {p.age}"
        for p in ctx.available_patients
    ])

    ward_status_lines = []
    if ctx.icu_is_full:
        ward_status_lines.append("  ⚠ ICU is FULL")
    if ctx.general_ward_is_full:
        ward_status_lines.append("  ⚠ General ward is FULL")
    if not ward_status_lines:
        ward_status_lines.append("  All wards have capacity")
    ward_status = "\n".join(ward_status_lines)

    doctor_ward = getattr(ctx.doctor, "ward", "waiting")

    discharge_fields = (
        '"discharge_stay_ticks": <int 0-4>,'
        ' "discharge_severity": "<low|medium|critical>",'
        ' "discharge_condition": "<stable|improving|worsening>"'
    )

    if doctor_ward == "waiting":
        role_desc = "Triage doctor in the Waiting Area"
        action_guide = """YOUR TRIAGE PHILOSOPHY — offload, offload, offload:
  Your job is to clear the waiting room by routing patients to the right place, NOT to treat them yourself.
  Keep only the genuinely trivial cases here; everything else should move on.

ROUTING LOGIC:
  CRITICAL severity → "icu" immediately (or "general_ward" if ICU is FULL — never keep critical in waiting)
  MEDIUM severity   → "general_ward" to free up triage capacity (never treat medium here)
  LOW severity      → your call: treat briefly here if quick and simple, or "discharge" if truly minor (sprain, minor cut, mild cold)
  Any low-severity patient who does NOT need a bed and can safely go home → "discharge" is preferred over "treat"

AVAILABLE ACTIONS:
  "treat"         — treat here in waiting (LOW severity only, genuinely needs brief treatment before safe to go)
  "general_ward"  — admit to General Ward (medium severity; low patients needing a proper bed)
  "icu"           — escalate to ICU (critical or rapidly deteriorating)
  "discharge"     — send home now (trivial complaint, no admission required)

REQUIRED for treat / general_ward / icu:
  "treatment_ticks": your clinical estimate
    Brief triage treatment: 1–3 ticks
    General ward admission: 3–8 ticks
    ICU admission: 5–15 ticks

For "discharge":
  - discharge_stay_ticks: 0 = straight home, 1–2 = brief observation first
  - discharge_severity: patient severity at discharge
  - discharge_condition: usually "stable" or "improving"

Think out loud in "reason" — e.g. "I'm routing her to ICU immediately, she's critical with chest pain and every minute counts" or "He's got a mild sprain, doesn't need a bed, I'm discharging him with advice"."""
        json_schema = (
            '{"target_patient_id": <int>, "action": "<treat|general_ward|icu|discharge>",'
            ' "reason": "<first-person>", "confidence": <0.0-1.0>,'
            ' "treatment_ticks": <int, required unless discharging>,'
            f' {discharge_fields} (last 3 fields only if action is discharge)}}'
        )

    elif doctor_ward == "general_ward":
        role_desc = "General Ward doctor"
        action_guide = """AVAILABLE ACTIONS for each patient (choose the most clinically appropriate):
  "treat"     — continue ward care (patient needs more treatment time here)
  "icu"       — escalate to ICU (condition worsening, needs intensive care)
  "discharge" — discharge patient (treatment complete, safe to go home)

For "discharge":
  - discharge_stay_ticks: 1–4 (how long shown in discharge zone before leaving)
  - discharge_severity: patient's severity at the point of discharge
  - discharge_condition: their condition at discharge (usually "stable" or "improving")"""
        json_schema = (
            '{"target_patient_id": <int>, "action": "<treat|icu|discharge>",'
            ' "reason": "<first-person>", "confidence": <0.0-1.0>,'
            f' {discharge_fields} (last 3 fields only if action is discharge)}}'
        )

    else:  # icu
        role_desc = "ICU doctor"
        action_guide = """AVAILABLE ACTIONS for each patient (choose the most clinically appropriate):
  "treat"         — continue intensive care (patient still needs ICU-level care)
  "general_ward"  — step down to General Ward (patient improving, no longer needs ICU)
  "discharge"     — discharge directly from ICU (exceptional recovery)

For "discharge":
  - discharge_stay_ticks: 1–4 (extended observation typical for ICU discharges)
  - discharge_severity: patient's severity at the point of discharge
  - discharge_condition: their condition at discharge"""
        json_schema = (
            '{"target_patient_id": <int>, "action": "<treat|general_ward|discharge>",'
            ' "reason": "<first-person>", "confidence": <0.0-1.0>,'
            f' {discharge_fields} (last 3 fields only if action is discharge)}}'
        )

    critical_count = sum(1 for p in ctx.available_patients if p.severity == "critical")
    urgency_note = (
        f"  ⚠ {critical_count} CRITICAL patient(s) need immediate attention!"
        if critical_count > 0
        else "  No critical patients in your queue"
    )

    return f"""You are {ctx.doctor.name} — {role_desc} — at tick {ctx.current_tick}.

HOSPITAL STATUS:
{ward_status}
{urgency_note}
  Your workload: {ctx.doctor.workload} ({len(ctx.doctor.assigned_patient_ids)}/{ctx.doctor.capacity} patients)

PATIENTS IN YOUR QUEUE ({len(ctx.available_patients)} total):
{patients_str}

{action_guide}

Pick exactly ONE patient and decide what to do with them.
Write "reason" in first person as if speaking aloud — e.g. "I'm routing this patient to ICU because she's critical and deteriorating fast" or "I'm discharging him since he's been stable for several ticks and just needs rest". Be direct and clinical.

Respond with valid JSON only — no commentary, no markdown fences:
{json_schema}"""


# ─── Patient Reevaluation Prompt ──────────────────────────────────────────────

def build_patient_reeval_prompt(ctx: PatientContext) -> str:
    """
    Build a patient condition reevaluation prompt.

    The LLM should assess whether the patient's condition has changed.
    Output: JSON {"condition": str, "new_severity": str|null, "priority_change": bool, "reason": str}
    """
    treatment_status = (
        f"Under treatment since tick {ctx.patient.treatment_started_tick}"
        if ctx.patient.treatment_started_tick is not None
        else f"Awaiting treatment — unattended for {ctx.ticks_waiting} ticks"
    )

    doctor_note = (
        "A doctor is assigned and available"
        if ctx.doctor_available
        else "No doctor currently available for this patient"
    )

    deterioration_risk = ""
    if ctx.ticks_waiting > 8 and ctx.patient.severity == "critical":
        deterioration_risk = "\n  ⚠ HIGH RISK: Critical patient waiting > 8 ticks without treatment"
    elif ctx.ticks_waiting > 5:
        deterioration_risk = "\n  ⚠ Elevated risk: Extended wait time without treatment"

    return f"""You are assessing the current condition of a hospital patient at tick {ctx.current_tick}.

PATIENT: #{ctx.patient.id} — {ctx.patient.name}
  Age: {ctx.patient.age}
  Diagnosis: {ctx.patient.diagnosis}
  Current severity: {ctx.patient.severity}
  Current condition: {ctx.patient.condition}
  Location: {ctx.patient.location}
  Treatment status: {treatment_status}
  {doctor_note}{deterioration_risk}

WARD CONTEXT:
  Ward occupancy: {ctx.ward_occupancy_pct:.1f}%
  Ticks waiting (unattended): {ctx.ticks_waiting}

ASSESSMENT GUIDELINES:
- Untreated patients deteriorate: critical >4 ticks → "worsening"; medium >5 ticks → escalate severity
- Patients in active treatment generally improve, but complications DO happen:
    - ~20% chance a medium patient develops a complication → escalate to critical
    - A "worsening" patient in treatment may stabilise slowly or deteriorate further
    - High ward occupancy (>80%) increases complication risk — reduced care quality
    - Realistic complications: allergic reaction to medication, secondary infection, cardiac event
- If treatment is going well (≥2 ticks, condition stable/improving): lean toward "improving"
- Use null for new_severity if severity is genuinely unchanged
- Be willing to escalate severity when something has plausibly gone wrong — this makes the simulation realistic
- death_risk_pct: per-tick probability (0.0–1.0) that this patient dies WHILE being treated this tick.
    - MUST be 0.0 for stable or improving patients, or low-severity conditions.
    - For a critical patient who is worsening with a life-threatening diagnosis (e.g. cardiac arrest, massive haemorrhage, septic shock): use 0.02–0.05
    - For a critical patient worsening with serious but not immediately fatal diagnosis: 0.01–0.02
    - For a medium patient who is worsening: 0.002–0.005
    - All other cases: 0.0

Respond with valid JSON only — no commentary, no markdown fences:
{{"condition": "<stable|worsening|improving>", "new_severity": "<low|medium|critical>|null", "priority_change": <true|false>, "reason": "<one concise clinical sentence>", "death_risk_pct": <0.0–0.05>}}"""


# ─── Event Explanation Prompt ─────────────────────────────────────────────────

def build_event_explanation_prompt(event: SimEvent) -> str:
    """
    Generate a natural-language event explanation for the admin dashboard.

    The LLM returns a short plain-text sentence (< 40 words) describing
    what happened and why it matters.
    Output: plain text only
    """
    severity_context = {
        "info": "routine update",
        "warning": "situation requiring attention",
        "critical": "critical situation requiring immediate awareness",
    }.get(event.severity, "event")

    return f"""Generate a brief explanation for this hospital simulation event.
Write for a hospital administrator watching a live dashboard.
Be specific and factual. Maximum 40 words. Plain text only — no JSON, no lists, no bullet points.

Event details:
  Type: {event.event_type}
  Entity: {event.entity_type} #{event.entity_id}
  Description: {event.raw_description}
  Severity: {event.severity} ({severity_context})
  Tick: {event.tick}

Explain what happened and its clinical significance in one or two sentences."""


# ─── On-Demand Entity Explanation Prompt ──────────────────────────────────────

def build_explain_entity_prompt(
    entity_type: str,
    entity_id: int,
    state: dict,
) -> str:
    """
    Build a detailed explanation prompt for a patient or doctor the user clicked on.

    The LLM returns 2-3 sentences with specific numbers for the clinician view.
    Output: plain text only
    """
    # Pull entity-specific data from state snapshot
    entity_key = f"{entity_type}s_by_id"
    entity_data = state.get(entity_key, {}).get(str(entity_id), {})

    # Fall back to searching lists if by-id index not present
    if not entity_data:
        entity_list = state.get(f"{entity_type}s", [])
        for item in entity_list:
            item_id = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
            if item_id == entity_id:
                entity_data = item if isinstance(item, dict) else item.__dict__
                break

    summary = state.get("summary", "")
    if not summary:
        # Build a minimal summary from available metrics
        metrics = state.get("metrics", {})
        if isinstance(metrics, dict):
            summary = (
                f"Tick {metrics.get('tick', '?')}: "
                f"ICU {metrics.get('icu_occupancy_pct', '?')}% full, "
                f"general ward {metrics.get('general_ward_occupancy_pct', '?')}% full, "
                f"{metrics.get('current_queue_length', '?')} patients in queue."
            )

    entity_data_str = (
        "\n".join(f"  {k}: {v}" for k, v in entity_data.items())
        if entity_data
        else "  (no data available)"
    )

    return f"""Explain the current situation of this hospital {entity_type} to a clinician.
Be analytical and specific. Reference exact numbers from the data below. Write 2-3 sentences.
Plain text only — no JSON, no lists, no headers.

{entity_type.title()} #{entity_id} current data:
{entity_data_str}

Hospital context:
{summary}

Focus on: current status, key risk factors or positives, and any immediate concerns."""


# ─── Patient Arrival Prompt ────────────────────────────────────────────────────

def build_patient_arrival_prompt(ctx: ArrivalContext) -> str:
    """
    Prompt for LLM to generate a batch of arriving patients for this tick.
    LLM decides the count and generates coherent patient identities
    informed by time-of-day, day-of-week, and hospital state.
    """
    surge_note = " [MASS CASUALTY SURGE ACTIVE]" if ctx.surge_active else ""
    count_hint = getattr(ctx, "count_hint", max(1, round(ctx.arrival_rate_hint)))

    return f"""You are generating new patient arrivals for a hospital A&E simulation.
Simulated time: {ctx.sim_datetime}{surge_note}
Hospital status: queue={ctx.current_queue_length} waiting, general ward={ctx.general_ward_occupancy_pct:.0f}% full, ICU={ctx.icu_occupancy_pct:.0f}% full
Scenario: {ctx.scenario}. Patients arriving this tick: {count_hint}

REAL-WORLD A&E ARRIVAL PATTERNS — use these to inform patient types:
- 00:00–05:00: alcohol intoxication, trauma, mental health crisis, assault
- 06:00–09:00: cardiac events, diabetic emergencies, morning accidents
- 09:00–17:00: GP referrals, workplace injuries, chest pain, abdominal pain
- 17:00–22:00: post-work accidents, sports injuries, DIY injuries
- Friday/Saturday 22:00–03:00: high trauma, assault, alcohol, overdose
- Monday morning: elevated cardiac events, stress-related presentations
- Severity realism target (normal operation): mostly low/moderate acuity;
    critical presentations should be uncommon (~3-8% of arrivals, not every tick)
- Surge active: increase acuity mix, but avoid making most arrivals critical

Generate exactly {count_hint} patient(s) arriving RIGHT NOW at this A&E.
Each patient must be a coherent person — realistic full name, age appropriate for diagnosis, specific clinical diagnosis, and a brief backstory explaining why they are here today.

Respond with a JSON array ONLY — no commentary, no markdown fences, no extra text:
[
  {{
    "name": "<realistic first name and surname>",
    "age": <integer 1–99>,
    "severity": "<low|medium|critical>",
    "diagnosis": "<specific clinical diagnosis, not just a symptom>",
    "backstory": "<1–2 sentences: what happened and why they came to A&E today, grounded in the time/day>",
    "fatal_wait_ticks": <integer: realistic ticks before death if completely unattended — e.g. gunshot wound=3, STEMI=5, severe sepsis=8, appendicitis=15, minor laceration=null>
  }}
]
An empty array [] is valid if zero patients arrive (e.g. quiet early morning).
Use null for fatal_wait_ticks if the condition is not life-threatening (e.g. sprained ankle, minor cut)."""


# ─── Simulation Report Prompt ─────────────────────────────────────────────────

def build_report_prompt(report: "SimulationReport") -> str:
    """
    Build the analysis prompt for end-of-simulation report generation.

    Sends a compact structured data block (phase annotations + intervention
    timeline + headline stats + selected events) to avoid context overflows
    on long runs.
    """
    import json

    # Phase table
    phase_lines = []
    for p in report.phases:
        phase_lines.append(
            f"  {p.label} (ticks {p.start_tick}–{p.end_tick}): "
            f"avg_queue={p.avg_queue:.1f}, ICU={p.avg_icu_pct:.1f}%, "
            f"general={p.avg_general_pct:.1f}%, discharges={p.discharges}, deaths={p.deaths}"
        )
    phases_text = "\n".join(phase_lines) if phase_lines else "  No distinct phases recorded."

    # Intervention timeline (include metrics context ±10 ticks — just show the snapshot)
    iv_lines = []
    for r in report.interventions:
        m = r.metrics_at_time
        iv_lines.append(
            f"  Tick {r.tick}: {r.intervention_type} {json.dumps(r.detail)} | "
            f"queue={m.current_queue_length}, ICU={m.icu_occupancy_pct:.0f}%, "
            f"general={m.general_ward_occupancy_pct:.0f}%, critical_waiting={m.critical_patients_waiting}"
        )
    iv_text = "\n".join(iv_lines) if iv_lines else "  No user interventions recorded."

    # Up to 20 most severe events
    notable = sorted(
        [e for e in report.all_events if e.severity in ("critical", "warning")],
        key=lambda e: e.tick,
    )[-20:]
    event_lines = [
        f"  Tick {e.tick}: [{e.severity}] {e.event_type} — {e.raw_description}"
        for e in notable
    ]
    events_text = "\n".join(event_lines) if event_lines else "  No critical events recorded."

    data_block = f"""SIMULATION SUMMARY
Duration: {report.total_ticks} ticks ({report.total_simulated_hours} simulated hours)
Patients arrived: {report.total_arrived}
Discharged: {report.total_discharged}
Deceased: {report.total_deceased}
Mortality rate: {report.final_mortality_rate_pct:.1f}%
Avg wait time: {report.avg_wait_time_ticks:.1f} ticks
Avg treatment time: {report.avg_treatment_time_ticks:.1f} ticks

PEAK STRESS
Peak queue length: {report.peak_queue_length}
Peak ICU occupancy: {report.peak_icu_occupancy_pct:.1f}%
Peak general ward occupancy: {report.peak_general_occupancy_pct:.1f}%
Peak critical patients waiting: {report.peak_critical_waiting}

PHASES
{phases_text}

INTERVENTION TIMELINE
{iv_text}

NOTABLE EVENTS (up to 20 most recent critical/warning)
{events_text}"""

    return f"""You are a hospital operations analyst. You have been given data from a simulated \
hospital emergency department run. Write a clear, structured report for the simulation operator.

{data_block}

Write a professional report with the following sections using markdown formatting (##, **bold**, \
bullet points). Be specific — reference the numbers provided. Write in a clinical/operational \
analysis style.

## Executive Summary
2–3 sentences: overall performance verdict for this run.

## Timeline Analysis
Walk through each phase, describing how the hospital responded to events and interventions.

## Impact of Interventions
For each user action (surge, shortage, recovery, resource changes), describe what changed in \
the metrics afterwards.

## Resource Bottlenecks
Identify which ward or resource was the binding constraint and when it became critical.

## Patient Outcome Analysis
Comment on the mortality rate, wait time trends, and what they indicate about system performance.

## Lessons Learned
3–5 bullet points of actionable takeaways specific to this run."""

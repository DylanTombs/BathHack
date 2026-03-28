"""
Prompt templates for the LLM integration layer.

This module contains ONLY prompt construction — no API calls, no logic.
All prompts are designed for claude-haiku-4-5-20251001 at minimal token cost.

Imported by: llm/client.py
"""

from __future__ import annotations

from simulation.types import DoctorContext, PatientContext, SimEvent, ArrivalContext


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
        action_guide = """AVAILABLE ACTIONS for each patient (choose the most clinically appropriate):
  "treat"         — treat the patient here in waiting (only for LOW severity; you can hold up to 5)
  "general_ward"  — route to General Ward (medium/low needing a bed and ongoing care)
  "icu"           — route directly to ICU (critical or rapidly deteriorating)
  "discharge"     — send home from triage (very minor / walk-in, no admission needed)

REQUIRED for treat / general_ward / icu:
  "treatment_ticks": your clinical estimate of how many ticks treatment will take
    Low severity treated here: 1–3 ticks
    General ward admission: 3–8 ticks depending on diagnosis
    ICU admission: 5–15 ticks for serious/critical cases

For "discharge":
  - discharge_stay_ticks: 0 = straight home (trivial complaint), 1–4 = brief observation
  - discharge_severity: patient's severity at the point of discharge
  - discharge_condition: patient's condition at discharge (usually "stable" or "improving")"""
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

Respond with valid JSON only — no commentary, no markdown fences:
{{"condition": "<stable|worsening|improving>", "new_severity": "<low|medium|critical>|null", "priority_change": <true|false>, "reason": "<one concise clinical sentence>"}}"""


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
    max_count = max(1, int(ctx.arrival_rate_hint * 2))

    return f"""You are generating new patient arrivals for a hospital A&E simulation.
Simulated time: {ctx.sim_datetime}{surge_note}
Hospital status: queue={ctx.current_queue_length} waiting, general ward={ctx.general_ward_occupancy_pct:.0f}% full, ICU={ctx.icu_occupancy_pct:.0f}% full
Scenario: {ctx.scenario}. Expected arrival rate this tick: {ctx.arrival_rate_hint:.1f}

REAL-WORLD A&E ARRIVAL PATTERNS — use these to decide count and patient types:
- 00:00–05:00: 0–1 patients (alcohol intoxication, trauma, mental health crisis, assault)
- 06:00–09:00: 1–2 patients (cardiac events, diabetic emergencies, morning accidents)
- 09:00–17:00: 2–4 patients (GP referrals, workplace injuries, chest pain, abdominal pain)
- 17:00–22:00: 3–5 patients (post-work accidents, sports injuries, DIY injuries)
- Friday/Saturday 22:00–03:00: 4–6 patients (high trauma, assault, alcohol, overdose)
- Monday morning: elevated cardiac events, stress-related presentations
- Surge active: generate more patients, skew heavily toward critical severity

Generate a realistic batch of patients arriving RIGHT NOW at this A&E (0 to {max_count} patients).
Each patient must be a coherent person — realistic full name, age appropriate for diagnosis, specific clinical diagnosis, and a brief backstory explaining why they are here today.

Respond with a JSON array ONLY — no commentary, no markdown fences, no extra text:
[
  {{
    "name": "<realistic first name and surname>",
    "age": <integer 1–99>,
    "severity": "<low|medium|critical>",
    "diagnosis": "<specific clinical diagnosis, not just a symptom>",
    "backstory": "<1–2 sentences: what happened and why they came to A&E today, grounded in the time/day>"
  }}
]
An empty array [] is valid if zero patients arrive (e.g. quiet early morning)."""

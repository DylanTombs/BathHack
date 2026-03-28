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
    Build a triage decision prompt for a specific doctor.

    The doctor must choose which waiting patient to treat next.
    Output: JSON {"target_patient_id": int, "reason": str, "confidence": float}
    """
    if not ctx.available_patients:
        # Shouldn't happen if trigger guard is correct, but be safe
        return (
            "No patients are currently waiting for assignment. "
            'Respond with: {"target_patient_id": -1, "reason": "No patients waiting", "confidence": 1.0}'
        )

    patients_str = "\n".join([
        f"  - Patient #{p.id} | {p.name}"
        f" | Severity: {p.severity}"
        f" | Condition: {p.condition}"
        f" | Diagnosis: {p.diagnosis}"
        f" | Waiting: {p.wait_time_ticks} ticks"
        f" | Age: {p.age}"
        f" | Location: {p.location}"
        for p in ctx.available_patients
    ])

    ward_status_lines = []
    if ctx.icu_is_full:
        ward_status_lines.append("  ⚠ ICU is FULL — no escalation possible")
    if ctx.general_ward_is_full:
        ward_status_lines.append("  ⚠ General ward is FULL — beds unavailable")
    if not ward_status_lines:
        ward_status_lines.append("  All wards have capacity available")
    ward_status = "\n".join(ward_status_lines)

    critical_count = sum(1 for p in ctx.available_patients if p.severity == "critical")
    urgency_note = (
        f"  ⚠ {critical_count} CRITICAL patient(s) require immediate attention!"
        if critical_count > 0
        else "  No critical patients in queue"
    )

    return f"""You are Dr. {ctx.doctor.name} ({ctx.doctor.specialty} specialist) at tick {ctx.current_tick}.

HOSPITAL STATUS:
{ward_status}
{urgency_note}
  Your workload: {ctx.doctor.workload}
  Your current patient count: {len(ctx.doctor.assigned_patient_ids)} / {ctx.doctor.capacity}
  Total decisions made this session: {ctx.doctor.decisions_made}

PATIENTS WAITING FOR ASSIGNMENT ({len(ctx.available_patients)} total):
{patients_str}

CLINICAL DECISION REQUIRED:
Choose exactly one patient to treat next. Apply standard triage principles:
- Prioritise critical severity over medium over low
- For equal severity, longer waiting time should take precedence
- Consider ICU availability when choosing where to assign

Respond with valid JSON only — no commentary, no markdown fences:
{{"target_patient_id": <integer id from list above>, "reason": "<one concise clinical sentence>", "confidence": <0.0-1.0>}}"""


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
- Critical patients without treatment for >4 ticks should be marked "worsening"
- Patients under effective treatment for ≥3 ticks may improve to "stable" or "improving"
- High ward occupancy (>90%) worsens outcomes due to reduced care quality
- Only escalate severity if clinical signs justify it
- Use null for new_severity if severity is unchanged

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

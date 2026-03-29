"""
ReportGenerator — produces an AI-written analysis of a completed simulation run.

Uses the Anthropic client directly (consistent with the project stack).
Model is configurable via REPORT_LLM_MODEL env var.
Falls back to a plain-text template report if the LLM call fails.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.report_data import SimulationReport

logger = logging.getLogger(__name__)


class AnthropicReportClient:
    """
    Thin async wrapper around the Anthropic messages API.
    Uses a large token budget (3000) since this is a one-shot call.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self.model = model
        try:
            import anthropic  # noqa: F401
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            import anthropic as _anthropic
            self._client = _anthropic.AsyncAnthropic(api_key=api_key)
            self._available = True
        except ImportError:
            logger.warning(
                "anthropic package not installed — report will use fallback template"
            )
            self._client = None
            self._available = False

    async def generate(self, prompt: str) -> str:
        """Call the Anthropic API and return the response text, or '' on failure."""
        if not self._available or self._client is None:
            return ""
        try:
            message = await self._client.messages.create(
                model=self.model,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text if message.content else ""
        except Exception as exc:
            logger.error("Anthropic report generation failed: %s", exc)
            return ""


class ReportGenerator:
    """
    Orchestrates report generation: builds the prompt, calls the LLM,
    and falls back to a template string on failure.
    """

    def __init__(self, model: str | None = None) -> None:
        resolved_model = model or os.getenv(
            "REPORT_LLM_MODEL", "claude-haiku-4-5-20251001"
        )
        self._client = AnthropicReportClient(resolved_model)

    async def generate(self, report: "SimulationReport") -> str:
        """Return the LLM-written analysis, or a template fallback."""
        from llm.prompts import build_report_prompt
        prompt = build_report_prompt(report)
        result = await self._client.generate(prompt)
        if not result:
            return _fallback_report(report)
        return result


# ── Fallback template ─────────────────────────────────────────────────────────

def _fallback_report(report: "SimulationReport") -> str:
    """Plain-text summary used when the LLM is unavailable."""
    lines = [
        "# Hospital Simulation Report",
        "",
        "## Executive Summary",
        f"The simulation ran for {report.total_ticks} ticks. "
        f"{report.total_arrived} patients arrived; "
        f"{report.total_discharged} were discharged and {report.total_deceased} died "
        f"(mortality rate: {report.final_mortality_rate_pct:.1f}%).",
        "",
        "## Headline Statistics",
        f"- Patients arrived: {report.total_arrived}",
        f"- Discharged: {report.total_discharged}",
        f"- Deceased: {report.total_deceased}",
        f"- Mortality rate: {report.final_mortality_rate_pct:.1f}%",
        f"- Avg wait time: {report.avg_wait_time_ticks:.1f} ticks",
        f"- Avg treatment time: {report.avg_treatment_time_ticks:.1f} ticks",
        f"- Peak queue: {report.peak_queue_length}",
        f"- Peak ICU occupancy: {report.peak_icu_occupancy_pct:.1f}%",
        f"- Peak general ward occupancy: {report.peak_general_occupancy_pct:.1f}%",
        "",
        "## Phases",
    ]
    for p in report.phases:
        lines.append(
            f"- **{p.label}** (ticks {p.start_tick}–{p.end_tick}): "
            f"avg queue={p.avg_queue:.1f}, "
            f"ICU={p.avg_icu_pct:.1f}%, "
            f"general={p.avg_general_pct:.1f}%, "
            f"discharges={p.discharges}, deaths={p.deaths}"
        )
    if not report.phases:
        lines.append("- No distinct phases recorded.")

    lines += ["", "## Interventions"]
    for r in report.interventions:
        lines.append(f"- Tick {r.tick}: **{r.intervention_type}** — {r.detail}")
    if not report.interventions:
        lines.append("- No user interventions recorded.")

    return "\n".join(lines)

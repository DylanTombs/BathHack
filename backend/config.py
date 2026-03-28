"""
Backend configuration loaded from environment variables.
Copy .env.example to .env and fill in your ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    llm_model: str
    tick_interval_seconds: float
    max_beds_general: int
    max_beds_icu: int
    initial_doctors: int
    log_level: str


def load_config() -> Config:
    """
    Load configuration from environment variables.
    Raises ValueError if ANTHROPIC_API_KEY is not set.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )

    return Config(
        anthropic_api_key=api_key,
        llm_model=os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001"),
        tick_interval_seconds=float(os.environ.get("TICK_INTERVAL_SECONDS", "1.0")),
        max_beds_general=int(os.environ.get("MAX_BEDS_GENERAL", "20")),
        max_beds_icu=int(os.environ.get("MAX_BEDS_ICU", "5")),
        initial_doctors=int(os.environ.get("INITIAL_DOCTORS", "4")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )

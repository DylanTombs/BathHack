"""
Configuration loader for the Hospital Simulation backend.
Reads from environment variables (with .env support via python-dotenv).
"""
from __future__ import annotations
import os
import logging
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    openrouter_api_key: str
    llm_model: str
    tick_interval_seconds: float
    max_beds_general: int
    max_beds_icu: int
    initial_doctors: int
    arrival_rate_per_tick: float
    log_level: str


def load_config() -> Config:
    cfg = Config(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "openai/gpt-4o-mini"),
        tick_interval_seconds=float(os.getenv("TICK_INTERVAL_SECONDS", "1.0")),
        max_beds_general=int(os.getenv("MAX_BEDS_GENERAL", "20")),
        max_beds_icu=int(os.getenv("MAX_BEDS_ICU", "5")),
        initial_doctors=int(os.getenv("INITIAL_DOCTORS", "4")),
        arrival_rate_per_tick=float(os.getenv("ARRIVAL_RATE_PER_TICK", "1.5")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
    logging.basicConfig(level=getattr(logging, cfg.log_level, logging.INFO))
    return cfg

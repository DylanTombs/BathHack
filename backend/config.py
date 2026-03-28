import os
from dataclasses import dataclass


@dataclass
class Config:
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    tick_interval_seconds: float = 1.0
    max_beds_general: int = 20
    max_beds_icu: int = 5
    initial_doctors: int = 4
    log_level: str = "INFO"
    arrival_rate_per_tick: float = 1.5   # Poisson mean


def load_config() -> Config:
    return Config(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
        tick_interval_seconds=float(os.getenv("TICK_INTERVAL_SECONDS", "1.0")),
        max_beds_general=int(os.getenv("MAX_BEDS_GENERAL", "20")),
        max_beds_icu=int(os.getenv("MAX_BEDS_ICU", "5")),
        initial_doctors=int(os.getenv("INITIAL_DOCTORS", "4")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        arrival_rate_per_tick=float(os.getenv("ARRIVAL_RATE_PER_TICK", "1.5")),
    )

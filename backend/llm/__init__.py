"""
LLM Integration Layer — Agent 2

Public exports for use by Agent 1 (simulation engine) and Agent 3 (backend API):

    from llm import AnthropicLLMClient, LLMTriggerGuard, ExplainerService

Integration pattern (Agent 3 post-merge):
    llm_client = AnthropicLLMClient(config.anthropic_api_key, config.llm_model)
    explainer  = ExplainerService(llm_client)
    engine     = SimulationEngine(config, llm_callback=llm_client)
"""

from llm.client import AnthropicLLMClient
from llm.explainer import ExplainerService
from llm.triggers import LLMTriggerGuard

__all__ = [
    "AnthropicLLMClient",
    "LLMTriggerGuard",
    "ExplainerService",
]

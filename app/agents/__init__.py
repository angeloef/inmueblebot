"""
Módulo de agentes del bot.
"""
from app.agents.llm_router import LLMRouter, llm_router, LLMResponse
from app.agents.real_estate_agent import RealEstateAgent, real_estate_agent

__all__ = [
    "LLMRouter",
    "llm_router",
    "LLMResponse",
    "RealEstateAgent",
    "real_estate_agent",
]

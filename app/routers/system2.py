"""System 2 router — delegates to the existing LLM agent loop (Phase 5).

Now accepts an optional belief context prompt for multi-turn awareness.
"""

from app.agents.s2_agent import process_message
from app.agents.schemas import CSAgentResponse as AgentResponse


async def route_s2(
    message: str, session_id: str, context_prompt: str = ""
) -> AgentResponse:
    """Forward to the full LLM agent loop with optional belief context.

    The context_prompt injects accumulated conversation state
    (criteria, intents, selection) into the LLM system prompt.
    """
    return await process_message(
        message=message,
        session_id=session_id,
        context_prompt=context_prompt,
    )

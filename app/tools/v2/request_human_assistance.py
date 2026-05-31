"""Request handoff to a human agent.

When called, the bot signals that a human agent should take over. The
v2_adapter automatically pauses the bot when this tool is in tools_called.
"""

from loguru import logger

from app.core.identity import get_current_contact


async def request_human_assistance(
    reason: str = "",
    message: str = "",
) -> str:
    """Signal that the user needs a human agent. Bot will be auto-paused by v2_adapter.

    Args:
        reason: Why a human is needed (for the agent's context).
        message: Custom message to include in the handoff confirmation.
    """
    contact = get_current_contact()
    identity = contact.get("bsuid") or contact.get("phone") or "unknown"
    logger.info(f"[request_human_assistance] Handoff requested — identity={identity} reason={reason!r}")

    base = (
        "Entendido. Te estoy conectando con uno de nuestros agentes. "
        "En breve alguien se va a comunicar con vos para ayudarte personalmente."
    )
    if message:
        return f"{message}\n\n{base}"
    return base

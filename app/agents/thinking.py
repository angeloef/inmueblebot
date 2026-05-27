"""Hidden CoT reasoning — internal thought process never shown to user (Phase 9).

Uses a lightweight LLM call with reasoning_effort='low' to generate
an internal monologue that guides planning and action.
"""

from app.agents.cs_llm_client import get_client
from app.core.config import get_settings
settings = get_settings()

THINKING_PROMPT = """Sos un agente interno de razonamiento. Tu trabajo es analizar el mensaje del usuario
y generar un plan mental PRIVADO. El usuario NUNCA verá esto.

Analizá:
1. ¿Qué quiere realmente el usuario?
2. ¿Qué información tengo ya? (criterios de búsqueda, selecciones previas)
3. ¿Qué herramientas necesito usar y en qué orden?
4. ¿Qué espero obtener de cada herramienta?
5. ¿Qué podría salir mal? (plan B)

Respondé en formato conciso, estilo bullet-point mental. Máximo 150 palabras."""


async def think(
    message: str,
    context_prompt: str = "",
    belief_summary: str = "",
) -> str:
    """Generate hidden CoT reasoning for the current turn.

    Args:
        message: The user's message.
        context_prompt: Accumulated belief state context.
        belief_summary: Compact belief summary.

    Returns:
        Internal reasoning text (hidden from user).
    """
    client = get_client()

    full_context = THINKING_PROMPT
    if belief_summary:
        full_context += f"\n\nEstado actual de la conversación:\n{belief_summary}"
    if context_prompt:
        full_context += f"\n\nContexto adicional:\n{context_prompt[:500]}"
    full_context += f"\n\nMensaje del usuario: \"{message}\""

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": full_context}],
            temperature=0.2,
            max_completion_tokens=256,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return ""


def summarize_thinking(thinking: str) -> str:
    """Extract a one-line summary of the thinking for logging."""
    if not thinking:
        return "(no thinking)"
    lines = thinking.strip().split("\n")
    first = lines[0].strip().lstrip("-#•*1234567890. ")
    return first[:120]

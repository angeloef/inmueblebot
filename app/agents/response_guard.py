"""Response guard — an LLM critic that reviews the bot's candidate response BEFORE
it is sent to the user.

Goal: catch ROUTING / CONTENT mismatches that slip past the deterministic router
(e.g. an informational question answered with a property list, a greeting answered
with office hours, an off-topic or fabricated answer) and re-route to the correct
specialist so the user receives the right answer.

Design (active + selective):
  - Runs ONLY on LLM-generated informational responses (search / knowledge / rapport /
    negotiator / FAQ / refinement). Deterministic shortcuts and active booking flows are
    skipped by the caller — they are correct by construction or too stateful to
    regenerate safely.
  - Uses the fast/cheap CLASSIFY model with a tight, structured verdict.
  - Conservative: on any uncertainty or error it returns ok=true (fail-open — it must
    NEVER block a send or loop).
"""

import json

from loguru import logger

from app.agents.cs_llm_client import get_client, get_model, LLMRole

# Specialists the guard may suggest re-routing to.
VALID_SPECIALISTS = {"search", "knowledge", "rapport", "negotiator", "scheduling"}

_GUARD_SYSTEM = """Sos un revisor de calidad de un chatbot inmobiliario de Oberá (Misiones, Argentina).
Recibís el ÚLTIMO mensaje del usuario y la RESPUESTA que el bot está por enviarle.
Tu ÚNICA tarea: decidir si la respuesta REALMENTE atiende lo que el usuario pidió.

Marcá la respuesta como INCORRECTA (ok=false) SOLO si hay un error CLARO, por ejemplo:
- El usuario hizo una pregunta INFORMATIVA (requisitos, garantía, garante, contrato,
  seña, expensas, comisión, horarios, cómo es el proceso para alquilar/comprar) y el bot
  respondió con una LISTA de propiedades o una búsqueda en vez de la información.
- El usuario solo SALUDÓ o hizo charla y el bot respondió con datos de oficina, una lista
  de propiedades o un agendamiento que nadie pidió.
- El usuario pidió BUSCAR o VER propiedades y el bot respondió con una FAQ genérica sin
  mostrar nada.
- El usuario pidió DETALLES o FOTOS de una propiedad y el bot respondió con otra cosa.
- La respuesta afirma haber hecho algo que claramente NO hizo (ej. "ya agendé tu visita"
  sin datos), o está totalmente fuera de tema.

Si la respuesta es razonable, está EN TEMA y atiende el pedido (aunque no sea perfecta) → ok=true.
ANTE LA DUDA, ok=true. No molestes respuestas aceptables.

Especialistas para re-rutear (elegí el correcto si ok=false):
- search: buscar / ver / listar / filtrar propiedades, detalles, fotos.
- knowledge: requisitos, garantías, contratos, horarios, info general del proceso.
- rapport: saludos, charla, o pedido de hablar con una persona.
- negotiator: precio, presupuesto, negociación.
- scheduling: agendar una visita.

Respondé SOLO con un objeto JSON, sin texto extra:
{"ok": true|false, "problema": "<motivo breve o null>", "especialista": "<nombre o null>"}"""


async def evaluate_response(
    user_message: str,
    bot_response: str,
    tools_called: list[str],
    recent_context: str = "",
) -> dict:
    """Judge whether `bot_response` actually addresses `user_message`.

    Returns {"ok": bool, "problema": str|None, "especialista": str|None}.
    Fail-open: any error → {"ok": True, ...} so the send is never blocked.
    """
    if not user_message or not bot_response:
        return {"ok": True, "problema": None, "especialista": None}
    try:
        client = get_client(LLMRole.CLASSIFY)
        user_block = (
            (f"[CONTEXTO RECIENTE]\n{recent_context}\n\n" if recent_context else "")
            + f"[MENSAJE DEL USUARIO]\n{user_message}\n\n"
            + f"[RESPUESTA DEL BOT]\n{bot_response}\n\n"
            + f"[HERRAMIENTAS USADAS]\n{', '.join(tools_called) if tools_called else 'ninguna'}"
        )
        resp = await client.chat.completions.create(
            model=get_model(LLMRole.CLASSIFY),
            messages=[
                {"role": "system", "content": _GUARD_SYSTEM},
                {"role": "user", "content": user_block},
            ],
            max_completion_tokens=150,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"ok": True, "problema": None, "especialista": None}
        ok = bool(data.get("ok", True))
        esp = data.get("especialista")
        if esp not in VALID_SPECIALISTS:
            esp = None
        return {"ok": ok, "problema": data.get("problema"), "especialista": esp}
    except Exception as e:
        logger.warning(f"[Guard] evaluate_response failed (fail-open): {e}")
        return {"ok": True, "problema": None, "especialista": None}

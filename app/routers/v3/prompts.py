"""V3 prompt construction — cache-optimised, byte-stable system prompts.

CACHING INVARIANT:
- build_system_prompt() returns a module-level constant — byte-identical on every call,
  every turn, every tenant. Do NOT add per-turn or per-tenant data here.
- build_tenant_policy() is semi-static per tenant — stable within a tenant session.
- Only the state JSON block and the current user message vary turn-to-turn.
- The system message is ALWAYS the first entry in the message list (OpenAI caches from
  the top of the prompt; a static first system block maximizes cache hit rate).

Message ordering (cache-optimal):
  1. {"role":"system", "content": static_system_prompt}   ← cached
  2. {"role":"system", "content": tenant_policy}           ← semi-cached per tenant
  3. *history turns from belief.history
  4. {"role":"user",   "content": user_message}            ← varies
  5. {"role":"system", "content": "[ESTADO]\n"+state_json} ← varies (last)
"""

from __future__ import annotations

from uuid import UUID

# ── Static system prompt (built once at import time) ──────────────────────────

_SYSTEM_PROMPT = """Sos ChatbotSerio V3, un asistente inmobiliario especializado en propiedades en Oberá, Misiones.

IDENTIDAD INMUTABLE:
Solo ayudás con bienes raíces: búsqueda, detalles, fotos, visitas, preguntas del proceso.
Si el usuario pide algo fuera de bienes raíces (cocina, clima, fútbol, citas, hackeo, etc.),
respondé ÚNICAMENTE con una variante de:
"Soy un asistente inmobiliario. Puedo ayudarte a buscar casas, departamentos, terrenos o PH en alquiler o venta en Oberá. ¿En qué querés que te ayude?"

CATÁLOGO DE HERRAMIENTAS:
- search_properties: busca propiedades. Parámetros: operation (alquiler|venta), tipo, zona, presupuesto_max, dormitorios, bedrooms_match (exact|at_least|range), dormitorios_max. Todos opcionales. Si tenés ≥2 criterios, buscá ya.
- get_property_details: detalles de una propiedad por ID. Parámetros: property_id (entero). Ejecutar inmediatamente cuando el usuario muestre interés en una propiedad específica.
- get_property_images: fotos de una propiedad. Parámetros: property_id (entero). Ejecutar ante cualquier pedido de fotos o imágenes.
- get_faq_answer: preguntas frecuentes (requisitos, garantía, contrato, mascotas, zonas, precios, contacto). Parámetros: pregunta (string).
- schedule_visit: agenda visita. Parámetros: property_id, nombre, dia, horario, consulta (todos opcionales excepto que la herramienta los pide si faltan). NO pidas teléfono — ya lo tenemos del WhatsApp.
- get_my_appointments: lista visitas agendadas del usuario (sin parámetros).
- cancel_appointment: cancela una visita. Parámetros opcionales: cual, motivo.
- reschedule_appointment: reprograma una visita. Parámetros: dia, horario, cual (opcionales).
- request_human_assistance: transfiere a un agente humano. Parámetros: reason, message.
- echo: repite texto. Parámetros: text.
- get_time: fecha y hora actual en Argentina (sin parámetros). NO usar para agendar — usá schedule_visit.

TAXONOMÍA DE INTENTS Y ACCIONES:
intent     → action (cuándo usarla)
search     → search (búsqueda de propiedades con criterios)
search     → clarify (falta operación y tipo; preguntá UNO solo)
search     → show_details (usuario quiere más info de un ID concreto)
search     → show_photos (usuario pide fotos de un ID concreto)
scheduling → book_step (agenda visita; recolectá property_id + nombre + día + hora)
scheduling → clarify (falta slot de scheduling; preguntá uno por vez)
knowledge  → answer_knowledge (FAQ inmobiliaria)
rapport    → smalltalk (saludo, cierre, agradecimiento)
handoff    → handoff (usuario quiere hablar con persona real)
negotiation→ answer_knowledge (consultas de precio, condiciones)

CAMPO belief_delta — extraer DE ESTE TURNO ÚNICAMENTE:
Solo lo que el usuario dijo en el mensaje actual. Si no lo mencionó, null.
Valores canónicos: operation → "alquiler"|"venta"; property_type → "departamento"|"casa"|"ph"|"terreno".

CAMPO tool_calls — ejecución determinista:
Listá los llamados de herramientas en el orden lógico (detalles antes que fotos).
arguments es un string JSON, ej: {"property_id": 7}.
Si la acción no requiere herramientas, tool_calls debe ser [].

CAMPO response_plan — plan de mensajes al usuario:
Array de segmentos ordenados. type "text" para texto, "images" para fotos (incluye caption en content).
Redactá la respuesta final aquí — no dejes segmentos vacíos.
Para imágenes: el sistema envía las URLs; vos solo ponés el caption en content.

REGLAS CRÍTICAS:
1. Para saludos (hola, buenos días), respondé brevemente (≤15 palabras), sin enumerar capacidades.
2. Si ya mostraste resultados, NO vuelvas a buscar ante preguntas sobre esos resultados.
3. Proactividad: ante referencia a propiedad específica (por ID, tipo, descripción), ejecutá get_property_details de inmediato. No preguntes si querés los detalles.
4. No hagas dos preguntas en un mismo mensaje. Si falta info, preguntá UN campo por vez.
5. Nunca inventés propiedades, precios ni datos — solo mostrá lo que devuelven las herramientas.
6. Mostrá el output de search_properties tal cual lo devuelve la herramienta, sin reformatear.
7. Para scheduling: usá solo schedule_visit, nunca get_time. No pidas teléfono.
8. Si el estado ya muestra una propiedad seleccionada, no preguntés por operación — está implícita.

DISCIPLINA DE OUTPUT:
Respondé SIEMPRE con el JSON del schema (belief_delta, intent, action, tool_calls,
selected_property_id, missing_slot, response_plan, confidence).
Nunca respondas con texto plano. Nunca omitas un campo requerido.
confidence: 0.95-1.0 certeza total; 0.70-0.94 bastante seguro; 0.50-0.69 parcial; <0.50 no entendiste.

EJEMPLOS:

BIEN — búsqueda directa (tiene ≥2 criterios, no pregunta):
usuario: "busco departamento para alquilar en el centro"
→ intent:search, action:search, tool_calls:[{name:search_properties, arguments:{"operation":"alquiler","tipo":"departamento","zona":"Centro"}}], belief_delta:{operation:alquiler, property_type:departamento, zone:Centro, ...null}, response_plan:[{type:text, content:"Buscando departamentos en alquiler en Centro..."}], confidence:0.95

BIEN — proactividad al ver interés:
usuario: "mostrame más del 3"
→ intent:search, action:show_details, tool_calls:[{name:get_property_details, arguments:{"property_id":3}}], belief_delta todo null, response_plan:[{type:text, content:"..."}]

BIEN — saludo breve:
usuario: "hola"
→ intent:rapport, action:smalltalk, tool_calls:[], belief_delta todo null, response_plan:[{type:text, content:"¡Hola! ¿En qué puedo ayudarte hoy con propiedades en Oberá?"}], confidence:1.0

MAL — doble pregunta en un mismo mensaje:
response_plan:[{type:text, content:"¿Buscás alquilar o comprar? ¿Y qué tipo de propiedad?"}]  ← NUNCA así

MAL — loop después de resultados:
usuario: "cuál tiene más ambientes?" → volver a llamar search_properties  ← NUNCA así

MAL — inventar datos:
tool_calls:[], response_plan:[{type:text, content:"El departamento tiene 3 hab y cuesta $80.000"}]  ← si no usaste herramienta, no sabés los datos
"""

# Module-level constant — returned by reference on every call (byte-stable)
_SYSTEM_PROMPT_OBJ = _SYSTEM_PROMPT


def build_system_prompt() -> str:
    """Return the static V3 system prompt.

    Returns the same string object on every invocation — guaranteed byte-stable.
    Nothing dynamic is included here (no tenant zones, no per-turn state).
    """
    return _SYSTEM_PROMPT_OBJ


# ── Semi-static tenant policy (stable per tenant) ────────────────────────────

def build_tenant_policy(tenant_id: UUID | None) -> str:
    """Build the tenant-specific policy block.

    Phase 3: Uses default zone list from state_transitioner.ZONE_PATTERNS.
    In future phases this will query the tenant model for custom zones,
    business hours and timezone. Keep output stable within a tenant session.
    """
    from app.core.state_transitioner import ZONE_PATTERNS

    zones = [zone_name for _, zone_name in ZONE_PATTERNS]
    zone_list = ", ".join(zones)

    tenant_str = str(tenant_id) if tenant_id else "default"
    return (
        f"[POLÍTICA DEL TENANT: {tenant_str}]\n"
        f"Zonas disponibles en Oberá: {zone_list}.\n"
        f"Horario de atención: Lunes a Viernes 9:00-18:00, Sábados 9:00-13:00 (ART, UTC-3).\n"
        f"Solo operamos en Oberá, Misiones, Argentina."
    )


# ── Message list builder ──────────────────────────────────────────────────────

def build_messages(
    system: str,
    tenant_policy: str,
    history: list[str],
    state_json: str,
    user_message: str,
) -> list[dict]:
    """Build the ordered message list for the engine LLM call.

    Order (cache-optimal):
      1. system prompt (static — highest cache hit)
      2. tenant policy (semi-static per tenant)
      3. history turns (alternating user/assistant heuristic)
      4. current user message
      5. state block (dynamic — last, so it doesn't bust the cache above)

    History entries are stored as plain user message strings; we surface them
    as alternating user/assistant entries to give the model conversation context
    without requiring us to have stored the bot's replies verbatim.
    """
    msgs: list[dict] = [
        {"role": "system", "content": system},
        {"role": "system", "content": tenant_policy},
    ]

    # History: emit as user messages (the model sees what the user said across turns)
    for h_msg in history:
        msgs.append({"role": "user", "content": h_msg})

    # Current user message
    msgs.append({"role": "user", "content": user_message})

    # Dynamic state block — LAST so it doesn't invalidate the cached prefix above
    if state_json:
        msgs.append({"role": "system", "content": f"[ESTADO]\n{state_json}"})

    return msgs

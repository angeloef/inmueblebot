"""
Agente principal de bienes raíces.
Orquesta la interacción entre LLM, herramientas y memoria.
"""
import json
import asyncio
from typing import Dict, Any, Optional, List
from loguru import logger

from app.agents.llm_router import llm_router, LLMResponse
from app.agents.tools import execute_tool, TOOL_FUNCTIONS
from app.agents.prompts import get_system_prompt, TOOL_DEFINITIONS
from app.agents.router import should_handoff, STAGE_HANDOFF, STAGE_OUT_OF_SCOPE
from app.core.memory import memory_manager
from app.core.state_machine import state_machine, ConversationStateEnum
from app.core.intent import Intent



class RealEstateAgent:
    """
    Agente de bienes raíces con tool calling.
    
    Maneja el flujo completo de conversación:
    1. Carga contexto del usuario desde memoria
    2. Prepara mensajes para el LLM
    3. Ejecuta tool calling con fallback automático (MiniMax → Gemini)
    4. Guarda respuesta en memoria
    5. Actualiza preferencias y lead score
    6. Retorna respuesta estructurada
    """
    
    MAX_TOOL_CALLS = 7  # Multi-intent sequences: search→details→images→schedule + extras
    
    def __init__(self):
        self.llm = llm_router
        self.tools = TOOL_DEFINITIONS
        self._user_locks: dict = {}
    
    def _get_user_lock(self, phone: str) -> asyncio.Lock:
        """Get or create per-user lock to serialize turns."""
        if phone not in self._user_locks:
            self._user_locks[phone] = asyncio.Lock()
        return self._user_locks[phone]
    
    async def process_turn(
        self,
        phone: str,
        user_message: str,
        intent: Intent = None,
        force_agent: bool = False,
        extracted_entities: dict = None
    ) -> Dict[str, Any]:
        """
        Procesa un turno de conversación.
        
        Args:
            phone: Número de teléfono del usuario
            user_message: Mensaje del usuario
            intent: Intent clasificado (opcional)
            force_agent: Forzar uso del agente completo aunque sea un intent simple
        
        Returns:
            dict con:
            - response_text: Texto de respuesta
            - rich_content: Contenido adicional (propiedades, etc.)
            - tools_used: Lista de herramientas usadas
            - next_state: Estado siguiente
        """
        logger.info(f"Agent procesando mensaje de {phone}: {user_message[:50]}...")
        
        async with self._get_user_lock(phone):
            try:
                # Save user message to history FIRST so the LLM sees it in context
                try:
                    await memory_manager.save_message(phone, "user", user_message)
                except Exception as e:
                    logger.warning(f"Error saving user message: {e}")

                try:
                    merged_context = await memory_manager.get_merged_context(phone)
                except Exception as e:
                    logger.warning(f"Error get_merged_context, usando default: {e}")
                    merged_context = {"current_state": "idle", "conversation_stage": "new"}

                try:
                    history = await memory_manager.get_recent_messages(phone, limit=15)
                except Exception as e:
                    logger.warning(f"Error get_recent_messages: {e}")
                    history = []

                user_prefs = merged_context

                # Merge classifier-extracted entities into user_prefs so the
                # system prompt sees them before the first LLM call
                if extracted_entities:
                    for _field in ("location", "budget_min", "budget_max", "bedrooms",
                                   "bathrooms", "operation_type", "property_type"):
                        if extracted_entities.get(_field) is not None and not user_prefs.get(_field):
                            user_prefs[_field] = extracted_entities[_field]
                    logger.info(f"[Agent] Merged classifier entities into user_prefs: {extracted_entities}")

                # Fetch existing appointments for context (prevents time hallucination in rescheduling)
                try:
                    from app.services.appointment_service import appointment_service
                    from uuid import UUID
                    if "user_id" in merged_context and merged_context["user_id"]:
                        uid = UUID(str(merged_context["user_id"]))
                        existing = await appointment_service.get_upcoming_appointments(uid, limit=3)
                        if existing:
                            user_prefs["existing_appointments"] = existing
                            logger.info(f"[Agent] Loaded {len(existing)} existing appointments for {phone}")
                except Exception as e:
                    logger.warning(f"[Agent] Could not load existing appointments: {e}")

                # v2.0: Handoff detection is now handled by the regex router
                # (propose_transition → out_of_scope / human_assistance states)

                # ── v2.0: State-driven routing with regex-first transition proposal ──
                from app.agents.router import propose_transition as _regex_propose
                from app.agents.router import STAGE_OUT_OF_SCOPE, STAGE_HANDOFF, should_handoff

                _current_sm_state = merged_context.get("current_state", "idle")
                _proposed_state, _proposal_conf = _regex_propose(
                    user_message, _current_sm_state, merged_context, history
                )

                if _proposal_conf == "high" and _proposed_state:
                    # Regex router is confident — do the state transition now
                    _transitioned = await state_machine.transition(
                        phone, _current_sm_state, _proposed_state
                    )
                    if _transitioned:
                        _next_state = _proposed_state
                    else:
                        # Illegal transition — fall back to current state
                        _next_state = _current_sm_state
                    logger.info(
                        f"[Agent] v2.0 regex router: {_current_sm_state} -> {_next_state} "
                        f"(conf={_proposal_conf}, transitioned={_transitioned})"
                    )
                else:
                    # Low confidence — keep current state, classifier handles intent
                    _next_state = _current_sm_state
                    logger.info(
                        f"[Agent] v2.0 regex router: staying in {_next_state} (conf={_proposal_conf})"
                    )

                # ── Out-of-scope / handoff: still fast-path these ──
                if _next_state == "out_of_scope":
                    from app.services.handoff_service import handoff_service
                    _reason = "out_of_scope"
                    _message = (
                        "Esto escapa a lo que puedo hacer por acá. "
                        "Te paso con un asesor humano que te va a ayudar mejor. "
                        "Dejame pasarle el contexto de lo que veníamos hablando "
                        "así no tenés que repetir todo."
                    )
                    handoff_result = await handoff_service.trigger_handoff(phone, _reason)
                    return {
                        "response_text": _message,
                        "rich_content": {"action": "handoff_initiated", "reason": _reason},
                        "tools_used": ["request_human_assistance"],
                        "next_state": ConversationStateEnum.HUMAN_ASSISTANCE.value
                    }
                if _next_state == "human_assistance" or should_handoff(merged_context):
                    from app.services.handoff_service import handoff_service
                    _reason = "fail_threshold_reached"
                    _message = (
                        "Veo que estoy teniendo problemas para ayudarte con esto. "
                        "Te paso con un asesor humano que te va a atender mejor. "
                        "Dejame pasarle el contexto de lo que veníamos hablando."
                    )
                    handoff_result = await handoff_service.trigger_handoff(phone, _reason)
                    return {
                        "response_text": _message,
                        "rich_content": {"action": "handoff_initiated", "reason": _reason},
                        "tools_used": ["request_human_assistance"],
                        "next_state": ConversationStateEnum.HUMAN_ASSISTANCE.value
                    }

                # ── v2.0: Gate tools by state ──
                _allowed_tools = state_machine.get_tools_for_state(_next_state)
                if _allowed_tools:
                    _gated_tools = [
                        t for t in self.tools
                        if t["function"]["name"] in _allowed_tools
                    ]
                    logger.info(
                        f"[Agent] v2.0 tool gating: state={_next_state}, "
                        f"allowed={_allowed_tools}, "
                        f"before={len(self.tools)} after={len(_gated_tools)}"
                    )
                else:
                    _gated_tools = self.tools  # STATE_TOOLS empty → no gating (IDLE, OUT_OF_SCOPE)

                # Get last_shown_properties from context for reference
                last_props = merged_context.get("last_shown_properties", [])

                # Check if returning user (has context from previous session but no history yet)
                last_context = merged_context
                has_context = bool(last_context.get("selected_property_id") or last_context.get("last_shown_properties"))
                is_new_session = len(history) == 0

                if has_context and is_new_session:
                    # Inject returning user context
                    user_prefs["is_returning"] = True
                    last_prop = last_context.get("selected_property_id", None)
                    last_props_list = last_context.get("last_shown_properties", [])
                    if last_prop:
                        user_prefs["last_reference"] = last_prop
                    elif last_props_list:
                        # Use the first property title as reference
                        first_prop = last_props_list[0].get("title", "propiedades") if isinstance(last_props_list[0], dict) else str(last_props_list[0])
                        user_prefs["last_reference"] = first_prop
                    logger.info(f"[Agent] Returning user detected for {phone}, last_ref: {user_prefs.get('last_reference')}")

                # Property reference resolution: resolve 'esa', 'el de 2 amb', etc.
                from app.core.hybrid.reference import reference_parser

                if (
                    user_message
                    and not any(id_str in user_message for id_str in ["ID:", "id ", "ID "])
                    and merged_context.get("last_shown_properties")
                ):
                    ref_ctx = {
                        "property_options": merged_context["last_shown_properties"],
                        "selected_property_id": merged_context.get("selected_property_id"),
                    }
                    ref_result = await reference_parser.parse(user_message, ref_ctx)
                    if ref_result.value and ref_result.confidence >= 0.8:
                        logger.info(
                            "[ReferenceParser] User reference %r -> property %s (conf=%.2f, parser=%s)",
                            user_message,
                            ref_result.value,
                            ref_result.confidence,
                            ref_result.parser_used,
                        )
                        merged_context["selected_property_id"] = ref_result.value
                        user_prefs["selected_property_id"] = ref_result.value
                        await memory_manager.update_context_field(
                            phone, "selected_property_id", ref_result.value
                        )

                messages = self._build_messages(
                    user_message=user_message,
                    history=history,
                    user_context=user_prefs,
                    phone=phone,
                    last_shown_properties=last_props if last_props else None,
                    stage=_next_state,
                    capability=None,
                )

                # ── Scheduling nudge: fetch pending scheduling ONCE per turn ──────────────────
                # Used by: (a) start-of-turn LLM nudge, (b) SCHEDULING GUARD skip condition
                try:
                    _turn_pending_sched = await memory_manager.get_pending_scheduling(phone) or {}
                except Exception:
                    _turn_pending_sched = {}

                if _turn_pending_sched.get("active") and _turn_pending_sched.get("property_id"):
                    _tp_pid = _turn_pending_sched.get("property_id")
                    _tp_date = _turn_pending_sched.get("date_str", "")
                    _tp_time = _turn_pending_sched.get("time_str", "")
                    _user_msg_lower_sched = (user_message or "").lower()
                    _is_photo_req = any(kw in _user_msg_lower_sched for kw in ["foto", "imagen", "imag", "ver foto"])
                    if not _is_photo_req:
                        _nudge_parts = [
                            "INSTRUCCION PRIORITARIA: El usuario esta en el flujo de agendamiento.",
                            f"Propiedad seleccionada: ID={_tp_pid}.",
                        ]
                        if _tp_date:
                            _nudge_parts.append(f"Fecha ya proporcionada: '{_tp_date}'.")
                        if _tp_time:
                            _nudge_parts.append(f"Hora ya proporcionada: '{_tp_time}'.")
                        _nudge_parts.extend([
                            "El usuario puede estar dando: una fecha, una hora, su nombre u otro dato requerido.",
                            f"LLAMA schedule_visit(property_id={_tp_pid}, ...) CON LA INFORMACION DISPONIBLE.",
                            "PROHIBIDO confirmar verbalmente sin llamar la herramienta.",
                            "PROHIBIDO volver a mostrar fotos.",
                            "Si el usuario da su nombre, usalo en schedule_visit como contact_name.",
                        ])
                        messages.append({"role": "system", "content": " ".join(_nudge_parts)})
                        logger.info(f"[Agent] 📅 START-OF-TURN scheduling nudge injected for {phone} (pid={_tp_pid})")

                # ── Photo nudge: if user asks for photos with a selected property, force get_property_images ──
                _photo_keywords_turn = ["foto", "imagen", "imag", "ver foto", "mostrar foto", "mira"]
                _user_wants_photos = any(kw in (user_message or "").lower() for kw in _photo_keywords_turn)
                _selected_pid = merged_context.get("selected_property_id")
                if _user_wants_photos and _selected_pid and not _turn_pending_sched.get("active"):
                    _also_wants_sched = any(kw in (user_message or "").lower() for kw in
                        ["agendar", "visita", "coordinar", "reservar", "turno", "cita"])
                    _photo_nudge = (
                        f"INSTRUCCION PRIORITARIA: El usuario quiere ver las fotos de la propiedad ID={_selected_pid}. "
                        f"LLAMA get_property_images(property_id={_selected_pid}) AHORA. "
                        "PROHIBIDO repetir la pregunta '¿Te gustaria ver las fotos?'. El usuario ya respondio que si. "
                    )
                    if _also_wants_sched:
                        _photo_nudge += (
                            "El usuario TAMBIEN quiere agendar una visita. "
                            "Despues de mostrar las fotos, preguntale que dia y horario le viene bien."
                        )
                    messages.append({"role": "system", "content": _photo_nudge})
                    logger.info(f"[Agent] 📷 PHOTO nudge injected for {phone} (pid={_selected_pid}, also_sched={_also_wants_sched})")

                # ── Entities injection: give LLM the classifier entities explicitly ──
                if extracted_entities:
                    _ent_parts = [f"{k}={v}" for k, v in extracted_entities.items() if v is not None]
                    if _ent_parts:
                        messages.append({
                            "role": "system",
                            "content": (
                                f"ENTIDADES EXTRAIDAS DEL MENSAJE: {', '.join(_ent_parts)}. "
                                "Usalas directamente como argumentos en la primera herramienta. "
                                "No le preguntes al usuario datos que ya estan en esta lista."
                            )
                        })
                        logger.info(f"[Agent] Entities injected: {_ent_parts}")

                # ── Multi-intent detection: detect all intents in the message ──────────
                _mi_intents = {}
                _mi_lower = (user_message or "").lower()
                if any(kw in _mi_lower for kw in ["foto", "imagen", "imag", "ver foto"]):
                    _mi_intents["photos"] = "ver las fotos de la propiedad"
                if any(kw in _mi_lower for kw in ["agendar", "visita", "coordinar", "reservar", "turno", "cita"]):
                    _mi_intents["schedule"] = "agendar una visita"
                if any(kw in _mi_lower for kw in ["cancelar", "cancelá", "anular"]):
                    _mi_intents["cancel"] = "cancelar una cita existente"
                if any(kw in _mi_lower for kw in ["comparar", "comparame", "diferencia entre", "cual es mejor", "cuál es mejor"]):
                    _mi_intents["compare"] = "comparar propiedades entre sí"
                if any(kw in _mi_lower for kw in ["busco", "buscar", "mostrame opciones", "hay algo", "buscame", "quiero ver opciones"]):
                    _mi_intents["search"] = "buscar propiedades con criterios"
                if len(_mi_intents) >= 2:
                    _mi_list = "\n".join(f"  - {desc}" for desc in _mi_intents.values())
                    _mi_msg_content = (
                        f"MULTI-INTENT DETECTADO: El usuario quiere {len(_mi_intents)} cosas:\n"
                        f"{_mi_list}\n"
                        "Ejecutalas en orden logico con las herramientas necesarias. "
                        "NO te detengas ni hagas preguntas intermedias si ya tenes la informacion suficiente. "
                        "Completa TODAS las acciones antes de responder."
                    )
                    messages.append({"role": "system", "content": _mi_msg_content})
                    logger.info(f"[Agent] Multi-intent: {list(_mi_intents.keys())}")

                tools_used = []
                response_text = ""
                rich_content = {}
                cumulative_tokens = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}

                reschedule_failures = 0
                for iteration in range(self.MAX_TOOL_CALLS):
                    break_out = False
                    # v2.0: Use state-gated tools
                    tools_count = len(_gated_tools) if _gated_tools else 0

                    logger.info(f"[Agent] Iteration {iteration + 1}: Sending {tools_count} tools to LLM")

                    llm_response = await self.llm.ainvoke(
                        messages=messages,
                        tools=_gated_tools,
                        temperature=0.7,
                        structured_response=True,  # v2.0: enforce AgentResponse schema
                    )

                    # Token usage logging
                    if llm_response.usage:
                        u = llm_response.usage
                        prompt_t = u.get("prompt_tokens", u.get("input_tokens", "?"))
                        completion_t = u.get("completion_tokens", u.get("output_tokens", "?"))
                        total_t = u.get("total_tokens", u.get("total", "?"))
                        logger.info(
                            f"[Tokens] phone={phone[-4:]} | provider={llm_response.provider} | "
                            f"prompt={prompt_t} | completion={completion_t} | total={total_t}"
                        )
                        if isinstance(total_t, (int, float)):
                            cumulative_tokens["prompt"] += prompt_t if isinstance(prompt_t, (int, float)) else 0
                            cumulative_tokens["completion"] += completion_t if isinstance(completion_t, (int, float)) else 0
                            cumulative_tokens["total"] += total_t
                            cumulative_tokens["calls"] += 1

                    # Log tool call results
                    if llm_response.has_tool_calls:
                        tool_names = [tc.name for tc in llm_response.tool_calls]
                        logger.info(f"[Agent] ✓ Tool calls made: {tool_names}")
                    else:
                        logger.info(f"[Agent] No tools called (provider: {llm_response.provider})")

                    if not llm_response.has_tool_calls:
                        # v2.0: Use structured AgentResponse for text responses
                        if llm_response.structured is not None:
                            sr = llm_response.structured
                            logger.info(
                                f"[Agent] v2.0 structured: action={sr.action} "
                                f"confidence={sr.confidence:.2f}"
                            )
                            if sr.action == "respond":
                                # v2.0: Progressive escalation based on confidence
                                _base_response = sr.response or llm_response.content or ""
                                if sr.confidence < 0.5:
                                    # Very low confidence — handoff with context
                                    logger.warning(
                                        f"[Agent] Low confidence ({sr.confidence:.2f}) — escalating to human"
                                    )
                                    from app.services.handoff_service import handoff_service
                                    handoff_result = await handoff_service.trigger_handoff(
                                        phone, "low_confidence"
                                    )
                                    response_text = handoff_result.get(
                                        "message",
                                        "Te paso con un asesor humano que te va a ayudar mejor."
                                    )
                                elif sr.confidence < 0.7:
                                    # Moderate confidence — ask clarifying question instead
                                    _question = sr.question or "¿Podrías darme más detalles?"
                                    logger.info(
                                        f"[Agent] Moderate confidence ({sr.confidence:.2f}) — asking clarification"
                                    )
                                    response_text = _question
                                elif sr.confidence < 0.9:
                                    # Good but not great — append confirmation prompt
                                    response_text = _base_response + "\n\n¿Entendí bien tu consulta?"
                                    logger.info(
                                        f"[Agent] Good confidence ({sr.confidence:.2f}) — confirming with user"
                                    )
                                else:
                                    # High confidence — respond autonomously
                                    response_text = _base_response
                                break
                            elif sr.action == "ask_question":
                                response_text = sr.question or sr.response or llm_response.content or ""
                                break
                            # action="tool_call" with no native tool_calls: fall through
                            # to check if the structured tool_calls list has content
                            if sr.tool_calls:
                                # Convert structured tool_calls to native format
                                from app.agents.llm_router import ToolCall as TCR
                                llm_response.tool_calls = [
                                    TCR(name=tc.name, arguments=tc.arguments)
                                    for tc in sr.tool_calls
                                ]
                                # Don't break — fall through to tool execution below
                            else:
                                response_text = sr.response or llm_response.content or ""
                                break

                        # v2.0: Anti-hallucination guard (simplified — structured output
                        # makes "voy a buscar" patterns impossible. Only check intent mismatch.)
                        if not response_text:
                            search_was_called = any(
                                "search_properties" in t or "recommend_properties" in t
                                for t in tools_used
                            )
                            if intent == Intent.PROPERTY_SEARCH and not search_was_called:
                                logger.warning(
                                    "[Agent] PROPERTY_SEARCH intent but no search tool called "
                                    "— blocking potential hallucination"
                                )
                                response_text = (
                                    "No encontré propiedades disponibles con esos criterios "
                                    "en este momento. Podés intentar con otros filtros o "
                                    "contactar a un agente."
                                )
                            else:
                                response_text = llm_response.content or ""
                        break

                    # PHASE 1.5: Execute tool calls
                    for tool_call in llm_response.tool_calls:
                        tool_name = tool_call.name
                        tool_args = tool_call.arguments

                        logger.info(f"Tool call: {tool_name} con args: {tool_args}")
                        tools_used.append(tool_name)

                        # v2.0: Property ID guard and Scheduling guard REMOVED.
                        # State-gated tools (Phase 1) prevent the LLM from calling
                        # schedule_visit in non-scheduling states, and structured
                        # output (Phase 2) prevents hallucinated property IDs.

                        tool_result = await execute_tool(
                            tool_name=tool_name,
                            arguments=tool_args,
                            phone=phone
                        )

                        # v2.0: Typed tool result — extract user_message and JSON for LLM
                        _result_user_msg = getattr(tool_result, 'user_message', str(tool_result))
                        _result_json = tool_result.to_json() if hasattr(tool_result, 'to_json') else str(tool_result)

                        # SHORT-CIRCUIT: if tool result IS the final answer, skip remaining LLM iterations
                        if hasattr(tool_result, 'user_message'):
                            _umsg = _result_user_msg
                            if "<!--CONFIRMED:" in _umsg:
                                response_text = _umsg
                                logger.info(f"[Agent] Short-circuit: {tool_name} succeeded with confirmation, using result directly")
                                break_out = True
                                break
                            if tool_name == "cancel_appointment" and "Cita Cancelada" in _umsg:
                                response_text = _umsg
                                logger.info(f"[Agent] Short-circuit: {tool_name} succeeded, using confirmation directly")
                                break_out = True
                                break

                        # Reschedule failure counter: max 3 consecutive failures
                        if tool_name == "reschedule_appointment":
                            _umsg = _result_user_msg
                            if "<!--CONFIRMED:" not in _umsg:
                                reschedule_failures += 1
                                logger.warning(
                                    f"[Agent] reschedule_appointment failed ({reschedule_failures}/3): "
                                    f"no CONFIRMED in result"
                                )
                                if reschedule_failures >= 3:
                                    response_text = "Lo siento, estoy teniendo dificultades técnicas con la reprogramación. Por favor intentá de nuevo más tarde o contactá a un asesor."
                                    logger.warning("[Agent] Reschedule failure limit reached (3) — breaking out")
                                    break_out = True
                                    break
                            else:
                                reschedule_failures = 0

                        # Detect tool loops
                        if len(tools_used) >= 2:
                            last_two = tools_used[-2:]
                            if last_two[0] == last_two[1]:
                                logger.warning(f"[Agent] Loop detected: same tool called twice: {last_two[0]}. Breaking.")
                                if last_two[0] in ("schedule_visit", "reschedule_appointment", "cancel_appointment"):
                                    _umsg = _result_user_msg
                                    if "<!--CONFIRMED:" in _umsg or "Cita Reprogramada" in _umsg or "Cita Cancelada" in _umsg or "Cita Agendada" in _umsg:
                                        response_text = _umsg
                                        logger.info(f"[Agent] Scheduling tool {last_two[0]} succeeded despite loop — confirmation used")
                                    else:
                                        response_text = "Lo siento, estoy teniendo dificultades técnicas con la reprogramación. Por favor intentá de nuevo más tarde o contactá a un asesor."
                                        logger.info(f"[Agent] Scheduling tool {last_two[0]} failed in loop — breaking outer loop too")
                                    break_out = True
                                    break
                                break

                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call_{iteration}",
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(tool_args)
                                    }
                                }
                            ]
                        })

                        messages.append({
                            "role": "tool",
                            "name": tool_name,
                            "tool_call_id": f"call_{iteration}",
                            "content": _result_json  # v2.0: structured JSON for LLM
                        })

                        # ── v2.0 Plan B: Contextual next-step guidance ──
                        # Simplified — tool results carry structured data (total_count, status, etc.)
                        if tool_name == "search_properties":
                            _n_results = getattr(tool_result, 'total_count', 0)
                            _pt = tool_args.get("property_type", "").lower()

                            if _n_results == 0:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "No se encontraron propiedades con esos criterios. "
                                        "Ofrecele alternativas al usuario: ajustar zona, presupuesto, "
                                        "o tipo de propiedad."
                                    )
                                })
                            else:
                                _plural_map = {
                                    "terreno": ("terrenos", "los"), "casa": ("casas", "las"),
                                    "departamento": ("departamentos", "los"), "ph": ("PH", "los"),
                                }
                                _noun, _art = _plural_map.get(_pt, ("propiedades", "las"))
                                _loc = tool_args.get("location", "")
                                _header = (
                                    f"Estos son {_art} {_noun} que tenemos en {_loc}:"
                                    if _loc else f"Estos son {_art} {_noun} que tenemos disponibles:"
                                )
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        f"El tool result contiene {_n_results} propiedades en structured JSON. "
                                        f"Usa los datos del tool result para responder. "
                                        f"Header sugerido: '{_header}'. "
                                        f"Cerrando sugerido: 'Queres mas informacion de alguno de estos {_noun}?'"
                                    )
                                })
                        elif tool_name == "get_property_details":
                            _u_lower = (user_message or "").lower()
                            _wants_photos = any(kw in _u_lower for kw in ["foto", "imagen", "imag"])
                            _wants_visit  = any(kw in _u_lower for kw in ["visita", "agendar", "coordinar", "reservar"])
                            _pid_det = tool_args.get("property_id", "")
                            if _wants_photos and _wants_visit:
                                _follow_up = (
                                    f"El usuario ya pidio FOTOS y VISITA. "
                                    f"Llama get_property_images(property_id={_pid_det}) ahora. "
                                    "Luego pregunta dia y horario para schedule_visit."
                                )
                            elif _wants_photos:
                                _follow_up = f"El usuario ya pidio las fotos. Llama get_property_images(property_id={_pid_det}) AHORA."
                            elif _wants_visit:
                                _follow_up = "El usuario ya quiere coordinar visita. Preguntale dia y horario directamente."
                            else:
                                _follow_up = "Presenta los datos y pregunta si quiere ver fotos o coordinar una visita."
                            messages.append({
                                "role": "system",
                                "content": (
                                    "Acabas de recibir los DATOS REALES de la propiedad en el tool result (structured JSON). "
                                    f"Usa EXACTAMENTE esos datos. {_follow_up}"
                                )
                            })
                        elif tool_name == "compare_properties":
                            messages.append({
                                "role": "system",
                                "content": (
                                    "Mostraste una comparación de propiedades. "
                                    "Preguntale al usuario cuál le interesa más "
                                    "para pasarle los detalles."
                                )
                            })
                        elif tool_name == "get_faq_answer":
                            _faq_result = str(tool_result) if tool_result else ""
                            if not _faq_result.strip() or "no tengo información" in _faq_result.lower() or _faq_result.strip() in ("{}", "[]"):
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "No tengo información sobre esa consulta en mi base de datos. "
                                        "Decile al usuario que no tengo ese dato y ofrecele ayuda "
                                        "con propiedades o visitas. "
                                        "NO inventes una respuesta."
                                    )
                                })
                            else:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "Acabás de recibir la respuesta de FAQ en el tool result de arriba. "
                                        "Usá ESA información para responder la pregunta del usuario. "
                                        "NO digas 'Respondiste una pregunta frecuente' — simplemente dale la respuesta. "
                                        "Después de responder, preguntale si le queda alguna duda. "
                                        "Ej: '¿Te queda alguna duda o quisieras consultar algo más?'"
                                    )
                                })
                        elif tool_name == "cancel_appointment":
                            if "Cita Cancelada" in str(tool_result) or "<!--CONFIRMED:" in str(tool_result):
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "La cita se canceló con éxito. Confirmale al usuario "
                                        "y preguntale si necesita algo más. "
                                        "Si dice que no, despedite cordialmente."
                                    )
                                })
                            else:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "No se pudo cancelar la cita. Informale al usuario "
                                        "y ofrecelé intentar de nuevo o contactar a un asesor humano."
                                    )
                                })
                        elif tool_name in ("schedule_visit", "reschedule_appointment") and "CONFIRMED" in str(tool_result):
                            messages.append({
                                "role": "system",
                                "content": (
                                    "La cita se agendó con éxito. Confirmale al usuario "
                                    "los detalles (día y hora) y preguntale si necesita "
                                    "algo más. Si dice que no, despedite cordialmente. "
                                    "Ej: 'Cita Agendada. [día] a las [hora]. Te esperamos, cualquier cosa avisanos.'"
                                )
                            })
                        elif tool_name in ("schedule_visit", "reschedule_appointment"):
                            # Scheduling was rejected (Sunday, off-hours, etc.)
                            _sched_result = str(tool_result).lower()
                            if "necesito tu nombre" in _sched_result or "nombre" in _sched_result:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "El sistema necesita el nombre del usuario. "
                                        "Preguntale su nombre y apellido cordialmente. "
                                        "NO le preguntes día u horario de nuevo — esos datos ya están registrados."
                                    )
                                })
                            elif "domingo" in _sched_result or "fuera de horario" in _sched_result or "no disponible" in _sched_result:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "El horario no está disponible. Ofrecele 2-3 alternativas al usuario "
                                        "(lunes a sábado de 9 a 18hs). "
                                        "NO repitas que el horario no funciona — pasá directo a soluciones."
                                    )
                                })

                        # ── Fail counter: track tool failures for handoff detection ──
                        _result_str = str(tool_result) if tool_result else ""
                        _is_empty_result = not _result_str.strip() or _result_str.strip() in ("{}", "[]", '""', "''")
                        _is_error = "error" in _result_str.lower() or "no se pudo" in _result_str.lower()
                        _is_no_results = "no tengo" in _result_str.lower() or "no encontr" in _result_str.lower() or "sin resultados" in _result_str.lower()
                        _is_scheduling_rejected = tool_name in ("schedule_visit", "reschedule_appointment") and "CONFIRMED" not in _result_str and "Cita Cancelada" not in _result_str and "Cita Agendada" not in _result_str and "Cita Reprogramada" not in _result_str

                        if _is_empty_result or _is_error or _is_no_results or _is_scheduling_rejected:
                            _capability = tool_name.replace("get_", "").replace("recommend_", "").split("_")[0]
                            _fail_key = f"{_capability}_fail_count"
                            merged_context[_fail_key] = merged_context.get(_fail_key, 0) + 1
                            logger.info(f"[Agent] {tool_name} failed — {_fail_key}={merged_context[_fail_key]}")
                            # Persist to memory
                            try:
                                await memory_manager.update_context_field(phone, _fail_key, merged_context[_fail_key])
                            except Exception:
                                pass
                        else:
                            # Reset fail count on success
                            _capability = tool_name.replace("get_", "").replace("recommend_", "").split("_")[0]
                            _fail_key = f"{_capability}_fail_count"
                            if merged_context.get(_fail_key, 0) > 0:
                                merged_context[_fail_key] = 0
                                try:
                                    await memory_manager.update_context_field(phone, _fail_key, 0)
                                except Exception:
                                    pass

                        if "search_properties" in tool_name or "recommend_properties" in tool_name:
                            new_rich = self._extract_rich_content(tool_args, tool_result)
                            # Preserve images from previous get_property_images calls
                            existing_images = rich_content.get("images", [])
                            if existing_images:
                                new_rich["images"] = existing_images
                            elif new_rich.get("properties"):
                                # Extract images from property list if available
                                for prop in new_rich["properties"]:
                                    if prop.get("images"):
                                        new_rich["images"] = prop["images"]
                                        break
                            rich_content = new_rich

                            # Save last_shown_properties for context (compressed: id + title only)
                            last_props = rich_content.get("properties", [])
                            if last_props:
                                compressed = [
                                    {"id": p.get("id", p.get("property_id", "N/A")), "title": p.get("title", "N/A")}
                                    for p in last_props
                                ]
                                logger.info(f"[Agent] Saving {len(compressed)} properties to context (compressed to id+title)")
                                # Save to memory for next turn
                                try:
                                    await memory_manager.update_context_field(
                                        phone,
                                        "last_shown_properties",
                                        compressed
                                    )
                                except Exception as e:
                                    logger.warning(f"[Agent] Could not save last_shown_properties: {e}")

                        if "get_property_images" in tool_name:
                            new_rich = self._extract_rich_content(tool_args, tool_result)
                            # Preserve images from both current and previous rich_content
                            existing_images = rich_content.get("images", [])
                            new_images = new_rich.get("images", [])
                            if existing_images:
                                new_rich["images"] = existing_images + new_images
                            rich_content = new_rich
                            # Check if user also asked to schedule — push LLM to call schedule_visit next
                            _user_msg_lower = (user_message or "").lower()
                            _sched_keywords = ["coordinar", "visita", "agendar", "reservar", "turno", "cita"]
                            _photo_keywords = ["foto", "imagen", "imag", "ver foto", "mira", "mostrar"]
                            _asked_for_schedule = any(kw in _user_msg_lower for kw in _sched_keywords)
                            _asked_for_photos = any(kw in _user_msg_lower for kw in _photo_keywords)
                            _images_found = bool(new_rich.get("images"))
                            # Check if there is a pending scheduling context from a previous turn
                            try:
                                _pending_sched = await memory_manager.get_pending_scheduling(phone) or {}
                            except Exception:
                                _pending_sched = {}
                            _pending_prop = str(_pending_sched.get("property_id", "")) if isinstance(_pending_sched, dict) else ""
                            logger.info(f"[Agent] 🔍 pending_sched={_pending_sched!r}, _pending_prop={_pending_prop!r}")
                            if _asked_for_schedule:
                                _selected = merged_context.get("selected_property_id", tool_args.get("property_id", ""))
                                if _selected:
                                    # Extract date/time already given in the user message
                                    import re as _re
                                    _day_rx = r'\b(hoy|ma[nñ]ana|pasado\s+ma[nñ]ana|lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)\b'
                                    _time_rx = r'a\s+las?\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|hs|h)?)|(\d{1,2}(?::\d{2})?\s*(?:am|pm|hs|h))\b'
                                    _day_m  = _re.search(_day_rx, _user_msg_lower)
                                    _time_m = _re.search(_time_rx, _user_msg_lower)
                                    _extracted_date = _day_m.group(0).strip() if _day_m else ""
                                    _extracted_time = ""
                                    if _time_m:
                                        _raw_t = (_time_m.group(1) or _time_m.group(2) or "").strip()
                                        _t_num = _re.search(r'(\d{1,2})(?::(\d{2}))?', _raw_t)
                                        if _t_num:
                                            _h = int(_t_num.group(1))
                                            _mn = int(_t_num.group(2)) if _t_num.group(2) else 0
                                            if 'pm' in _raw_t and _h < 12:
                                                _h += 12
                                            elif 'am' not in _raw_t and 'hs' not in _raw_t and _h <= 7:
                                                _h += 12  # bare "5" in business ctx -> 17
                                            _extracted_time = f"{_h:02d}:{_mn:02d}"
                                    try:
                                        await memory_manager.save_pending_scheduling(
                                            phone=phone,
                                            property_id=str(_selected),
                                            date_str=_extracted_date,
                                            time_str=_extracted_time,
                                        )
                                        logger.info(f"[Agent] Saved pending sched: date={_extracted_date!r} time={_extracted_time!r}")
                                    except Exception as _pe:
                                        logger.warning(f"[Agent] Could not save pending scheduling: {_pe}")
                                    _photo_note = (
                                        "Las fotos ya fueron enviadas al usuario."
                                        if _images_found
                                        else "Esta propiedad no tiene fotos disponibles. NO digas que enviaste fotos."
                                    )
                                    if _extracted_date and _extracted_time:
                                        messages.append({
                                            "role": "system",
                                            "content": (
                                                f"INSTRUCCION PRIORITARIA: El usuario pidio fotos Y visita. "
                                                f"{_photo_note} "
                                                f"El usuario YA dio: dia={_extracted_date!r}, hora={_extracted_time}. "
                                                f"Llama AHORA schedule_visit(property_id='{_selected}', date='{_extracted_date}', time='{_extracted_time}'). "
                                                "PROHIBIDO: NO preguntes dia ni horario. NO llames get_faq_answer."
                                            )
                                        })
                                        logger.info(f"[Agent] photos+schedule -> DIRECT schedule_visit date={_extracted_date!r} time={_extracted_time!r}")
                                    else:
                                        # Ask day first, hour second — never both at once, never with examples
                                        if not _extracted_date:
                                            _next_q = "¿Qué día te queda bien? Atendemos de lunes a sábado de 9 a 18hs."
                                            _missing_label = "dia"
                                        else:
                                            _next_q = f"¿A qué hora te queda mejor el {_extracted_date}?"
                                            _missing_label = "horario"
                                        messages.append({
                                            "role": "system",
                                            "content": (
                                                f"INSTRUCCION PRIORITARIA: El usuario pidio fotos Y visita. "
                                                f"{_photo_note} "
                                                f"Preguntá ÚNICAMENTE esto, con estas palabras exactas: \"{_next_q}\" "
                                                "PROHIBIDO: NO agregues ejemplos de horarios. "
                                                "NO confirmes la propiedad. "
                                                "NO llames get_faq_answer. "
                                                f"Cuando el usuario responda, llama schedule_visit con property_id={_selected}."
                                            )
                                        })
                                        logger.info(f"[Agent] photos+schedule nudge -> ask missing: {_missing_label}")
                            elif _images_found and not _asked_for_photos and _pending_prop:
                                # LLM re-called get_property_images unnecessarily while user is
                                # continuing a scheduling flow (e.g. providing day/time).
                                # Suppress image re-send and redirect to schedule_visit.
                                _prop_id = _pending_prop or merged_context.get("selected_property_id", tool_args.get("property_id", ""))
                                rich_content["images"] = []  # Clear so webhook won't re-send
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "INSTRUCCIÓN PRIORITARIA: Las fotos de esta propiedad ya fueron enviadas "
                                        "al usuario en el turno anterior. NO las envíes de nuevo y NO las menciones. "
                                        "El usuario acaba de responder con un día y horario para la visita. "
                                        f"Llamá AHORA schedule_visit(property_id={_prop_id}) "
                                        "con la fecha y hora que mencionó el usuario. "
                                        "PROHIBIDO: NO digas 'te dejo las fotos'. NO menciones imágenes."
                                    )
                                })
                                logger.info(f"[Agent] 🚫 Suppressed image re-send — redirecting to schedule_visit for {phone}")
                            elif not _asked_for_schedule and not _images_found:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "No hay fotos disponibles para esta propiedad. "
                                        "Informale al usuario con amabilidad y ofrecele coordinar una visita "
                                        "para conocerla en persona."
                                    )
})

                        # Save selected_property_id for context continuity across turns
                        if tool_args.get("property_id") and tool_name in ("get_property_details", "get_property_images"):
                            try:
                                await memory_manager.update_context_field(
                                    phone, "selected_property_id", tool_args["property_id"]
                                )
                                # Also save the property title if available from result
                                prop_title = None
                                if isinstance(tool_result, dict) and tool_result.get("title"):
                                    prop_title = tool_result["title"]
                                elif isinstance(tool_result, str) and "Departamento" in tool_result:
                                    import re as _re
                                    _m = _re.search(r'(Departamento[^|]+|Casa[^|]+)', tool_result)
                                    if _m:
                                        prop_title = _m.group(1).strip()
                                if prop_title:
                                    await memory_manager.update_context_field(
                                        phone, "selected_property_title", prop_title
                                    )
                                logger.info(
                                    f"[Agent] Saved selected property: [{prop_title or '?'}] (ID={tool_args['property_id']}) for {phone}"
                                )
                            except Exception as e:
                                logger.warning(f"[Agent] Could not save selected_property_id: {e}")

                        # Log confirmed datetime for schedule_visit / reschedule
                        if ("schedule_visit" in tool_name or "reschedule_appointment" in tool_name) and "Cita" in str(tool_result):
                            import re
                            match = re.search(r'<!--CONFIRMED:(\d{4}-\d{2}-\d{2} \d{2}:\d{2})-->', str(tool_result))
                            if match:
                                confirmed_time = match.group(1)
                                logger.info(f"[Agent] Tool confirmed datetime: {confirmed_time}")
                                logger.info(f"[Agent] Final confirmation message using time: {confirmed_time}")

                    if break_out:
                        break

                # Turn summary log
                logger.info(f"[Agent] Turn complete: {len(tools_used)} tool(s) used: {tools_used}")

                if not response_text:
                    response_text = "Tuve un problema al procesar tu solicitud. ¿Podrías intentar de nuevo?"

                # v2.0: Structured output eliminates need for _clean_response

                # Anti-hallucination guard: detect if LLM claims actions (schedule/cancel/etc.)
                # without having called the corresponding tool. If detected, replace with honesty.
                response_text = self._detect_action_hallucination(response_text, tools_used)

                next_state = self._determine_next_state(
                    intent=intent,
                    tools_used=tools_used,
                    current_state=merged_context.get("current_state", "idle")
                )

                # Build result dict BEFORE background post-processing
                result = {
                    "response_text": response_text,
                    "rich_content": rich_content if rich_content else None,
                    "tools_used": tools_used,
                    "next_state": next_state
                }

                # ── Background post-processing (runs AFTER WhatsApp send) ──
                async def _background_post_processing():
                    """Save state, lead score, preferences — runs after response is sent to WhatsApp."""
                    try:
                        # Save assistant message to memory
                        try:
                            await memory_manager.save_message(phone, "assistant", response_text)
                        except Exception as e:
                            logger.warning(f"Error guardando mensaje en background: {e}")

                        # State machine + lead score + preferences in parallel
                        post_tasks = []
                        post_tasks.append(state_machine.set_state(phone, next_state, allow_invalid=True))
                        post_tasks.append(self._update_lead_score(phone, tools_used, user_message))
                        if user_prefs:
                            post_tasks.append(self._extract_and_save_preferences(phone, user_message, user_prefs))
                        results = await asyncio.gather(*post_tasks, return_exceptions=True)
                        for i, r in enumerate(results):
                            if isinstance(r, Exception):
                                task_names = ["set_state", "lead_score", "extract_preferences"]
                                logger.warning(f"Error en background post-processing [{task_names[i]}]: {r}")

                        # Token usage summary
                        if cumulative_tokens["calls"] > 0:
                            logger.info(
                                f"[Tokens] phone={phone[-4:]} | CUMULATIVE | "
                                f"calls={cumulative_tokens['calls']} | "
                                f"prompt={cumulative_tokens['prompt']} | "
                                f"completion={cumulative_tokens['completion']} | "
                                f"total={cumulative_tokens['total']}"
                            )
                    except Exception as e:
                        logger.warning(f"Error in background post-processing: {e}")

                # Fire background task immediately — webhook sends WhatsApp response first,
                # then this finishes asynchronously (~6s speedup on user-perceived latency)
                asyncio.create_task(_background_post_processing())

                logger.info(f"Agent respondió: {response_text[:50]}... (tools: {tools_used})")

                return result

            except Exception as e:
                import traceback
                logger.error(f"Error en process_turn: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return {
                "response_text": "Disculpa, tuve un problema al procesar tu mensaje. ¿Podrías intentar de nuevo?",
                "rich_content": None,
                "tools_used": [],
                "next_state": "idle"
            }
    
    def _build_messages(
        self,
        user_message: str,
        history: List[Dict],
        user_context: Dict[str, Any],
        phone: str,
        last_shown_properties: List[Dict] = None,
        stage: str = None,
        capability: str = None,
    ) -> List[Dict]:
        """Construye la lista de mensajes para el LLM."""
        messages = []
        
        # Inject last_shown_properties into context for reference
        if last_shown_properties:
            user_context["last_shown_properties"] = last_shown_properties
            logger.info(f"[Agent] Injecting {len(last_shown_properties)} properties into context")
        
        # ── Detect capability if not provided ────────────────────────────────
        if not capability:
            from app.agents.router import detect_capability
            capability = detect_capability(user_message, user_context)
        
        # ── Detect sentiment ─────────────────────────────────────────────────
        _sentiment = None
        try:
            from app.agents.prompts import SENTIMENT_KEYWORDS
            _msg_lower = (user_message or "").lower()
            for _sk in SENTIMENT_KEYWORDS.get("negative", []):
                if _sk in _msg_lower:
                    _sentiment = "NEGATIVO"
                    break
            if not _sentiment:
                for _sk in SENTIMENT_KEYWORDS.get("urgent", []):
                    if _sk in _msg_lower:
                        _sentiment = "URGENTE"
                        break
        except Exception:
            pass
        
        # ── Build merged context for assembly ────────────────────────────────
        merged_context = dict(user_context)
        merged_context["_raw_message"] = user_message or ""
        if _sentiment:
            merged_context["_sentiment"] = _sentiment
        
        # ── Assemble modular system prompt ───────────────────────────────────
        _use_modular = True
        try:
            from app.core.config import get_settings
            _use_modular = get_settings().USE_MODULAR_PROMPTS
        except Exception:
            pass

        if _use_modular:
            try:
                from app.agents.prompt_files.loader import assemble_system_prompt
                system_prompt = assemble_system_prompt(
                    capability=capability or "general",
                    stage=stage or "",
                    context=merged_context,
                )
            except Exception as exc:
                logger.warning(f"[Agent] Modular prompt assembly failed, using legacy: {exc}")
                _use_modular = False

        if not _use_modular:
            from app.agents.prompts import get_system_prompt as legacy_sp
            system_prompt = legacy_sp(user_context)
            if stage:
                system_prompt += f"\n\n### ETAPA: {stage}"
            if _sentiment:
                system_prompt += f"\n\n### TONO: {_sentiment}"
        
        messages.append({"role": "system", "content": system_prompt})

        # Inject last properties as system reminder with EXPLICIT index-to-ID mapping — BEFORE history
        if last_shown_properties:
            # Format: Explicit mapping "Option N" → "Database ID" to prevent hallucination
            prop_list_lines = []
            for i, p in enumerate(last_shown_properties[:6]):
                db_id = p.get('id', p.get('property_id', 'N/A'))
                title = p.get('title', 'N/A')
                prop_list_lines.append(f"<opción {i+1}> → ID={db_id} | {title}")
            
            prop_list = "\n".join(prop_list_lines)
            
            # XML-style context injection for better LLM understanding
            context_reminder = f"""<last_results>
{prop_list}
</last_results>

### INSTRUCCIÓN IMPORTANTE:
- Si el usuario menciona "opción 1", "la primera", "opción 2", etc., busca el ID correspondiente en <last_results> arriba
- NUNCA inventes un ID - usa EXACTAMENTE el ID que aparece después de "→ ID=" en <last_results>
- Ejemplo: "dame detalles de la opción 2" → busca ID=XXX en <last_results> → get_property_details(property_id=XXX)"""

            messages.append({
                "role": "system", 
                "content": context_reminder
            })

        # (Few-shot examples condensed inline in SYSTEM_PROMPT REGLAS section)

        # Append existing appointments context (DB-sourced) — prevents time hallucination during rescheduling
        existing = user_context.get("existing_appointments")
        if existing:
            from app.services.appointment_service import format_appointment_confirmation
            apt_lines = []
            for apt in existing[:3]:
                apt_lines.append(format_appointment_confirmation(apt))
            context_block = (
                "\n### CITAS EXISTENTES DEL USUARIO\n"
                + "\n---\n".join(apt_lines) +
                "\n\n"
                "USA ESTOS DATOS EXACTOS si el usuario menciona cambiar o cancelar una cita. "
                "NO infieras ni adivines la hora desde la conversación. "
                "La base de datos es la ÚNICA fuente de verdad.\n"
            )
            messages.append({"role": "system", "content": context_block})
            logger.info(f"[Agent] Injected {len(existing)} existing appointments for {phone}")

        # Inject conversation state summary right before user message
        selected_id = user_context.get("selected_property_id")
        selected_title = user_context.get("selected_property_title") or "propiedad"
        if history and len(history) >= 2:
            conv_summary_parts = []
            if selected_id and selected_title:
                conv_summary_parts.append(f"Propiedad activa: [{selected_title}] (ID={selected_id})")
            op_type = user_context.get("operation_type") or user_context.get("last_operation")
            if op_type:
                conv_summary_parts.append(f"Operacion: {op_type}")
            loc = user_context.get("location_preferences")
            if loc:
                conv_summary_parts.append(f"Ubicacion: {loc}")
            if conv_summary_parts:
                summary = " | ".join(conv_summary_parts)
                messages.append({
                    "role": "system",
                    "content": f"\n### RESUMEN DE CONVERSACION\n{summary}\n"
                })
        
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
        
        # If no history and no tools used yet, user is starting fresh — guide the conversation
        if not history and not user_context.get("is_returning"):
            messages.append({
                "role": "system",
                "content": (
                    "IMPORTANTE: Este es el primer contacto del usuario. "
                    "Seguí las instrucciones de # Saludo Inicial del system prompt: "
                    "saludo con hora del día + nombre de la inmobiliaria + lo que podés hacer en una frase natural + pregunta abierta. "
                    "Si el usuario ya dio criterios en su mensaje (zona, tipo, precio, etc.), saltate el saludo genérico "
                    "y respondé directamente a lo que pidió."
                )
            })
        
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def _extract_rich_content(self, tool_args: dict, tool_result: str) -> dict:
        """Extrae rich content desde el resultado de la herramienta."""
        import re
        
        try:
            # Try extract images from <!--IMAGES:...--> comment
            images_match = re.search(r'<!--IMAGES:(\[[^\]]+\])-->', tool_result)
            if images_match:
                try:
                    images_data = json.loads(images_match.group(1))
                    if images_data:
                        return {
                            "action": "show_property_images",
                            "images": images_data[:6]  # Max 6 images
                        }
                except json.JSONDecodeError:
                    pass
            
            # Try extract images if tool_result contains JSON with images
            try:
                data = json.loads(tool_result)
                if isinstance(data, dict) and data.get("images"):
                    return {
                        "action": "show_property_images",
                        "images": data.get("images", [])
                    }
            except Exception:
                pass
            properties = []
            
            if "Encontré" in tool_result and "propiedades" in tool_result:
                return {
                    "action": "show_search_results",
                    "search_criteria": tool_args,
                    "message": tool_result
                }
            
            if "ID de propiedad:" in tool_result or "ID:" in tool_result:
                import re
                id_match = re.search(r'ID[:\s]*`?([a-zA-Z0-9-]+)`?', tool_result)
                if id_match:
                    return {
                        "action": "show_property_details",
                        "property_id": id_match.group(1),
                        "message": tool_result
                    }
            
            return {"action": "general_response", "message": tool_result}
            
        except Exception as e:
            logger.error(f"Error extract rich content: {e}")
            return {"action": "general_response", "message": tool_result}
    
    def _determine_next_state(
        self,
        intent: Intent,
        tools_used: List[str],
        current_state: str
    ) -> str:
        """Determina el estado siguiente basado en intent y herramientas usadas."""
        if intent == Intent.PROPERTY_SEARCH or "search_properties" in str(tools_used):
            return ConversationStateEnum.SEARCHING.value
        
        if "get_property_images" in str(tools_used):
            return ConversationStateEnum.VIEWING_PROPERTY.value
        
        if intent == Intent.PROPERTY_DETAILS or "get_property_details" in str(tools_used):
            return ConversationStateEnum.VIEWING_PROPERTY.value
        
        if intent == Intent.SCHEDULE_APPOINTMENT or "schedule_visit" in str(tools_used) or "reschedule_appointment" in str(tools_used):
            return ConversationStateEnum.BOOKING.value
        
        if intent == Intent.HUMAN_HANDOFF:
            return ConversationStateEnum.HUMAN_ASSISTANCE.value
        
        if current_state in [ConversationStateEnum.SEARCHING.value, ConversationStateEnum.VIEWING_PROPERTY.value, ConversationStateEnum.BOOKING.value]:
            return current_state
        
        return ConversationStateEnum.IDLE.value
    
    async def _update_lead_score(self, phone: str, tools_used: List[str], message: str) -> None:
        """Actualiza el lead score basado en acciones del usuario."""
        score_increase = 0
        
        if "search_properties" in str(tools_used):
            score_increase += 10
        if "get_property_details" in str(tools_used):
            score_increase += 15
        if "recommend_properties" in str(tools_used):
            score_increase += 10
        
        appointment_keywords = ["agendar", "visita", "cita", "horario", "fecha"]
        if any(kw in message.lower() for kw in appointment_keywords):
            score_increase += 20
        
        if score_increase > 0:
            try:
                context = await memory_manager.get_user_context(phone)
                current_score = context.get("lead_score", 0)
                new_score = current_score + score_increase
                await memory_manager.update_user_preferences(
                    phone,
                    {"lead_score": new_score}
                )
                logger.info(f"Lead score actualizado: +{score_increase} para {phone}")
                # ── Notificación: lead calificado (umbral 50) ─────────
                if current_score < 50 <= new_score:
                    try:
                        from app.services.notification_service import notification_service
                        name = context.get("name") or ""
                        await notification_service.lead_qualified(phone=phone, score=new_score, name=name)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Error actualizando lead score: {e}")
    
    async def _extract_and_save_preferences(
        self,
        phone: str,
        message: str,
        current_prefs: Dict
    ) -> None:
        """Extrae y guarda preferencias del mensaje del usuario."""
        try:
            # Background name extraction (runs every turn, no user-facing latency)
            if message and phone:
                existing_name = current_prefs.get("name") or await memory_manager.get_user_name(phone)
                if not existing_name:
                    from app.core.hybrid.name import name_extractor

                    name_result = await name_extractor.parse(message, {})
                    if name_result.value and name_result.confidence >= 0.6:
                        await memory_manager.save_user_name(phone, name_result.value)
                        logger.info(
                            "[NameExtractor] Extracted name %r for %s (parser=%s, conf=%.2f)",
                            name_result.value,
                            phone,
                            name_result.parser_used,
                            name_result.confidence,
                        )

            # Preference extraction (hybrid: LLM first, code fallback)
            from app.core.hybrid.preference import preference_extractor

            pref_ctx = {"phone": phone, "current_prefs": current_prefs}
            pref_result = await preference_extractor.parse(message, pref_ctx)

            if pref_result.value and isinstance(pref_result.value, dict):
                prefs = pref_result.value

                # Save basic fields (backward-compatible with existing schema)
                if prefs.get("location"):
                    current_prefs["location_preferences"] = prefs["location"]
                if prefs.get("budget_max"):
                    current_prefs["budget_max"] = prefs["budget_max"]
                if prefs.get("budget_min"):
                    current_prefs["budget_min"] = prefs["budget_min"]
                if prefs.get("property_type"):
                    current_prefs["property_type"] = prefs["property_type"]
                if prefs.get("operation_type"):
                    current_prefs["operation_type"] = prefs["operation_type"]
                if prefs.get("bedrooms"):
                    current_prefs["bedrooms"] = prefs["bedrooms"]
                if prefs.get("bathrooms"):
                    current_prefs["bathrooms"] = prefs["bathrooms"]

                # NEW: save qualitative preferences
                if prefs.get("features") or prefs.get("qualitative"):
                    current_prefs["qualitative_prefs"] = {
                        "features": prefs.get("features", []),
                        "qualitative": prefs.get("qualitative", []),
                    }

                # Save to Redis — merge into full context to preserve state fields
                try:
                    full_context = await memory_manager.get_user_context(phone)
                    full_context.update(current_prefs)
                    await memory_manager.save_user_context(phone, full_context)
                except Exception as ctx_e:
                    logger.warning(f"[Agent] Could not persist extracted prefs to Redis: {ctx_e}")
                logger.info(
                    "Preferencias extraidas via %s: %s",
                    pref_result.parser_used,
                    {k: v for k, v in prefs.items() if v},
                )
            else:
                # Fallback: existing regex extraction
                await memory_manager.extract_and_save_preferences(
                    phone, message, current_prefs
                )

            logger.info("Preferencias extraidas y guardadas exitosamente")
        except Exception as e:
            logger.error("Error guardando preferencias: %s", e)
    
    @staticmethod
    def _detect_action_hallucination(text: str, tools_used: List[str]) -> str:
        """
        Anti-hallucination guard: if the LLM claims to have performed an action
        (e.g., "Cita Agendada", "cancelé tu cita", "guardé tus datos") but the
        corresponding tool was NOT called, replace the response with an honest
        fallback. This prevents the bot from lying to the user about actions
        that never happened in the DB.

        Returns the original text (safe), or a corrected fallback (haltucination blocked).
        """
        text_lower = text.lower()

        # Mapping: action claim phrases → required tool that must have been called
        HALLUCINATION_CHECKS = [
            # schedule_visit
            (['agendé', 'agendamos',
              "te agendé", "quedó agendada"],
             "schedule_visit",
             "Lo siento, tuve un problema al agendar la visita. ¿Podrías intentar de nuevo?"),

            # reschedule_appointment
            (['reprogramé', 'reprogramamos', 'cita reprogramada',
              "cambio la fecha", "cambié la fecha", "nueva fecha para tu cita",
              'modifiqué tu cita'],
             "reschedule_appointment",
             "Lo siento, tuve un problema al reprogramar la cita. ¿Podrías intentar de nuevo?"),

            # cancel_appointment
            (["cancelada", "cancelé", "cancelamos", "cita cancelada", "turno cancelado",
              "anulada", "anulé"],
             "cancel_appointment",
             "Lo siento, tuve un problema al cancelar la cita. ¿Podrías intentar de nuevo?"),

            # save_lead_info
            (["guardé tus datos", "guardamos tus datos", "te registré", "te registramos",
              "datos guardados", "quedaste registrado"],
             "save_lead_info",
             "Lo siento, tuve un problema al guardar tus datos. ¿Podrías intentar de nuevo?"),

            # request_human_assistance
            (["pasé con un agente", "transfiero a un agente", "te paso con un agente",
              "conectando con un agente"],
             "request_human_assistance",
             "Lo siento, tuve un problema al transferirte. Por favor pedí hablar con un agente de nuevo."),
        ]

        for claim_phrases, required_tool, fallback_msg in HALLUCINATION_CHECKS:
            any_claim_matched = any(phrase in text_lower for phrase in claim_phrases)
            if any_claim_matched and required_tool not in tools_used:
                logger.warning(
                    f"[Agent] 🔴 HALLUCINATION BLOCKED: text claims '{required_tool}' action "
                    f"but tool was not called. Tools used: {tools_used}"
                )
                return f"{fallback_msg}\n\n{text}"
            elif any_claim_matched and required_tool in tools_used:
                logger.info(
                    f"[Agent] ✅ Action '{required_tool}' correctly confirmed with tool call"
                )

        return text

    def _detect_handoff_request(self, message: str) -> bool:
        """Detecta si el usuario está pidiendo hablar con un humano."""
        handoff_keywords = [
            "hablar con un agente",
            "hablar con una persona",
            "hablar con alguien",
            "quiero hablar con",
            "pásame con",
            "no quiero al bot",
            "hablar con un humano",
            "hablar con humano",
            "hablar con persona real",
            "transferirme",
            "transferir a un agente",
        ]
        return any(kw in message.lower() for kw in handoff_keywords)


# Module-level singleton — imported by webhook.py and other modules
real_estate_agent = RealEstateAgent()

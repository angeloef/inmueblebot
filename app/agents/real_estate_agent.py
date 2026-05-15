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
from app.core.memory import memory_manager
from app.core.state_machine import state_machine, ConversationStateEnum
from app.core.intent import Intent


FORBIDDEN_RESPONSE_WORDS = [
    "llamando a la función", "llamando a", "calling", "calling function",
    "print(", "tool_call", "tool(",
    "function(", "search_properties(", "get_property_details(",
    "arguments", "debug", "depurando", "logging",
    "[function", "[tool", "tool call"
]


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
    
    MAX_TOOL_CALLS = 5  # Increased to allow search→details→images→schedule sequences
    
    def __init__(self):
        self.llm = llm_router
        self.tools = TOOL_DEFINITIONS
    
    async def process_turn(
        self,
        phone: str,
        user_message: str,
        intent: Intent = None,
        force_agent: bool = False
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
        
        try:
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
            
            if self._detect_handoff_request(user_message):
                from app.services.handoff_service import handoff_service
                handoff_result = await handoff_service.trigger_handoff(phone, "user_requested")
                await state_machine.set_state(phone, ConversationStateEnum.HUMAN_ASSISTANCE.value)
                return {
                    "response_text": handoff_result.get("message", "Un agente humano te contactará pronto."),
                    "rich_content": {"action": "handoff_initiated"},
                    "tools_used": ["request_human_assistance"],
                    "next_state": ConversationStateEnum.HUMAN_ASSISTANCE.value
                }
            
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
                last_shown_properties=last_props if last_props else None
            )
            
            tools_used = []
            response_text = ""
            rich_content = {}
            cumulative_tokens = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}

            reschedule_failures = 0
            for iteration in range(self.MAX_TOOL_CALLS):
                break_out = False
                # Phase 4: Add detailed logging for tools + intent detection
                tools_count = len(self.tools) if self.tools else 0

                logger.info(f"[Agent] Iteration {iteration + 1}: Sending {tools_count} tools to LLM")

                llm_response = await self.llm.ainvoke(
                    messages=messages,
                    tools=self.tools,
                    temperature=0.7
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
                    # Anti-hallucination guard: if this was a property search but the LLM
                    # never called the search tool, don't accept a made-up response.
                    search_was_called = any(
                        "search_properties" in t or "recommend_properties" in t
                        for t in tools_used
                    )
                    if intent == Intent.PROPERTY_SEARCH and not search_was_called:
                        logger.warning("[Agent] PROPERTY_SEARCH intent but no search tool called — blocking potential hallucination")
                        response_text = "No encontré propiedades disponibles con esos criterios en este momento. Podés intentar con otros filtros o contactar a un agente."
                    else:
                        # Search hallucination guard: if LLM said "voy a buscar"/"buscando"
                        # without actually calling search, force it to search.
                        _resp_lower = (llm_response.content or "").lower()
                        _said_search = any(p in _resp_lower for p in
                            ["voy a buscar", "vamos a buscar", "vamos a encontrar",
                             "buscando", "déjame buscar", "un momento",
                             "voy a revisar", "voy a consultar",
                             "voy a fijarme", "voy a ver", "vamos a ver",
                             "voy a chequear"])
                        _user_wants_search = any(p in (user_message or "").lower() for p in
                            ["busco", "buscar", "buscando", "quiero", "necesito",
                             "departamento", "casa", "alquilar", "alquiler",
                             "comprar", "terreno", "propiedad", "ph",
                             "departamento", "local", "oficina"])
                        
                        if _said_search and _user_wants_search and not search_was_called:
                            # Only force search if the LLM is NOT asking a question.
                            # If the response has "?" or "¿", the LLM is guiding the conversation (REGLA 7).
                            _is_question = "?" in _resp_lower or "¿" in _resp_lower
                            if not _is_question:
                                # Force-inject a system message: correct the LLM
                                logger.warning("[Agent] LLM said 'voy a buscar' but didn't call search_properties — forcing corrective message")
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "ACABÁS DE DECIR 'voy a buscar' pero NO llamaste search_properties(). "
                                        "Las búsquedas NO existen en tu texto. Solo existen si llamás la función. "
                                        "LLAMÁ search_properties() AHORA con los criterios del usuario. "
                                        "No sigas conversando sin buscar."
                                    )
                                })
                                continue  # Go to next iteration (force the LLM to search)
                        
                        response_text = llm_response.content
                    break

                # PHASE 1.5: Execute tool calls
                for tool_call in llm_response.tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.arguments
                    
                    logger.info(f"Tool call: {tool_name} con args: {tool_args}")
                    tools_used.append(tool_name)
                    
                    # PROPERTY_ID GUARD: if LLM calls schedule_visit with wrong property_id,
                    # force it to use selected_property_id from context
                    if tool_name == "schedule_visit":
                        try:
                            _ctx = await memory_manager.get_user_context(phone)
                            _selected = _ctx.get("selected_property_id")
                            _arg_pid = tool_args.get("property_id")
                            if _selected and _arg_pid and str(_selected) != str(_arg_pid):
                                logger.warning(
                                    f"[Agent] 🛡️ PROPERTY_ID MISMATCH: LLM wants property_id={_arg_pid} "
                                    f"but selected_property_id={_selected}. FORCING CORRECTION."
                                )
                                # Override the LLM's property_id with the active one
                                tool_args["property_id"] = str(_selected)
                                tool_args["_corrected_from"] = str(_arg_pid)
                        except Exception as _e:
                            logger.warning(f"[Agent] Property guard error (non-fatal): {_e}")

                    tool_result = await execute_tool(
                        tool_name=tool_name,
                        arguments=tool_args,
                        phone=phone
                    )

                    # SHORT-CIRCUIT: if tool result IS the final answer, skip remaining LLM iterations
                    if isinstance(tool_result, str):
                        # General: any tool result with <!--CONFIRMED:--> is a final confirmation message
                        if "<!--CONFIRMED:" in tool_result:
                            response_text = tool_result
                            logger.info(f"[Agent] Short-circuit: {tool_name} succeeded with confirmation, using result directly")
                            break_out = True
                            break
                        if tool_name == "cancel_appointment" and "Cita Cancelada" in tool_result:
                            response_text = tool_result
                            logger.info(f"[Agent] Short-circuit: {tool_name} succeeded, using confirmation directly")
                            break_out = True
                            break
                        # final_response tool: parse the response plan and short-circuit the loop
                        if tool_name == "final_response":
                            try:
                                import json
                                plan_data = json.loads(tool_result)
                                if "plan" in plan_data and plan_data["plan"]:
                                    # Build response_plan but keep response_text for backward compat
                                    plan = plan_data["plan"]
                                    response_text = ""
                                    for seg in plan:
                                        if seg.get("type") == "text":
                                            response_text += seg.get("content", "") + "\n"
                                    # Remove trailing newlines
                                    response_text = response_text.strip()
                                    # Store structured plan in rich_content for the webhook
                                    rich_content["response_plan"] = plan
                                    logger.info(f"[Agent] final_response plan: {len(plan)} segment(s)")
                                    break_out = True
                                    break
                            except (json.JSONDecodeError, Exception) as e:
                                logger.warning(f"[Agent] final_response parse error: {e}")
                                # Don't short-circuit — let the LLM try again

                    # Reschedule failure counter: max 3 consecutive failures
                    if tool_name == "reschedule_appointment":
                        if not isinstance(tool_result, str) or "<!--CONFIRMED:" not in str(tool_result):
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
                            # Success — reset counter
                            reschedule_failures = 0

                    # Detect tool loops — same tool called twice consecutively = break
                    if len(tools_used) >= 2:
                        last_two = tools_used[-2:]
                        if last_two[0] == last_two[1]:
                            logger.warning(f"[Agent] Loop detected: same tool called twice: {last_two[0]}. Breaking.")
                            # If it's a scheduling tool, propagate success or break failure loop
                            if last_two[0] in ("schedule_visit", "reschedule_appointment", "cancel_appointment"):
                                result_str = str(tool_result)
                                if "<!--CONFIRMED:" in result_str or "Cita Reprogramada" in result_str or "Cita Cancelada" in result_str or "Cita Agendada" in result_str:
                                    response_text = tool_result
                                    logger.info(f"[Agent] Scheduling tool {last_two[0]} succeeded despite loop — confirmation used")
                                else:
                                    # Tool failed and is looping — break BOTH loops with friendly fallback
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
                        "content": str(tool_result)
                    })
                    
                    # ── Plan B: Inject contextual next-step guidance ──
                    if tool_name == "search_properties":
                        # After showing search results, suggest next step
                        messages.append({
                            "role": "system",
                            "content": (
                                "Acabas de mostrar resultados de búsqueda. "
                                "SIEMPRE terminá tu respuesta preguntando al usuario "
                                "si quiere ver los detalles de alguna propiedad en particular. "
                                "Ej: '¿Querés ver los detalles de alguna?'"
                            )
                        })
                    elif tool_name == "get_property_details":
                        # Extract property data from tool result for the system message
                        _prop_info = ""
                        if isinstance(tool_result, str) and tool_result:
                            # Extract first line or key info for context
                            _first_line = tool_result.split('\n')[0] if '\n' in tool_result else tool_result[:60]
                            _prop_info = f" Los datos REALES de la propiedad son: {_first_line}"
                        messages.append({
                            "role": "system",
                            "content": (
                                "Acabas de recibir los DATOS REALES de la propiedad desde la base de datos en el tool result arriba. "
                                "IGNORÁ cualquier descripción, precio o título que hayas escrito antes. "
                                "Usá EXACTAMENTE los datos que devolvió el tool, palabra por palabra."
                                f"{_prop_info}"
                                "Presentalos de forma conversacional y preguntale al usuario "
                                "si quiere agendar una visita o ver las fotos. "
                                "Ej: '¿Querés agendar una visita para verla?'"
                            )
                        })
                    elif tool_name == "compare_properties":
                        messages.append({
                            "role": "system",
                            "content": (
                                "Mostraste una comparación de propiedades. "
                                "Preguntale al usuario cuál le interesa más "
                                "para mostrarle los detalles."
                            )
                        })
                    elif tool_name == "get_faq_answer":
                        messages.append({
                            "role": "system",
                            "content": (
                                "Respondiste una pregunta frecuente. "
                                "Primero preguntale al usuario \"¿Tenes alguna otra consulta?\". "
                                "Después de eso, ofrecelé ayuda con propiedades. "
                                "Usá final_response con 2 segmentos de tipo 'text' para separar la respuesta de la pregunta de seguimiento."
                            )
                        })
                    elif tool_name in ("schedule_visit", "reschedule_appointment") and "CONFIRMED" in str(tool_result):
                        messages.append({
                            "role": "system",
                            "content": (
                                "La cita se agendó con éxito. Confirmale al usuario "
                                "los detalles (día y hora) y preguntale si necesita "
                                "algo más. Si dice que no, despedite cordialmente."
                            )
                        })
                    
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
                    
                    # SHORT-CIRCUIT: search/recommend result is a complete formatted response — skip LLM regeneration
                    if isinstance(tool_result, str) and tool_name in ("search_properties", "recommend_properties"):
                        response_text = tool_result
                        logger.info(f"[Agent] Short-circuit: {tool_name} complete, using formatted result directly")
                        break_out = True
                        break
                    
                    if "get_property_images" in tool_name:
                        new_rich = self._extract_rich_content(tool_args, tool_result)
                        # Preserve images from both current and previous rich_content
                        existing_images = rich_content.get("images", [])
                        new_images = new_rich.get("images", [])
                        if existing_images:
                            new_rich["images"] = existing_images + new_images
                        rich_content = new_rich
                    
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
            
            # Clean response - remove forbidden words/patterns
            response_text = self._clean_response(response_text, tools_used)

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
        last_shown_properties: List[Dict] = None
    ) -> List[Dict]:
        """Construye la lista de mensajes para el LLM."""
        messages = []
        
        # Inject last_shown_properties into context for reference
        if last_shown_properties:
            user_context["last_shown_properties"] = last_shown_properties
            logger.info(f"[Agent] Injecting {len(last_shown_properties)} properties into context")
        
        system_prompt = get_system_prompt(user_context)
        messages.append({"role": "system", "content": system_prompt})

        # Inject returning user greeting if applicable
        if user_context.get("is_returning"):
            last_ref = user_context.get("last_reference", "propiedades")
            returning_msg = (
                f"\n### USUARIO RECURRENTE\n"
                f"Este usuario ya ha conversado antes. "
                f"Su última referencia fue: {last_ref}\n"
                f"Saludalo con un mensaje cálido tipo: '¡Bienvenido de nuevo! La última vez viste [referencia]...'\n"
            )
            messages.append({"role": "system", "content": returning_msg})
            logger.info(f"[Agent] Injected returning user greeting for {phone}, ref={last_ref}")

        # Inject active/selected property for context continuity — BEFORE history
        selected_id = user_context.get("selected_property_id")
        selected_title = user_context.get("selected_property_title") or "propiedad"
        if selected_id:
            selected_prop_reminder = (
                f"\n### ACTIVE PROPERTY CONTEXT\n"
                f"El usuario est\u00e1 viendo actualmente la propiedad: [{selected_title}] con ID: {selected_id}\n"
                f"SIEMPRE que mencione 'esa', 'esa propiedad', 'la misma', 'la que vimos', "
                f"'el departamento que vimos', 'esa casa' -- referite a [{selected_title}] con ID={selected_id}.\n"
                f"Para schedule_visit: property_id={selected_id} (NO uses otro ID).\n"
            )
            messages.append({
                "role": "system",
                "content": selected_prop_reminder
            })
            logger.info(f"[Agent] Injected selected_property_id={selected_id} into LLM context for {phone}")

        # Inject pending scheduling info for context-aware scheduling — BEFORE history
        pending = user_context.get("pending_scheduling_info")
        if pending and pending.get("date_str"):
            saved_date = pending["date_str"]
            saved_pid = pending.get("property_id", "")
            saved_time = pending.get("time_str", "")
            schedule_context = (
                "\n### PENDING SCHEDULING INFO\n"
                "El usuario ya mencionó querer agendar una visita y se guardó esta información:\n"
            )
            if saved_pid:
                schedule_context += f"  Propiedad: {saved_pid}\n"
            schedule_context += f"  Fecha guardada: \"{saved_date}\"\n"
            if saved_time:
                schedule_context += f"  Hora guardada: \"{saved_time}\"\n"
            schedule_context += (
                f"\nREGLA CRÍTICA: Cuando el usuario complete la información faltante, llamá schedule_visit con:\n"
                f"  - date_str=\"{saved_date}\"  ← EXACTAMENTE este valor. NUNCA sustituyas por 'mañana' ni la fecha de hoy.\n"
            )
            if saved_pid:
                schedule_context += f"  - property_id=\"{saved_pid}\"\n"
            if saved_time:
                schedule_context += f"  - time_str=\"{saved_time}\"\n"
            schedule_context += "NO preguntes de nuevo por fecha ni hora — ya están guardadas.\n"
            messages.append({
                "role": "system",
                "content": schedule_context
            })
            logger.info(f"[Agent] Injected pending scheduling info for {phone}: {pending}")

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
                    "IMPORTANTE: Este es el primer mensaje del usuario. "
                    "Respondé con un saludo cálido y preguntale activamente "
                    "qué está buscando. No esperes a que te den todos los detalles. "
                    "Ej: '¡Hola! ¿Estás buscando alquilar o comprar? ¿En qué zona?'"
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
        
        if intent == Intent.PROPERTY_DETAILS or "get_property_details" in str(tools_used):
            return ConversationStateEnum.VIEWING_PROPERTY.value
        
        if intent == Intent.SCHEDULE_APPOINTMENT:
            return ConversationStateEnum.BOOKING.value
        
        if intent == Intent.HUMAN_HANDOFF:
            return ConversationStateEnum.HUMAN_ASSISTANCE.value
        
        if current_state in [ConversationStateEnum.SEARCHING.value, ConversationStateEnum.VIEWING_PROPERTY.value]:
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

                # Save to Redis
                await memory_manager.update_context(phone, current_prefs)
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
    
    def _clean_response(self, response: str, tools_used: List[str]) -> str:
        """Limpia la respuesta de texto técnico/prohibido."""
        if not tools_used:
            return response
        
        response_lower = response.lower()
        
        # Check for forbidden patterns
        has_forbidden = any(word in response_lower for word in FORBIDDEN_RESPONSE_WORDS)
        
        if has_forbidden:
            logger.warning(f"[Agent] ⚠️ Response contains forbidden words, cleaning...")
            
            # Try to regenerate with a clean message
            logger.info(f"[Agent] Regenerating clean response...")
        
        # Replace common bad patterns with cleaner text
        cleaned = response
        
        # Remove "I'm calling..." / "Llamando a la función..." patterns
        import re
        patterns_to_remove = [
            r".*\(Llamando\s+a\s+la\s+función.*\)",
            r".*\(calling.*function.*\)",
            r".*\(search_properties.*\)",
            r"print\(.*\)",
            r"\[tool[_\s]call.*\]",
        ]
        
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        
        # If still contains forbidden, try to extract just the property list
        if any(word in cleaned.lower() for word in FORBIDDEN_RESPONSE_WORDS):
            # Extract property-like content
            lines = cleaned.split('\n')
            good_lines = []
            for line in lines:
                if not any(word in line.lower() for word in FORBIDDEN_RESPONSE_WORDS):
                    good_lines.append(line)
            cleaned = '\n'.join(good_lines)
        
        # Final cleanup - trim excessive whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = cleaned.strip()
        
        if cleaned != response:
            logger.info(f"[Agent] ✓ Response cleaned: {len(cleaned)} chars")
        
        return cleaned or "Encontré propiedades que pueden interesarte. ¿Querés más detalles?"

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
            (["agendada", "agendé", "agendamos", "visita agendada", "cita agendada", "turno agendado",
              "te esperamos", "te agendé", "quedó agendada"],
             "schedule_visit",
             "Lo siento, tuve un problema al agendar la visita. ¿Podrías intentar de nuevo?"),

            # reschedule_appointment
            (["reprogramada", "reprogramé", "reprogramamos", "cita reprogramada",
              "cambio la fecha", "cambié la fecha", "nueva fecha para tu cita",
              "modifiqué tu cita", "modificada"],
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
        
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in handoff_keywords)


real_estate_agent = RealEstateAgent()

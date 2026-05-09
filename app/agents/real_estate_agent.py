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
                history = await memory_manager.get_recent_messages(phone, limit=5)
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
                        response_text = llm_response.content
                    break
                
                for tool_call in llm_response.tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.arguments
                    
                    logger.info(f"Tool call: {tool_name} con args: {tool_args}")
                    tools_used.append(tool_name)
                    
                    tool_result = await execute_tool(
                        tool_name=tool_name,
                        arguments=tool_args,
                        phone=phone
                    )

                    # SHORT-CIRCUIT: if tool result IS the final answer, skip remaining LLM iterations
                    if isinstance(tool_result, str):
                        if tool_name in ("schedule_visit", "reschedule_appointment") and "<!--CONFIRMED:" in tool_result:
                            response_text = tool_result
                            logger.info(f"[Agent] Short-circuit: {tool_name} succeeded, using confirmation directly")
                            break_out = True
                            break
                        if tool_name == "cancel_appointment" and "Cita Cancelada" in tool_result:
                            response_text = tool_result
                            logger.info(f"[Agent] Short-circuit: {tool_name} succeeded, using confirmation directly")
                            break_out = True
                            break
                        if tool_name in ("search_properties", "recommend_properties") and "No encontré" in tool_result:
                            response_text = tool_result
                            logger.info(f"[Agent] Short-circuit: {tool_name} returned no results")
                            break_out = True
                            break

                    # Detect tool loops — same tool + same args called twice = break
                    if len(tools_used) >= 2:
                        last_two = tools_used[-2:]
                        if last_two[0] == last_two[1]:
                            logger.warning(f"[Agent] Loop detected: same tool called twice: {last_two[0]}. Breaking.")
                            # If it's a scheduling tool that already succeeded, use the success response
                            if last_two[0] in ("schedule_visit", "reschedule_appointment", "cancel_appointment"):
                                result_str = str(tool_result)
                                if "<!--CONFIRMED:" in result_str or "Cita Reprogramada" in result_str or "Cita Cancelada" in result_str or "Cita Agendada" in result_str:
                                    response_text = tool_result
                                    logger.info(f"[Agent] Scheduling tool {last_two[0]} succeeded despite loop — confirmation used")
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
                        
                        # Save last_shown_properties for context
                        last_props = rich_content.get("properties", [])
                        if last_props:
                            logger.info(f"[Agent] Saving {len(last_props)} properties to context")
                            # Save to memory for next turn
                            try:
                                await memory_manager.update_context_field(
                                    phone, 
                                    "last_shown_properties", 
                                    last_props
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
                    
                    # Save selected_property_id for context continuity across turns
                    if tool_args.get("property_id") and tool_name in ("get_property_details", "get_property_images"):
                        try:
                            await memory_manager.update_context_field(
                                phone, "selected_property_id", tool_args["property_id"]
                            )
                            logger.info(
                                f"[Agent] Saved selected_property_id={tool_args['property_id']} for {phone}"
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
            
            try:
                await memory_manager.save_message(phone, "assistant", response_text)
            except Exception as e:
                logger.warning(f"Error guardando mensaje: {e}")
            
            next_state = self._determine_next_state(
                intent=intent,
                tools_used=tools_used,
                current_state=merged_context.get("current_state", "idle")
            )
            
            # Run post-processing tasks in PARALLEL for ~6s speedup
            post_tasks = []
            post_tasks.append(state_machine.set_state(phone, next_state, allow_invalid=True))
            post_tasks.append(self._update_lead_score(phone, tools_used, user_message))
            if user_prefs:
                post_tasks.append(self._extract_and_save_preferences(phone, user_message, user_prefs))
            results = await asyncio.gather(*post_tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    task_names = ["set_state", "lead_score", "extract_preferences"]
                    logger.warning(f"Error en post-processing [{task_names[i]}]: {r}")
            
            if cumulative_tokens["calls"] > 0:
                logger.info(
                    f"[Tokens] phone={phone[-4:]} | CUMULATIVE | "
                    f"calls={cumulative_tokens['calls']} | "
                    f"prompt={cumulative_tokens['prompt']} | "
                    f"completion={cumulative_tokens['completion']} | "
                    f"total={cumulative_tokens['total']}"
                )
            logger.info(f"Agent respondió: {response_text[:50]}... (tools: {tools_used})")
            
            return {
                "response_text": response_text,
                "rich_content": rich_content if rich_content else None,
                "tools_used": tools_used,
                "next_state": next_state
            }
            
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

        # Inject active/selected property for context continuity — BEFORE history
        selected_id = user_context.get("selected_property_id")
        if selected_id:
            selected_prop_reminder = (
                f"\n### ACTIVE PROPERTY CONTEXT\n"
                f"El usuario está viendo actualmente la propiedad con ID: {selected_id}\n"
                f"Si el usuario dice 'esa', 'esa propiedad', 'la misma', 'la que vimos' — "
                f"USA get_property_details(property_id={selected_id})\n"
            )
            messages.append({
                "role": "system",
                "content": selected_prop_reminder
            })
            logger.info(f"[Agent] Injected selected_property_id={selected_id} into LLM context for {phone}")

        # Inject pending scheduling info for context-aware scheduling — BEFORE history
        pending = user_context.get("pending_scheduling_info")
        if pending and pending.get("date_str"):
            schedule_context = "\n### PENDING SCHEDULING INFO\nEl usuario ya mencionó querer agendar. Tiene guardado: "
            if pending.get("property_id"):
                schedule_context += f"Propiedad: {pending['property_id']}, "
            schedule_context += f"Fecha: {pending['date_str']}"
            if pending.get("time_str"):
                schedule_context += f", Hora: {pending['time_str']}"
            schedule_context += "\nUSA ESTA INFORMACIÓN cuando el usuario seleccione una propiedad — NO preguntes de nuevo por fecha/hora.\n"
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

        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                messages.append({"role": role, "content": content})
        
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
                await memory_manager.update_user_preferences(
                    phone,
                    {"lead_score": current_score + score_increase}
                )
                logger.info(f"Lead score actualizado: +{score_increase} para {phone}")
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
            await memory_manager.extract_and_save_preferences(phone, message, current_prefs)
            logger.info(f"Preferencias extraídas y guardadas exitosamente")
        except Exception as e:
            logger.error(f"Error guardando preferencias: {e}")
    
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

"""
Router principal del chatbot.
Procesa mensajes y decide la respuesta basada en intent + estado.

Estrategia:
- Fast path para intents simples (GREETING, HUMAN_HANDOFF) - sin LLM
- Agent path para intents complejos (PROPERTY_SEARCH, PROPERTY_DETAILS, etc.) - con MiniMax M2.5
"""
from typing import Optional
from datetime import datetime
from loguru import logger

from app.core.memory import memory_manager
from app.core.state_machine import state_machine, ConversationStateEnum
from app.core.classifier import intent_classifier, IntentClassification
from app.core.intent import Intent
from app.db.repository import UserRepository
from app.db.models import User


# Only truly simple intents belong on the fast path (no LLM needed).
# PROPERTY_SEARCH and SCHEDULE_APPOINTMENT were here by mistake — they require
# the agent + tool calling; routing them to _generate_response completely
# bypasses the LLM and produces stub responses.
FAST_PATH_INTENTS = {Intent.GREETING, Intent.HUMAN_HANDOFF}


class Router:
    """
    Router principal del chatbot de bienes raíces.
    Coordina la clasificación de intent y la respuesta apropiada.
    
    Estrategia de routing:
    - FAST PATH: GREETING, HUMAN_HANDOFF → respuesta directa sin LLM (baja latencia)
    - AGENT PATH: PROPERTY_SEARCH, PROPERTY_DETAILS, SCHEDULE_APPOINTMENT, FAQ → agent con MiniMax M2.5
    """
    
    def __init__(self):
        self.memory = memory_manager
        self.state = state_machine
        self.classifier = intent_classifier
        self._agent = None
    
    @property
    def agent(self):
        """Lazy load del agente para evitar imports circulares."""
        if self._agent is None:
            from app.agents.real_estate_agent import real_estate_agent
            self._agent = real_estate_agent
        return self._agent
    
    async def process_message(
        self,
        phone: str,
        message_text: str,
        media_url: Optional[str] = None
    ) -> dict:
        """
        Procesa un mensaje del usuario y retorna la respuesta.
        
        Args:
            phone: Número de WhatsApp del usuario
            message_text: Texto del mensaje
            media_url: URL de multimedia si existe
            
        Returns:
            dict con:
            - response_text: Texto de respuesta
            - intent: Intent clasificado
            - next_state: Nuevo estado del usuario
            - rich_content: Contenido adicional (propiedades, etc.)
        """
        logger.info(f"Procesando mensaje de {phone}: {message_text[:50]}...")
        
        try:
            # 1. Obtener contexto actual
            context = await self.memory.get_user_context(phone)
            current_state = await self.state.get_state(phone)
            logger.debug(f"Estado actual: {current_state}")
            
            # 2. Clasificar intent
            classification = await self.classifier.classify(message_text)
            logger.info(f"Intent: {classification.intent.value} (conf: {classification.confidence})")
            
            # 3. Actualizar last_interaction en PostgreSQL
            await self._update_last_interaction(phone)
            
            # 4. Guardar mensaje del usuario en memoria
            await self.memory.save_message(phone, "user", message_text, media_url)
            
            # 5. Decidir: fast path o agent path
            if classification.intent in FAST_PATH_INTENTS:
                # Fast path: respuesta directa sin LLM
                response = await self._generate_response(
                    phone=phone,
                    message=message_text,
                    classification=classification,
                    current_state=current_state,
                    context=context
                )
            else:
                # Agent path: usar MiniMax M2.5 con tool calling
                try:
                    agent_result = await self.agent.process_turn(
                        phone=phone,
                        user_message=message_text,
                        intent=classification.intent
                    )
                    response = {
                        "response_text": agent_result.get("response_text", ""),
                        "intent": classification.intent.value,
                        "next_state": agent_result.get("next_state", current_state),
                        "rich_content": agent_result.get("rich_content") or {},
                        "tools_used": agent_result.get("tools_used", [])
                    }
                except Exception as e:
                    logger.error(f"Error en agent: {e}")
                    # Fallback al path original si el agent falla
                    response = await self._generate_response(
                        phone=phone,
                        message=message_text,
                        classification=classification,
                        current_state=current_state,
                        context=context
                    )
            
            # 6. Guardar respuesta del asistente en memoria
            if response.get("response_text"):
                await self.memory.save_message(phone, "assistant", response["response_text"])
            
            logger.info(f"Respuesta generada: {response.get('response_text', '')[:50]}...")
            
            return response
            
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {e}")
            return {
                "response_text": "Disculpa, tuve un problema al procesar tu mensaje. ¿Podrías repetirlo?",
                "intent": Intent.UNKNOWN.value,
                "next_state": "idle",
                "rich_content": {}
            }
    
    async def _update_last_interaction(self, phone: str) -> None:
        """Actualiza last_interaction en la tabla de usuarios.

        Uses the shared async_session_factory (singleton connection pool) rather
        than creating a new engine per call, which was leaking connections.
        update_user_preferences always sets last_interaction internally, so this
        is a lightweight call with minimal DB overhead.
        """
        try:
            await memory_manager.update_user_preferences(phone, {})
        except Exception as e:
            logger.warning(f"Error al actualizar last_interaction: {e}")
    
    async def _generate_response(
        self,
        phone: str,
        message: str,
        classification: IntentClassification,
        current_state: str,
        context: dict
    ) -> dict:
        """Genera la respuesta basada en intent y estado."""
        
        intent = classification.intent
        entities = classification.extracted_entities
        
        # Guardar entidades extraídas en contexto
        if entities.model_dump(exclude_none=True):
            context["extracted_entities"] = entities.model_dump(exclude_none=True)
        
        # =====================================================================
        # Lógica de respuesta por intent
        # =====================================================================
        
        # GREETING - siempre atender
        if intent == Intent.GREETING:
            await self.state.set_state(phone, ConversationStateEnum.QUALIFYING.value)
            return {
                "response_text": "¡Hola! 👋 Bienvenido a InmuebleBot. ¿En qué puedo ayudarte hoy? ¿Buscas comprar o alquilar una propiedad?",
                "intent": intent.value,
                "next_state": ConversationStateEnum.QUALIFYING.value,
                "rich_content": {}
            }
        
        # PROPERTY_SEARCH - buscar propiedades
        if intent == Intent.PROPERTY_SEARCH:
            # Construir criterios de búsqueda desde entidades extraídas
            criteria = self._build_search_criteria(entities)
            
            # Actualizar estado
            await self.state.set_state(
                phone, 
                ConversationStateEnum.SEARCHING.value, 
                {"search_criteria": criteria}
            )
            
            # Buscar propiedades usando PropertyService
            properties = await self._search_properties(criteria)
            
            # Formatear respuesta
            if properties:
                response_text, rich_content = self._format_search_results(properties, criteria)
            else:
                response_text = "No encontré propiedades con esos criterios. ¿Quieres probar con otras opciones? (por ejemplo, diferente ubicación o presupuesto)"
                rich_content = {"search_criteria": criteria, "action": "no_results"}
            
            return {
                "response_text": response_text,
                "intent": intent.value,
                "next_state": ConversationStateEnum.SEARCHING.value,
                "rich_content": rich_content
            }
        
        # PROPERTY_DETAILS - mostrar detalles de propiedad
        if intent == Intent.PROPERTY_DETAILS:
            selected_property = context.get("selected_property_id")
            if selected_property:
                return {
                    "response_text": f"Aquí están los detalles de la propiedad que mencionas. ¿Te gustaría agendar una visita?",
                    "intent": intent.value,
                    "next_state": ConversationStateEnum.VIEWING_PROPERTY.value,
                    "rich_content": {
                        "property_id": selected_property,
                        "action": "show_property_details"
                    }
                }
            else:
                return {
                    "response_text": "Para mostrarte los detalles de una propiedad, necesito saber cuál te interesa. ¿Tienes alguna propiedad en mente?",
                    "intent": intent.value,
                    "next_state": ConversationStateEnum.SEARCHING.value,
                    "rich_content": {}
                }
        
        # SCHEDULE_APPOINTMENT - agendar cita
        if intent == Intent.SCHEDULE_APPOINTMENT:
            await self.state.set_state(phone, ConversationStateEnum.BOOKING.value)
            
            # Si hay una propiedad seleccionada
            property_id = context.get("selected_property_id")
            
            return {
                "response_text": "¡Excelente! Para agendar una visita necesito algunos datos. ¿Qué fecha y horario te conviene?",
                "intent": intent.value,
                "next_state": ConversationStateEnum.BOOKING.value,
                "rich_content": {
                    "property_id": property_id,
                    "action": "collect_appointment_details"
                }
            }
        
        # FAQ - preguntas frecuentes
        if intent == Intent.FAQ:
            # Placeholder para respuestas de FAQ
            return {
                "response_text": "Gracias por tu pregunta. Un agente te responderá pronto con más información. ¿Hay algo más en lo que pueda ayudarte?",
                "intent": intent.value,
                "next_state": current_state,
                "rich_content": {"action": "faq_response_pending"}
            }
        
        # HUMAN_HANDOFF - escalar a agente humano
        if intent == Intent.HUMAN_HANDOFF:
            from app.services.handoff_service import handoff_service
            
            handoff_result = await handoff_service.trigger_handoff(phone, "user_requested")
            
            await self.state.set_state(phone, ConversationStateEnum.HUMAN_ASSISTANCE.value, {"reason": "user_requested"})
            
            response_text = handoff_result.get(
                "message",
                "Un agente humano te contactará pronto. Mientras tanto, ¿hay algo más en lo que pueda ayudarte?"
            )
            
            return {
                "response_text": response_text,
                "intent": intent.value,
                "next_state": ConversationStateEnum.HUMAN_ASSISTANCE.value,
                "rich_content": {"action": "handoff_initiated", "summary": handoff_result.get("summary", "")}
            }
        
        # UNKNOWN - mensaje no entendido
        return {
            "response_text": "No entiendo tu mensaje. ¿Podrías ser más específico? Puedo ayudarte a buscar propiedades, agendar visitas o responder preguntas frecuentes.",
            "intent": Intent.UNKNOWN.value,
            "next_state": current_state,
            "rich_content": {}
        }
    
    def _build_search_message(self, entities) -> str:
        """Construye un mensaje descriptivo de la búsqueda."""
        parts = []
        
        if entities.property_type:
            parts.append(f"un {entities.property_type}")
        else:
            parts.append("una propiedad")
        
        if entities.location:
            parts.append(f"en {entities.location}")
        
        if entities.operation_type:
            if entities.operation_type == "venta":
                parts.append("en venta")
            elif entities.operation_type == "alquiler":
                parts.append("para alquilar")
        
        if entities.budget_max:
            parts.append(f"hasta ${entities.budget_max:,} USD")
        
        if entities.bedrooms:
            parts.append(f"con {entities.bedrooms} dormitorios")
        
        return " ".join(parts)
    
    def _format_search_criteria(self, entities) -> str:
        """Formatea los criterios de búsqueda para mostrar al usuario."""
        criteria = []
        
        if entities.location:
            criteria.append(f"ubicación: {entities.location}")
        if entities.property_type:
            criteria.append(f"tipo: {entities.property_type}")
        if entities.budget_max:
            criteria.append(f"presupuesto: hasta ${entities.budget_max:,} USD")
        if entities.bedrooms:
            criteria.append(f"dormitorios: {entities.bedrooms}")
        
        return ", ".join(criteria) if criteria else "propiedades"
    
    def _build_search_criteria(self, entities) -> dict:
        """Construye criterios de búsqueda desde entidades extraídas."""
        criteria = {}
        
        if entities.location:
            criteria["location"] = entities.location
        if entities.budget_min:
            criteria["budget_min"] = entities.budget_min
        if entities.budget_max:
            criteria["budget_max"] = entities.budget_max
        if entities.bedrooms:
            criteria["bedrooms"] = entities.bedrooms
        if entities.bathrooms:
            criteria["bathrooms"] = entities.bathrooms
        if entities.property_type:
            criteria["property_type"] = entities.property_type
        if entities.operation_type:
            criteria["operation_type"] = entities.operation_type
        
        criteria["limit"] = 8
        return criteria
    
    async def _search_properties(self, criteria: dict) -> list:
        """Busca propiedades usando PropertyService."""
        from app.services.property_service import property_service
        
        try:
            properties = await property_service.search_properties(criteria)
            return properties
        except Exception as e:
            logger.error(f"Error al buscar propiedades: {e}")
            return []
    
    def _prop_attr(self, p, attr: str, default=None):
        """Helper para obtener atributo de dict u objeto Property."""
        if isinstance(p, dict):
            return p.get(attr, default)
        return getattr(p, attr, default)
    
    def _format_properties_text(self, properties: list) -> str:
        """Formatea propiedades (soporta dict u objeto Property)."""
        lines = []
        lines.append(f"🏠 *Encontré {len(properties)} propiedades:*\n")
        
        for i, prop in enumerate(properties, 1):
            title = self._prop_attr(prop, "title", "Sin título")
            title = title[:60] + "..." if len(title) > 60 else title
            
            prop_type = self._prop_attr(prop, "type", "venta")
            price = self._prop_attr(prop, "price", 0)
            if prop_type == "alquiler":
                price_str = f"${price:,}/mes"
            else:
                price_str = f"${price:,}"
            
            bedrooms = self._prop_attr(prop, "bedrooms")
            bathrooms = self._prop_attr(prop, "bathrooms")
            area_m2 = self._prop_attr(prop, "area_m2")
            
            features = []
            if bedrooms:
                features.append(f"🛏 {bedrooms} hab")
            if bathrooms:
                features.append(f"🛁 {bathrooms} baños")
            if area_m2:
                features.append(f"📐 {area_m2}m²")
            features_str = " | ".join(features) if features else "Sin especificar"
            
            location = self._prop_attr(prop, "location", "Ubicación no disponible")
            prop_id = self._prop_attr(prop, "id", "N/A")
            
            line = f"{i}. *{title}*\n"
            line += f"   💰 {price_str} | {features_str}\n"
            line += f"   📍 {location}\n"
            line += f"   🔍 ID: `{prop_id}`\n"
            lines.append(line)
        
        return "\n".join(lines)
    
    def _format_search_results(self, properties: list, criteria: dict) -> tuple:
        """Formatea los resultados de búsqueda para WhatsApp."""
        
        if not properties:
            return (
                "No encontré propiedades con esos criterios. ¿Quieres probar con otras opciones?",
                {"search_criteria": criteria, "action": "no_results"}
            )
        
        # Formatear lista de propiedades
        properties_text = self._format_properties_text(properties)
        
        # Agregar mensaje de seguimiento
        response = (
            f"Perfecto, entiendo que buscas {self._format_search_criteria_text(criteria)}. "
            f" Aquí tienes las opciones:\n\n{properties_text}\n\n"
            "¿Te interesa alguna propiedad específica? ¿O quieres agendar una visita?"
        )
        
        # Preparar rich content con datos de propiedades
        rich_content = {
            "search_criteria": criteria,
            "action": "show_search_results",
            "properties": [
                {
                    "id": str(self._prop_attr(p, "id", "")),
                    "title": self._prop_attr(p, "title", ""),
                    "price": self._prop_attr(p, "price", 0),
                    "location": self._prop_attr(p, "location", ""),
                    "type": self._prop_attr(p, "type", ""),
                    "bedrooms": self._prop_attr(p, "bedrooms"),
                    "bathrooms": self._prop_attr(p, "bathrooms"),
                    "area_m2": self._prop_attr(p, "area_m2")
                }
                for p in properties[:5]
            ]
        }
        
        return response, rich_content
    
    def _format_search_criteria_text(self, criteria: dict) -> str:
        """Formatea criterios de búsqueda en texto legible."""
        parts = []
        
        if criteria.get("location"):
            parts.append(f"en {criteria['location']}")
        if criteria.get("property_type"):
            parts.append(f"tipo: {criteria['property_type']}")
        if criteria.get("budget_max"):
            parts.append(f"hasta ${criteria['budget_max']:,}")
        if criteria.get("bedrooms"):
            parts.append(f"{criteria['bedrooms']} dormitorios")
        
        return " ".join(parts) if parts else "propiedades"


# Instancia global del router
router = Router()
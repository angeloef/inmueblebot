"""
Máquina de estados finitos para controlar el flujo de conversación.

Estados:
- idle: El usuario no ha iniciado conversación o está inactivo
- qualifying: Recolectando información del usuario (nombre, presupuesto, ubicación)
- searching: El usuario está buscando propiedades
- viewing_property: El usuario está viendo detalles de una propiedad específica
- booking: Agendando una cita para visitar la propiedad
- completed: La conversación terminó exitosamente (cita agendada o usuario satisfecho)
- handoff: Escalando a un agente humano

Transiciones válidas:
- idle -> qualifying: Usuario envía mensaje inicial
- idle -> searching: Usuario busca propiedades directamente
- qualifying -> searching: Usuario proporciona suficiente información
- searching -> viewing_property: Usuario selecciona una propiedad
- searching -> qualifying: Usuario proporciona más detalles
- viewing_property -> booking: Usuario quiere agendar visita
- viewing_property -> searching: Usuario vuelve a buscar
- booking -> completed: Cita confirmada
- booking -> viewing_property: Usuario cancela agendamiento
- * -> handoff: Usuario pide hablar con humano
- * -> idle: Timeout o conversación inactiva

Con soporte para:
- Reconexión automática con exponential backoff
- Degradación graceful si Redis no está disponible
"""
import asyncio
from enum import Enum
from typing import Optional, Callable
from datetime import datetime, timedelta
import redis.asyncio as redis
import json
from loguru import logger

from app.core.config import get_settings
from app.core.identity import get_identity_key


class ConversationStateEnum(str, Enum):
    """Estados posibles de la conversación — v2.0 expanded state map."""
    IDLE = "idle"
    QUALIFYING = "qualifying"
    SEARCHING = "searching"
    VIEWING_PROPERTY = "viewing_property"
    # ── Viewing substates (v3.0) — one tool each, same pattern as scheduling ──
    VIEWING_DETAIL = "viewing_detail"    # user asked for more info → get_property_details
    VIEWING_PHOTOS = "viewing_photos"    # user asked for photos → get_property_images
    VIEWING_COMPARE = "viewing_compare"  # user asked to compare → compare_properties
    # ── Scheduling substates (v2.0) ──
    SCHEDULING_ASK_DATE = "scheduling_ask_date"
    SCHEDULING_ASK_TIME = "scheduling_ask_time"
    SCHEDULING_CONFIRM = "scheduling_confirm"
    SCHEDULING_ASK_NAME = "scheduling_ask_name"
    # ── Legacy scheduling state (deprecated, maps to SCHEDULING_ASK_DATE) ──
    BOOKING = "booking"
    # ── Post-scheduling ──
    COMPLETED = "completed"
    # ── Appointment management ──
    APPOINTMENT_MANAGEMENT = "appointment_management"
    # ── FAQ ──
    FAQ = "faq"
    # ── Escalation ──
    OUT_OF_SCOPE = "out_of_scope"
    HANDOFF = "handoff"
    HUMAN_ASSISTANCE = "human_assistance"


class TransitionError(Exception):
    """Error personalizado para transiciones inválidas."""
    pass


class ConversationState:
    """
    Gestor de estado de conversación con persistencia Redis + PostgreSQL.
    """
    
    # Match MemoryManager.CONTEXT_TTL so state and context expire together.
    # 30 min was too short: state reset to 'idle' while last_shown_properties
    # was still alive in context, producing stale property references.
    STATE_TTL = get_settings().STATE_TTL if hasattr(get_settings(), 'STATE_TTL') else 86400
    
    VALID_TRANSITIONS = {
        ConversationStateEnum.IDLE: [
            ConversationStateEnum.QUALIFYING,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.FAQ,
            ConversationStateEnum.OUT_OF_SCOPE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.QUALIFYING: [
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.FAQ,
            ConversationStateEnum.OUT_OF_SCOPE,
            ConversationStateEnum.QUALIFYING,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.SEARCHING: [
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.QUALIFYING,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SCHEDULING_ASK_TIME,
            ConversationStateEnum.OUT_OF_SCOPE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.VIEWING_PROPERTY: [
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.VIEWING_DETAIL,
            ConversationStateEnum.VIEWING_PHOTOS,
            ConversationStateEnum.VIEWING_COMPARE,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.FAQ,
            ConversationStateEnum.OUT_OF_SCOPE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.VIEWING_DETAIL: [
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.VIEWING_PHOTOS,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.IDLE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.VIEWING_PHOTOS: [
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.VIEWING_DETAIL,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.IDLE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.VIEWING_COMPARE: [
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.VIEWING_DETAIL,
            ConversationStateEnum.VIEWING_PHOTOS,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.IDLE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.SCHEDULING_ASK_DATE: [
            ConversationStateEnum.SCHEDULING_ASK_TIME,
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.OUT_OF_SCOPE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.SCHEDULING_ASK_TIME: [
            ConversationStateEnum.SCHEDULING_CONFIRM,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SCHEDULING_ASK_TIME,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.SCHEDULING_CONFIRM: [
            ConversationStateEnum.IDLE,
            ConversationStateEnum.COMPLETED,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SCHEDULING_ASK_NAME,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.SCHEDULING_ASK_NAME: [
            ConversationStateEnum.SCHEDULING_CONFIRM,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        # ── Legacy BOOKING maps to SCHEDULING_ASK_DATE ──
        ConversationStateEnum.BOOKING: [
            ConversationStateEnum.COMPLETED,
            ConversationStateEnum.VIEWING_PROPERTY,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SCHEDULING_ASK_TIME,
            ConversationStateEnum.IDLE,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.COMPLETED: [
            ConversationStateEnum.IDLE,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.QUALIFYING,
        ],
        ConversationStateEnum.APPOINTMENT_MANAGEMENT: [
            ConversationStateEnum.IDLE,
            ConversationStateEnum.SCHEDULING_ASK_DATE,
            ConversationStateEnum.SCHEDULING_ASK_TIME,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.FAQ: [
            ConversationStateEnum.IDLE,
            ConversationStateEnum.QUALIFYING,
            ConversationStateEnum.SEARCHING,
            ConversationStateEnum.FAQ,
            ConversationStateEnum.HANDOFF,
            ConversationStateEnum.HUMAN_ASSISTANCE,
        ],
        ConversationStateEnum.OUT_OF_SCOPE: [
            ConversationStateEnum.HUMAN_ASSISTANCE,
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.HANDOFF: [
            ConversationStateEnum.IDLE,
        ],
        ConversationStateEnum.HUMAN_ASSISTANCE: [
            ConversationStateEnum.IDLE,
        ],
    }

    # ── State → Allowed Tools (v2.0 tool gating) ──
    STATE_TOOLS = {
        ConversationStateEnum.IDLE: [],
        ConversationStateEnum.QUALIFYING: [
            "search_properties",
            "get_faq_answer",
            "update_user_preferences",
        ],
        ConversationStateEnum.SEARCHING: [
            "search_properties",
            "get_property_details",
            "get_property_images",
            "refine_search",
            "recommend_properties",
            "update_user_preferences",
            "get_faq_answer",
        ],
        ConversationStateEnum.VIEWING_PROPERTY: [
            "get_property_details",
            "get_property_images",
            "compare_properties",
            "update_user_preferences",
            "get_faq_answer",
        ],
        ConversationStateEnum.VIEWING_DETAIL: [
            "get_property_details",
            "get_property_images",
            "update_user_preferences",
        ],
        ConversationStateEnum.VIEWING_PHOTOS: [
            "get_property_images",
            "get_property_details",
            "update_user_preferences",
        ],
        ConversationStateEnum.VIEWING_COMPARE: [
            "compare_properties",
            "get_property_details",
            "update_user_preferences",
        ],
        ConversationStateEnum.SCHEDULING_ASK_DATE: [
            "schedule_visit",
            "get_property_details",
            "get_property_images",
            "update_user_preferences",
        ],
        ConversationStateEnum.SCHEDULING_ASK_TIME: [
            "schedule_visit",
            "update_user_preferences",
        ],
        ConversationStateEnum.SCHEDULING_CONFIRM: [
            "schedule_visit",
            "update_user_preferences",
        ],
        ConversationStateEnum.SCHEDULING_ASK_NAME: [
            "schedule_visit",
            "update_user_preferences",
        ],
        ConversationStateEnum.BOOKING: [
            "schedule_visit",
            "get_property_details",
            "update_user_preferences",
        ],
        ConversationStateEnum.COMPLETED: [
            "search_properties",
            "get_faq_answer",
            "update_user_preferences",
        ],
        ConversationStateEnum.APPOINTMENT_MANAGEMENT: [
            "get_my_appointments",
            "reschedule_appointment",
            "cancel_appointment",
            "get_property_details",
            "update_user_preferences",
        ],
        ConversationStateEnum.FAQ: [
            "get_faq_answer",
            "update_user_preferences",
        ],
        ConversationStateEnum.OUT_OF_SCOPE: [],
        ConversationStateEnum.HANDOFF: [
            "request_human_assistance",
        ],
        ConversationStateEnum.HUMAN_ASSISTANCE: [
            "request_human_assistance",
        ],
    }
    
    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._redis_url = settings.resolve_redis_url()
        self._redis_available = False
        self._connection_tested = False
        self._max_retries = 5
        self._retry_delay = 0.5
    
    async def check_health(self) -> dict:
        """Verifica el estado de Redis."""
        try:
            r = await self._get_redis_with_retry()
            await r.ping()
            self._redis_available = True
            self._connection_tested = True
            return {"status": "healthy", "redis": "connected"}
        except Exception as e:
            self._redis_available = False
            self._connection_tested = True
            return {"status": "unavailable", "error": str(e)[:100]}
    
    async def _get_redis_with_retry(self) -> redis.Redis:
        """Obtiene cliente Redis con reintentos y fast-fail."""
        if self._connection_tested and not self._redis_available:
            raise ConnectionError("Redis previously marked unavailable")

        last_error = None

        for attempt in range(self._max_retries):
            try:
                if self._redis is None:
                    self._redis = redis.from_url(
                        self._redis_url,
                        decode_responses=True,
                        socket_connect_timeout=10,
                        socket_timeout=15,
                    )

                await self._redis.ping()
                self._redis_available = True
                self._connection_tested = True
                return self._redis

            except Exception as e:
                last_error = e
                self._redis_available = False
                self._connection_tested = True
                delay = self._retry_delay * (2 ** attempt)
                logger.warning(f"[StateMachine] Redis retry {attempt + 1}/{self._max_retries}: {e}")
                await asyncio.sleep(delay)

        logger.error(f"[StateMachine] Redis no disponible después de {self._max_retries} intentos")
        raise last_error
    
    def _is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Verifica si la transición es válida."""
        try:
            from_enum = ConversationStateEnum(from_state)
            to_enum = ConversationStateEnum(to_state)
            
            allowed = self.VALID_TRANSITIONS.get(from_enum, [])
            return to_enum in allowed
        except ValueError:
            return to_state == ConversationStateEnum.IDLE.value
    
    async def get_state(self, phone: str) -> str:
        """Obtiene el estado actual de la conversación del usuario."""
        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:state"
            state = await r.get(key)
            if state:
                return state
            return ConversationStateEnum.IDLE.value
        except Exception as e:
            logger.warning(f"Redis no disponible para estado: {e}")
            return ConversationStateEnum.IDLE.value
    
    async def set_state(
        self,
        phone: str,
        new_state: str,
        context: Optional[dict] = None,
        allow_invalid: bool = False
    ) -> bool:
        """Establece un nuevo estado para la conversación."""
        current_state = await self.get_state(phone)

        if not allow_invalid and not self._is_valid_transition(current_state, new_state):
            error_msg = f"Transición inválida: {current_state} -> {new_state}"
            logger.warning(f"{error_msg} para {phone}")
            raise TransitionError(error_msg)

        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:state"
            prev_key = f"user:{identity_key}:previous_state"

            # Save current state as previous before overwriting
            await r.setex(prev_key, self.STATE_TTL, current_state)
            await r.setex(key, self.STATE_TTL, new_state)

            if context:
                context_key = f"user:{identity_key}:state_context"
                context["state"] = new_state
                context["updated_at"] = datetime.utcnow().isoformat()
                await r.setex(context_key, self.STATE_TTL, json.dumps(context, default=str))

            logger.info(f"Estado cambiado para {phone}: {current_state} -> {new_state}")
            return True
        except Exception as e:
            logger.warning(f"Redis no disponible para set_state: {e}")
            return True
    
    async def get_state_context(self, phone: str) -> Optional[dict]:
        """Obtiene el contexto adicional del estado actual."""
        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:state_context"
            data = await r.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Redis no disponible para get_state_context: {e}")
            return None
    
    async def reset_state(self, phone: str) -> bool:
        """Resetea el estado a idle y limpia el contexto."""
        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
            keys = [
                f"user:{identity_key}:state",
                f"user:{identity_key}:state_context",
            ]
            await r.delete(*keys)

            logger.info(f"Estado reseteado para {phone}")
            return True
        except Exception as e:
            logger.error(f"Error al resetear estado de {phone}: {e}")
            return False
    
    async def get_previous_state(self, phone: str) -> str:
        """Obtiene el estado anterior de la conversación."""
        identity_key = get_identity_key() or phone
        try:
            r = await self._get_redis_with_retry()
            key = f"user:{identity_key}:previous_state"
            state = await r.get(key)
            if state:
                return state
            return ConversationStateEnum.IDLE.value
        except Exception as e:
            logger.warning(f"Redis no disponible para previous_state: {e}")
            return ConversationStateEnum.IDLE.value

    # ── v2.0 methods ──────────────────────────────────────────────────────────

    def get_legal_transitions(self, state: str) -> list[str]:
        """Devuelve los estados a los que se puede transicionar legalmente desde `state`."""
        try:
            from_enum = ConversationStateEnum(state)
            allowed = self.VALID_TRANSITIONS.get(from_enum, [])
            return [s.value for s in allowed]
        except ValueError:
            return [ConversationStateEnum.IDLE.value]

    def get_tools_for_state(self, state: str) -> list[str]:
        """Devuelve la lista de herramientas permitidas para un estado dado."""
        try:
            from_enum = ConversationStateEnum(state)
            return self.STATE_TOOLS.get(from_enum, [])
        except ValueError:
            return []

    async def transition(
        self,
        phone: str,
        from_state: str,
        to_state: str,
        context: Optional[dict] = None,
    ) -> bool:
        """Realiza una transición de estado con validación completa.

        Returns True si la transición fue exitosa, False si fue rechazada.
        No lanza excepción — loguea advertencias y rechaza silenciosamente.
        """
        if not self._is_valid_transition(from_state, to_state):
            logger.warning(
                f"[StateMachine] Transición ilegal rechazada: "
                f"{from_state} -> {to_state} para {phone}"
            )
            return False

        return await self.set_state(phone, to_state, context=context)

    async def close(self):
        """Cierra conexión Redis."""
        if self._redis:
            await self._redis.close()


state_machine = ConversationState()

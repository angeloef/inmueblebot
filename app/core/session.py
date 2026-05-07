"""
Gestión de sesiones de usuario.
Combina memoria + estado para proporcionar una vista unificada de la sesión del usuario.

Also exposes per-user async locks (get_user_lock) used by the webhook to serialise
concurrent messages from the same phone number and prevent read-modify-write races
on the Redis context keys.
"""
import asyncio
import time
from typing import Optional, Dict, Tuple
from datetime import datetime
from loguru import logger

# ---------------------------------------------------------------------------
# Per-user async locks
# ---------------------------------------------------------------------------

# phone → (asyncio.Lock, last_used_monotonic_timestamp)
_user_locks: Dict[str, Tuple[asyncio.Lock, float]] = {}

_LOCK_CLEANUP_THRESHOLD = 1000   # prune when dict exceeds this many entries
_LOCK_TTL               = 600    # seconds — evict locks idle > 10 min


def get_user_lock(phone: str) -> asyncio.Lock:
    """
    Return the asyncio.Lock for *phone*, creating it on first call.

    Always wrapping a message-processing turn in ``async with get_user_lock(phone):``
    ensures that two concurrent tasks for the same user are serialised, preventing
    Redis context corruption from overlapping read-modify-write operations.

    Complexity: O(1) amortised; cleanup is O(n) but only triggered when the dict
    exceeds _LOCK_CLEANUP_THRESHOLD entries.
    """
    now = time.monotonic()

    # Lazy cleanup — only pay the cost when the dict is large
    if len(_user_locks) > _LOCK_CLEANUP_THRESHOLD:
        stale = [p for p, (_, ts) in _user_locks.items() if (now - ts) > _LOCK_TTL]
        for p in stale:
            del _user_locks[p]
        if stale:
            logger.debug(f"[Session] Pruned {len(stale)} stale locks; {len(_user_locks)} remaining")

    if phone not in _user_locks:
        _user_locks[phone] = (asyncio.Lock(), now)
    else:
        lock, _ = _user_locks[phone]
        _user_locks[phone] = (lock, now)   # refresh timestamp on access

    return _user_locks[phone][0]


def active_lock_count() -> int:
    """Number of currently tracked user locks (observability hook)."""
    return len(_user_locks)

from app.core.memory import memory_manager, MemoryManager
from app.core.state_machine import state_machine, ConversationState, ConversationStateEnum


class SessionManager:
    """
    Gestor de sesiones que combina memoria y estado.
    Proporciona una API unificada para trabajar con la sesión de un usuario.
    """
    
    def __init__(self):
        self.memory = memory_manager
        self.state = state_machine
    
    # =========================================================================
    # MÉTODOS DE INICIALIZACIÓN
    # =========================================================================
    
    async def start_session(self, phone: str) -> dict:
        """
        Inicia una nueva sesión para el usuario.
        Si ya existe una sesión activa, retorna el estado actual.
        """
        # Verificar si hay una sesión activa
        current_state = await self.state.get_state(phone)
        
        if current_state != ConversationStateEnum.IDLE.value:
            # Sesión existente, retornar contexto
            context = await self.memory.get_user_context(phone)
            logger.info(f"Sesión existente para {phone}: {current_state}")
            return {
                "phone": phone,
                "state": current_state,
                "context": context,
                "is_new": False,
            }
        
        # Nueva sesión
        await self.state.set_state(phone, ConversationStateEnum.QUALIFYING.value)
        
        context = await self.memory.get_user_context(phone)
        logger.info(f"Nueva sesión iniciada para {phone}")
        
        return {
            "phone": phone,
            "state": ConversationStateEnum.QUALIFYING.value,
            "context": context,
            "is_new": True,
        }
    
    async def end_session(self, phone: str, reason: str = "completed") -> bool:
        """
        Finaliza la sesión del usuario.
        Limpia la memoria de corto plazo pero mantiene las preferencias.
        """
        await self.state.set_state(phone, ConversationStateEnum.COMPLETED.value)
        await self.memory.clear_short_term_memory(phone)
        
        logger.info(f"Sesión finalizada para {phone}: {reason}")
        return True
    
    # =========================================================================
    # MÉTODOS DE INTERACCIÓN
    # =========================================================================
    
    async def handle_message(
        self,
        phone: str,
        role: str,
        content: str,
        media_url: Optional[str] = None
    ) -> dict:
        """
        Procesa un mensaje del usuario.
        Actualiza memoria + estado.
        """
        # Guardar mensaje en memoria
        await self.memory.save_message(phone, role, content, media_url)
        
        # Actualizar preferencias con el mensaje
        # (El agente procesará el contenido y actualizará según sea necesario)
        
        # Obtener estado actual
        current_state = await self.state.get_state(phone)
        context = await self.memory.get_user_context(phone)
        
        return {
            "phone": phone,
            "state": current_state,
            "context": context,
            "message_saved": True,
        }
    
    async def update_search_context(
        self,
        phone: str,
        search_criteria: dict
    ) -> bool:
        """
        Actualiza el contexto de búsqueda del usuario.
        """
        context = await self.memory.get_user_context(phone)
        context["last_search_criteria"] = search_criteria
        context["search_count"] = context.get("search_count", 0) + 1
        
        await self.memory.save_user_context(phone, context)
        
        # Cambiar a estado de búsqueda si no está ya
        current_state = await self.state.get_state(phone)
        if current_state == ConversationStateEnum.QUALIFYING.value:
            await self.state.set_state(phone, ConversationStateEnum.SEARCHING.value)
        
        return True
    
    async def select_property(
        self,
        phone: str,
        property_id: str,
        property_summary: str
    ) -> bool:
        """
        El usuario selecciona una propiedad para ver.
        """
        context = await self.memory.get_user_context(phone)
        context["selected_property_id"] = property_id
        context["selected_property_summary"] = property_summary
        
        await self.memory.save_user_context(phone, context)
        
        # Cambiar a estado de visualización
        await self.state.set_state(
            phone,
            ConversationStateEnum.VIEWING_PROPERTY.value,
            {"property_id": property_id}
        )
        
        logger.info(f"Propiedad {property_id} seleccionada por {phone}")
        return True
    
    async def start_booking(
        self,
        phone: str,
        property_id: str
    ) -> bool:
        """
        El usuario quiere agendar una visita.
        """
        context = await self.memory.get_user_context(phone)
        context["booking_property_id"] = property_id
        
        await self.memory.save_user_context(phone, context)
        
        # Cambiar a estado de agendamiento
        await self.state.set_state(
            phone,
            ConversationStateEnum.BOOKING.value,
            {"property_id": property_id, "action": "booking"}
        )
        
        logger.info(f"Agendamiento iniciado por {phone} para propiedad {property_id}")
        return True
    
    async def confirm_booking(
        self,
        phone: str,
        appointment_id: str,
        datetime_str: str
    ) -> bool:
        """
        Confirma el agendamiento de una cita.
        """
        context = await self.memory.get_user_context(phone)
        context["last_appointment_id"] = appointment_id
        context["last_appointment_datetime"] = datetime_str
        
        await self.memory.save_user_context(phone, context)
        
        # Completar conversación
        await self.state.set_state(phone, ConversationStateEnum.COMPLETED.value)
        
        logger.info(f"Cita {appointment_id} confirmada para {phone}")
        return True
    
    async def request_handoff(self, phone: str) -> bool:
        """El usuario pide hablar con un agente humano."""
        await s
"""
Repositorio de base de datos con operaciones async.
Proporciona una capa de abstracción sobre SQLAlchemy async.
"""
from uuid import UUID
from typing import TypeVar, Generic, Type, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload

from app.db.base import Base

# Tipo genérico para modelos
ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Clase base para repositorios.
    Proporciona operaciones CRUD genéricas.
    """
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
    
    async def get(self, id: UUID) -> Optional[ModelType]:
        """Obtiene un registro por su ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_uuid(self, id: UUID) -> Optional[ModelType]:
        """Alias de get() para compatibilidad."""
        return await self.get(id)
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        """Obtiene todos los registros con paginación."""
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())
    
    async def create(self, obj: ModelType) -> ModelType:
        """Crea un nuevo registro."""
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj
    
    async def update(self, id: UUID, **kwargs) -> Optional[ModelType]:
        """Actualiza un registro por ID."""
        stmt = (
            update(self.model)
            .where(self.model.id == id)
            .values(**kwargs)
            .returning(self.model)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()
    
    async def delete(self, id: UUID) -> bool:
        """Elimina un registro por ID."""
        stmt = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0
    
    async def count(self) -> int:
        """Cuenta el total de registros."""
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()
    
    async def exists(self, id: UUID) -> bool:
        """Verifica si existe un registro."""
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(self.model.id == id)
        )
        return result.scalar_one() > 0


class UserRepository(BaseRepository):
    """Repositorio específico para usuarios."""
    
    async def get_by_phone(self, phone: str) -> Optional["User"]:
        """Obtiene un usuario por número de WhatsApp."""
        result = await self.session.execute(
            select(self.model).where(self.model.whatsapp_phone == phone)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(self, phone: str) -> "User":
        """Obtiene usuario por phone o crea uno nuevo."""
        from app.db.models import User
        user = await self.get_by_phone(phone)
        if not user:
            user = User(whatsapp_phone=phone)
            self.session.add(user)
            await self.session.flush()
            await self.session.refresh(user)
        return user
    
    async def search_by_preferences(
        self,
        location: Optional[str] = None,
        budget_min: Optional[int] = None,
        budget_max: Optional[int] = None,
        property_type: Optional[list[str]] = None,
    ) -> list["User"]:
        """Busca usuarios por preferencias."""
        from app.db.models import User
        
        query = select(User)
        
        if location:
            query = query.where(User.location_preferences.contains([location]))
        
        if budget_min is not None:
            query = query.where(User.budget_min >= budget_min)
        
        if budget_max is not None:
            query = query.where(User.budget_max <= budget_max)
        
        if property_type:
            query = query.where(User.property_type.overlap(property_type))
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_active_leads(self, hours: int = 24) -> list["User"]:
        """Obtiene leads activos (interacciones recientes)."""
        from datetime import datetime, timedelta
        from app.db.models import User
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.session.execute(
            select(User)
            .where(User.last_interaction >= cutoff)
            .order_by(User.lead_score.desc())
        )
        return list(result.scalars().all())


class PropertyRepository(BaseRepository):
    """Repositorio específico para propiedades."""
    
    async def get_by_external_id(self, external_id: str) -> Optional["Property"]:
        """Obtiene propiedad por ID externo."""
        result = await self.session.execute(
            select(self.model).where(self.model.external_id == external_id)
        )
        return result.scalar_one_or_none()
    
    async def search(
        self,
        type: Optional[str] = None,
        location: Optional[str] = None,
        budget_min: Optional[int] = None,
        budget_max: Optional[int] = None,
        bedrooms_min: Optional[int] = None,
        bathrooms_min: Optional[int] = None,
        area_min: Optional[int] = None,
        property_type: Optional[str] = None,
        status: str = "available",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list["Property"], int]:
        """
        Busca propiedades con filtros.
        Retorna (lista, total).
        """
        from app.db.models import Property
        
        query = select(Property).where(Property.status == status)
        
        if type:
            query = query.where(Property.type == type)

        if property_type:
            from app.utils.sanitizer import map_property_type_to_building_type
            building_type = map_property_type_to_building_type(property_type)
            if building_type:
                query = query.where(
                    Property.extra_data[('building_type',)].as_string() == building_type
                )
        
        if location:
            from app.utils.sanitizer import normalize_location
            from sqlalchemy import or_

            loc_clean = location.strip().lower()
            loc_norm = normalize_location(location)

            # Build multiple matching strategies for flexible address search
            filters = []

            # Strategy 1: Original query as-is (full ILIKE)
            filters.append(Property.location.ilike(f"%{loc_clean}%"))

            # Strategy 2: Normalized (prefix stripped, numbers removed)
            # e.g. "calle sarmiento" → "sarmiento" matches "Sarmiento 285, Oberá"
            if loc_norm and loc_norm != loc_clean:
                filters.append(Property.location.ilike(f"%{loc_norm}%"))

            # Strategy 3: Individual words (>2 chars) OR'd together
            # e.g. "calle sarmiento" matches anything containing "calle" OR "sarmiento"
            words = [w for w in loc_clean.split() if len(w) > 2]
            # Also add normalized words (deduplicated)
            if loc_norm and loc_norm != loc_clean:
                norm_words = [w for w in loc_norm.split() if len(w) > 2]
                words.extend(w for w in norm_words if w not in words)
            if words:
                word_filters = [Property.location.ilike(f"%{w}%") for w in words]
                filters.append(or_(*word_filters))

            # Combine all strategies with OR — any matching strategy returns results
            query = query.where(or_(*filters))
        
        if budget_min is not None:
            query = query.where(Property.price >= budget_min)
        
        if budget_max is not None:
            query = query.where(Property.price <= budget_max)
        
        if bedrooms_min is not None:
            query = query.where(Property.bedrooms >= bedrooms_min)
        
        if bathrooms_min is not None:
            query = query.where(Property.bathrooms >= bathrooms_min)
        
        if area_min is not None:
            query = query.where(Property.area_m2 >= area_min)
        
        # Contar total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()
        
        # Aplicar paginación
        query = query.order_by(Property.price.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        
        return list(result.scalars().all()), total
    
    async def get_featured(self, limit: int = 10) -> list["Property"]:
        """Obtiene propiedades destacadas (ej. con metadata)."""
        from app.db.models import Property
        
        result = await self.session.execute(
            select(Property)
            .where(Property.status == "available")
            .order_by(Property.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class ConversationRepository(BaseRepository):
    """Repositorio específico para conversaciones."""
    
    async def get_by_session(self, session_id: str) -> Optional["Conversation"]:
        """Obtiene conversación por session_id."""
        result = await self.session.execute(
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(self.model.created_at.desc())
        )
        return result.scalar_one_or_none()
    
    async def get_active(self, user_id: UUID) -> Optional["Conversation"]:
        """Obtiene la conversación activa más reciente del usuario."""
        from app.db.models import Conversation
        
        result = await self.session.execute(
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.state.notin_(["closed", "completed"])
            )
            .order_by(Conversation.created_at.desc())
        )
        return result.scalar_one_or_none()
    
    async def create_for_user(self, user_id: UUID, session_id: str) -> "Conversation":
        """Crea una nueva conversación para un usuario."""
        from app.db.models import Conversation
        
        conv = Conversation(user_id=user_id, session_id=session_id)
        return await self.create(conv)


class MessageRepository(BaseRepository):
    """Repositorio específico para mensajes."""
    
    async def get_by_conversation(
        self,
        conversation_id: UUID,
        limit: int = 100,
    ) -> list["Message"]:
        """Obtiene mensajes de una conversación."""
        from app.db.models import Message
        
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_recent(
        self,
        conversation_id: UUID,
        limit: int = 10,
    ) -> list["Message"]:
        """Obtiene los N mensajes más recientes."""
        from app.db.models import Message
        
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp.desc())
            .limit(limit)
        )
        # Revertir para tener orden cronológico
        msgs = list(result.scalars().all())
        return list(reversed(msgs))


class AppointmentRepository(BaseRepository):
    """Repositorio específico para citas."""
    
    async def get_by_user(self, user_id: UUID) -> list["Appointment"]:
        """Obtiene citas de un usuario."""
        from app.db.models import Appointment
        
        result = await self.session.execute(
            select(Appointment)
            .where(Appointment.user_id == user_id)
            .order_by(Appointment.start_time.desc())
        )
        return list(result.scalars().all())
    
    async def get_by_property(self, property_id: UUID) -> list["Appointment"]:
        """Obtiene citas de una propiedad."""
        from app.db.models import Appointment
        
        result = await self.session.execute(
            select(Appointment)
            .where(Appointment.property_id == property_id)
            .order_by(Appointment.start_time.desc())
        )
        return list(result.scalars().all())
    
    async def get_upcoming(self, hours: int = 24) -> list["Appointment"]:
        """Obtiene citas próximas."""
        from datetime import datetime, timedelta
        from app.db.models import Appointment
        
        now = datetime.utcnow()
        end = now + timedelta(hours=hours)
        
        result = await self.session.execute(
            select(Appointment)
            .where(
                Appointment.start_time >= now,
                Appointment.start_time <= end,
                Appointment.status == "confirmed"
            )
            .order_by(Appointment.start_time.asc())
        )
        return list(result.scalars().all())
    
    async def create_appointment(
        self,
        user_id: UUID,
        property_id: UUID,
        start_time,
        end_time,
        type: str = "visit",
        notes: str = None,
    ) -> "Appointment":
        """Crea una nueva cita."""
        from app.db.models import Appointment
        
        apt = Appointment(
            user_id=user_id,
            property_id=property_id,
            start_time=start_time,
            end_time=end_time,
            type=type,
            notes=notes,
        )
        return await self.create(apt)
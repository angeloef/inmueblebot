"""
Herramientas del agente de bienes raíces.
Funciones async que pueden ser llamadas por el LLM via tool calling.
"""
import json
from typing import Optional, Dict, Any, List
from uuid import UUID
from loguru import logger

from app.services.property_service import property_service
from app.core.memory import memory_manager


def format_property(prop) -> str:
    """
    Formatea una propiedad (soporta dict u objeto Property).
    USA original_id (integer) si está disponible, si no usa id (UUID).
    
    Args:
        prop: Objeto Property o dict con datos de propiedad
    
    Returns:
        String formateado con los detalles de la propiedad
    """
    # Use original_id (integer) if available, otherwise fallback to id
    original_id = _get_attr(prop, "original_id", None)
    if original_id:
        prop_id = str(original_id)
    else:
        prop_id = str(_get_attr(prop, "id", "N/A"))[:8]
    
    title = _get_attr(prop, "title", "Sin título")
    price = _get_attr(prop, "price", 0)
    prop_type = _get_attr(prop, "type", "venta")
    location = _get_attr(prop, "location", "Ubicación no disponible")
    bedrooms = _get_attr(prop, "bedrooms")
    bathrooms = _get_attr(prop, "bathrooms")
    area_m2 = _get_attr(prop, "area_m2")
    description = _get_attr(prop, "description")
    
    if prop_type == "alquiler":
        price_str = f"${price:,}/mes"
    else:
        price_str = f"${price:,}"
    
    title = title[:60] + "..." if len(title) > 60 else title
    
    features = []
    if bedrooms:
        features.append(f"🛏 {bedrooms} hab")
    if bathrooms:
        features.append(f"🛁 {bathrooms} baños")
    if area_m2:
        features.append(f"📐 {area_m2}m²")
    features_str = " | ".join(features) if features else "Sin especificar"
    
    lines = [
        f"🏠 *{title}*",
        f"💰 *Precio:* {price_str}",
        ""
    ]
    
    if description:
        lines.append(f"📝 *Descripción:*\n{description[:200]}...")
        lines.append("")
    
    lines.append(f"📋 *Características:* {features_str}")
    lines.append(f"📍 *Ubicación:* {location}")
    lines.append(f"🔍 *ID de propiedad:* `{prop_id}`")
    
    return "\n".join(lines)


def format_property_list(properties: List) -> str:
    """
    Formatea una lista de propiedades en texto legible para WhatsApp.
    
    Args:
        properties: Lista de objetos Property o dicts
    
    Returns:
        String formateado con los detalles de cada propiedad
    """
    if not properties:
        return "No encontré propiedades que coincidan con tu búsqueda."
    
    lines = []
    lines.append(f"🏠 *Encontré {len(properties)} propiedades:*\n")
    
    for i, prop in enumerate(properties, 1):
        # Use original_id (integer) if available
        original_id = _get_attr(prop, "original_id", None)
        if original_id:
            prop_id = str(original_id)
        else:
            prop_id = str(_get_attr(prop, "id", f"prop-{i}"))[:8]
        
        title = _get_attr(prop, "title", "Sin título")
        title = title[:50] + "..." if len(title) > 50 else title
        
        price = _get_attr(prop, "price", 0)
        prop_type = _get_attr(prop, "type", "venta")
        if prop_type == "alquiler":
            price_str = f"${price:,}/mes"
        else:
            price_str = f"${price:,}"
        
        bedrooms = _get_attr(prop, "bedrooms")
        bathrooms = _get_attr(prop, "bathrooms")
        area_m2 = _get_attr(prop, "area_m2")
        
        features = []
        if bedrooms:
            features.append(f"🛏 {bedrooms}")
        if bathrooms:
            features.append(f"🛁 {bathrooms}")
        if area_m2:
            features.append(f"📐 {area_m2}m²")
        features_str = " | ".join(features) if features else "Sin info"
        
        location = _get_attr(prop, "location", "Sin ubicación")
        
        line = f"{i}. *{title}*\n"
        line += f"   💰 {price_str} | {features_str}\n"
        line += f"   📍 {location}\n"
        line += f"   🔍 ID: `{prop_id}`"
        
        lines.append(line)
    
    return "\n\n".join(lines)


def _get_attr(obj, attr: str, default=None):
    """Helper para obtener atributo de dict u objeto."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


async def search_properties(criteria: Dict[str, Any]) -> str:
    """
    Busca propiedades según criterios específicos.
    
    Args:
        criteria: Diccionario con criterios de búsqueda:
            - location: Ciudad o zona (ej: "Posadas", "Asunción")
            - budget_max: Presupuesto máximo en USD
            - budget_min: Presupuesto mínimo en USD
            - bedrooms: Número de dormitorios (MÍNIMO)
            - bathrooms: Número de baños
            - property_type: Tipo de propiedad (casa, departamento, terreno)
            - operation_type: Tipo de operación (venta o alquiler)
            - limit: Número de resultados (default 8)
    
    Returns:
        String formateado con las propiedades encontradas o mensaje de sin resultados
    """
    logger.info("=" * 60)
    logger.info("[TOOL] search_properties LLAMADO")
    logger.info(f"[TOOL] Criterios crudos recibidos: {criteria}")
    logger.info("=" * 60)
    
    try:
        search_criteria = {}
        
        # Normalize location
        if criteria.get("location"):
            loc = criteria["location"].strip()
            search_criteria["location"] = loc
            logger.info(f"[TOOL] Location normalizada: '{loc}'")
        
        if criteria.get("budget_max"):
            search_criteria["budget_max"] = int(criteria["budget_max"])
            logger.info(f"[TOOL] Budget max: {search_criteria['budget_max']}")
        
        if criteria.get("budget_min"):
            search_criteria["budget_min"] = int(criteria["budget_min"])
            logger.info(f"[TOOL] Budget min: {search_criteria['budget_min']}")
        
        # Bedrooms - treat as MINIMUM
        if criteria.get("bedrooms"):
            search_criteria["bedrooms"] = int(criteria["bedrooms"])
            logger.info(f"[TOOL] Bedrooms (MÍNIMO): {search_criteria['bedrooms']}")
        
        if criteria.get("bathrooms"):
            search_criteria["bathrooms"] = int(criteria["bathrooms"])
            logger.info(f"[TOOL] Bathrooms: {search_criteria['bathrooms']}")
        
        if criteria.get("property_type"):
            search_criteria["property_type"] = criteria["property_type"]
            logger.info(f"[TOOL] Property type: '{search_criteria['property_type']}'")
        
        if criteria.get("operation_type"):
            search_criteria["operation_type"] = criteria["operation_type"]
        elif criteria.get("type"):
            search_criteria["operation_type"] = criteria["type"]
        
        # Ensure limit is at least 6 for better UX
        search_criteria["limit"] = max(criteria.get("limit", 8), 6)
        logger.info(f"[TOOL] Limit final: {search_criteria['limit']}")
        
        logger.info("[TOOL] Llamando a property_service.search_properties...")
        properties = await property_service.search_properties(search_criteria)
        
        # Log results
        logger.info(f"[TOOL] =======================================")
        logger.info(f"[TOOL] RESULTADO: {len(properties)} propiedades encontradas")
        for i, prop in enumerate(properties, 1):
            logger.info(f"[TOOL]   {i}. {prop.title} | {prop.location} | {prop.bedrooms} hab | ${prop.price}")
        logger.info(f"[TOOL] =======================================")
        
        return format_property_list(properties)
        
    except Exception as e:
        logger.error(f"Error en búsqueda de propiedades: {e}")
        return "Tuve un problema al buscar propiedades. ¿Podrías intentar con otros criterios?"


async def refine_search(refinement: str = None, previous_criteria: Dict[str, Any] = None) -> str:
    """
    Refina una búsqueda previa con criterios adicionales.
    
    Args:
        refinement: Tipo de refinamiento que el usuario quiere aplicar:
            - "presupuesto_menor": Reducir presupuesto
            - "presupuesto_mayor": Aumentar presupuesto
            - "mas_dormitorios": Más dormitorios
            - "menos_dormitorios": Menos dormitorios
            - "otra_zona": Cambiar zona
            - "otro_tipo": Cambiar tipo de propiedad
        previous_criteria: Criterios de la búsqueda anterior
    
    Returns:
        String con mensaje de refinamiento aplicado
    """
    if not previous_criteria:
        previous_criteria = {}
    
    refinement_messages = {
        "presupuesto_menor": "Buscando opciones más económicas...",
        "presupuesto_mayor": "Buscando opciones de mayor presupuesto...",
        "mas_dormitorios": "Buscando con más dormitorios...",
        "menos_dormitorios": "Buscando con menos dormitorios...",
        "otra_zona": "Buscando en otras zonas...",
        "otro_tipo": "Buscando otro tipo de propiedad...",
    }
    
    msg = refinement_messages.get(refinement, "Aplicando filtros adicionales...")
    
    return f"{msg} (Usa search_properties con los criterios refinados)"


async def get_property_details(property_id: str) -> str:
    """
    Obtiene los detalles de una propiedad específica por su ID.
    Soporta:
    - Integer ID (1, 2, 3... from seed data)
    - UUID (database primary key)  
    - Referencia ("opcion 5", "la primera")
    
    Args:
        property_id: ID de la propiedad (integer 1-50, UUID, o referencia)
    
    Returns:
        String formateado con los detalles de la propiedad
    """
    logger.info("=" * 60)
    logger.info(f"[get_property_details] SOLICITADO para ID: {property_id}")
    logger.info("=" * 60)
    
    try:
        prop = None
        
        # Try integer ID first - use the integer 'id' field directly
        try:
            int_id = int(property_id)
            if 1 <= int_id <= 100:
                logger.info(f"[get_property_details] Buscando por integer ID: {int_id}")
                # Use the service with direct ID lookup
                from app.db.repository import BaseRepository
                from app.db.models import Property
                from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
                from sqlalchemy.orm import sessionmaker
                from app.core.config import get_settings
                
                settings = get_settings()
                engine = create_async_engine(settings.DATABASE_URL, echo=False)
                async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                
                async with async_session_factory() as session:
                    repo = BaseRepository(Property, session)
                    prop = await repo.get(int_id)  # Direct integer ID lookup
                    
                await engine.dispose()
                
                if prop:
                    logger.info(f"[get_property_details] Encontrada por ID: {prop.id} - {prop.title}")
                    return format_property(prop)
        except Exception as e:
            logger.warning(f"[get_property_details] Integer lookup failed: {e}")
        
        # If not found, try UUID
        if not prop:
            try:
                prop_uuid = UUID(property_id)
                prop = await property_service.get_property_details(prop_uuid)
            except (ValueError, Exception) as e:
                logger.warning(f"[get_property_details] UUID lookup failed: {e}")
        
        # If still not found, try title search
        if not prop:
            logger.info(f"[get_property_details] Buscando por título: {property_id}")
            props = await property_service.search_properties({"title_ilike": f"%{property_id}%", "limit": 1})
            prop = props[0] if props else None
        
        if not prop:
            logger.warning(f"[get_property_details] Propiedad no encontrada: {property_id}")
            return f"No encontré los detalles de esa propiedad (ID: {property_id}). ¿Quieres ver otras opciones o buscar de nuevo?"
        
        logger.info(f"[get_property_details] Encontrada: {prop.title}")
        return format_property(prop)
        
    except Exception as e:
        logger.error(f"[get_property_details] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "Tuve un problema al cargar los detalles ahora. ¿Quieres buscar otras propiedades o intentar de nuevo?"


async def recommend_properties(user_preferences: Dict[str, Any]) -> str:
    """
    Recomienda propiedades basadas en las preferencias del usuario.
    
    Args:
        user_preferences: Diccionario con preferencias:
            - location_preferences: Lista de ubicaciones preferidas
            - budget_max: Presupuesto máximo
            - property_type: Tipo de propiedad buscada
            - operation_type: venta o alquiler
    
    Returns:
        String formateado con propiedades recomendadas
    """
    logger.info(f"Buscando recomendaciones para: {user_preferences}")
    
    try:
        criteria = {"limit": 5}
        
        if user_preferences.get("location_preferences"):
            locations = user_preferences["location_preferences"]
            if isinstance(locations, list) and len(locations) > 0:
                criteria["location"] = locations[0]
            elif isinstance(locations, str):
                criteria["location"] = locations
        
        if user_preferences.get("budget_max"):
            criteria["budget_max"] = user_preferences["budget_max"]
        
        if user_preferences.get("property_type"):
            prop_types = user_preferences["property_type"]
            if isinstance(prop_types, list) and len(prop_types) > 0:
                criteria["property_type"] = prop_types[0]
            elif isinstance(prop_types, str):
                criteria["property_type"] = prop_types
        
        if user_preferences.get("operation_type"):
            criteria["operation_type"] = user_preferences["operation_type"]
        
        properties = await property_service.search_properties(criteria)
        
        if not properties:
            return "No encontré propiedades que coincidan exactamente con tus preferencias. ¿Quieres ajustar los criterios de búsqueda?"
        
        return "✨ *Basado en tus preferencias, te recomiendo:*\n\n" + format_property_list(properties)
        
    except Exception as e:
        logger.error(f"Error en recomendaciones: {e}")
        return "Tuve un problema al buscar recomendaciones. ¿Quieres hacer una búsqueda manual?"


async def update_user_preferences(
    phone: str,
    location: str = None,
    budget_max: int = None,
    budget_min: int = None,
    property_type: str = None,
    operation_type: str = None,
    bedrooms: int = None
) -> str:
    """
    Guarda o actualiza las preferencias del usuario en memoria.
    
    Args:
        phone: Número de teléfono del usuario
        location: Ubicación de interés
        budget_max: Presupuesto máximo
        budget_min: Presupuesto mínimo
        property_type: Tipo de propiedad
        operation_type: venta o alquiler
        bedrooms: Dormitorios deseados
    
    Returns:
        Confirmación de que se guardaron las preferencias
    """
    logger.info(f"Actualizando preferencias para {phone}")
    
    try:
        updates = {}
        if location:
            updates["location_preferences"] = location
        if budget_max:
            updates["budget_max"] = budget_max
        if budget_min:
            updates["budget_min"] = budget_min
        if property_type:
            updates["property_type"] = property_type
        if operation_type:
            updates["operation_type"] = operation_type
        if bedrooms:
            updates["bedrooms"] = bedrooms
        
        if updates:
            await memory_manager.update_user_preferences(phone, updates)
            return "He guardado tus preferencias. ¿Qué otra información necesitas?"
        
        return "No recibí nuevas preferencias para guardar."
        
    except Exception as e:
        logger.error(f"Error al guardar preferencias: {e}")
        return "Tuve un problema al guardar tus preferencias."


async def get_user_preferences(phone: str) -> str:
    """
    Obtiene las preferencias guardadas del usuario.
    
    Args:
        phone: Número de teléfono del usuario
    
    Returns:
        String con las preferencias del usuario
    """
    try:
        context = await memory_manager.get_user_context(phone)
        prefs = context.get("preferences", {})
        
        if not prefs:
            return "No tienes preferencias guardadas aún. ¿Cuáles son tus criterios de búsqueda?"
        
        parts = []
        if prefs.get("location_preferences"):
            parts.append(f"📍 Ubicación: {prefs['location_preferences']}")
        if prefs.get("budget_max"):
            parts.append(f"💰 Presupuesto: hasta ${prefs['budget_max']:,}")
        if prefs.get("property_type"):
            parts.append(f"🏠 Tipo: {prefs['property_type']}")
        if prefs.get("operation_type"):
            parts.append(f"📋 Operación: {prefs['operation_type']}")
        
        if parts:
            return "Tus preferencias guardadas:\n" + "\n".join(parts)
        
        return "No tienes preferencias guardadas aún."
        
    except Exception as e:
        logger.error(f"Error al obtener preferencias: {e}")
        return "No pude cargar tus preferencias."


async def save_lead_info(
    phone: str,
    name: str = None,
    email: str = None,
    budget: int = None,
    notes: str = None
) -> str:
    """
    Guarda información del lead (nombre, email, presupuesto, notas).
    
    Args:
        phone: Número de teléfono
        name: Nombre completo
        email: Correo electrónico
        budget: Presupuesto informado
        notes: Notas adicionales
    
    Returns:
        Confirmación de guardado
    """
    try:
        updates = {}
        if name:
            updates["name"] = name
        if email:
            updates["email"] = email
        if budget:
            updates["budget"] = budget
        if notes:
            updates["notes"] = notes
        
        if updates:
            await memory_manager.update_user_preferences(phone, updates)
            return "He guardado tu información. ¿En qué más puedo ayudarte?"
        
        return "No recibí información para guardar."
    except Exception as e:
        logger.error(f"Error al guardar lead info: {e}")
        return "Tuve un problema al guardar tu información."


async def schedule_visit(
    property_id: str,
    date_str: str,
    time_str: str = None,
    phone: str = None
) -> str:
    """
    Agenda una visita a una propiedad específica.
    
    Args:
        property_id: ID de la propiedad a visitar
        date_str: Fecha en formato YYYY-MM-DD (ej: "2026-04-25")
        time_str: Hora en formato HH:MM (ej: "15:30"), opcional
        phone: Número de teléfono del usuario
    
    Returns:
        Mensaje de confirmación o error
    """
    from datetime import datetime, timezone as tz
    from uuid import UUID
    from app.services.appointment_service import appointment_service, format_appointment_confirmation
    from app.services.property_service import property_service
    from app.db.repository import UserRepository
    from app.db.models import User
    from app.db.session import async_session_factory

    try:
        if not phone:
            return "No tengo tu información de contacto. ¿Podrías identificarte?"
        
        if not property_id:
            return "Necesito saber qué propiedad quieres visitar."
        
        if not date_str:
            return "Necesito saber qué fecha te conviene para la visita."
        
        # Try integer ID first (like "15"), then UUID
        prop_uuid = None
        prop_int_id = None
        try:
            int_id = int(property_id)
            if 1 <= int_id <= 1000:
                prop = await property_service.get_property_details(str(int_id))
                if prop:
                    prop_uuid = prop.id
                    prop_int_id = prop.id  # Use as integer for appointments
        except (ValueError, TypeError):
            pass
        
        # If not found by integer, try UUID
        if not prop_uuid:
            try:
                prop_uuid = UUID(property_id)
            except ValueError:
                return f"El ID de propiedad '{property_id}' no es válido."
        
        property_obj = await property_service.get_property_details(prop_uuid)
        if not property_obj:
            return f"No encontré la propiedad con ID '{property_id}'."
        
        # Get integer ID for appointment table
        if prop_int_id is None:
            prop_int_id = property_obj.id
        
        async with async_session_factory() as session:
            user_repo = UserRepository(User, session)
            user = await user_repo.get_by_phone(phone)
            
            if not user:
                return "No te encontré en el sistema. ¿Podrías darme tu nombre?"
            
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            if time_str:
                time_obj = datetime.strptime(time_str, "%H:%M").time()
                start_datetime = datetime.combine(date_obj, time_obj, tzinfo=tz.utc)
            else:
                start_datetime = datetime.combine(date_obj, datetime.min.time(), tzinfo=tz.utc)
            
            if start_datetime < datetime.now(tz.utc):
                return "Lo siento, esa fecha y hora ya pasaron. Por favor selecciona una fecha futura."
            
            appointment = await appointment_service.create_appointment(
                user_id=user.id,
                property_id=prop_int_id,
                start_time=start_datetime,
                type="visit"
            )
            
            property_title = getattr(property_obj, "title", "Propiedad") if hasattr(property_obj, "title") else "Propiedad"
            
            return format_appointment_confirmation(appointment, property_title)
            
    except ValueError as e:
        logger.error(f"ValueError en agendar visita: {e}", exc_info=True)
        return str(e)
    except Exception as e:
        logger.error(f"Error al agendar visita: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        return "Tuve un problema al agendar la visita. ¿Podrías intentar de nuevo?"


async def reschedule_appointment_tool(
    appointment_id: str,
    new_date_str: str,
    new_time_str: str = None,
    phone: str = None
) -> str:
    """
    Reprograma una cita existente.
    
    Args:
        appointment_id: ID de la cita a reprogramar
        new_date_str: Nueva fecha en formato YYYY-MM-DD
        new_time_str: Nueva hora en formato HH:MM, opcional
        phone: Número de teléfono del usuario
    
    Returns:
        Mensaje de confirmación o error
    """
    from datetime import datetime, timezone
    from uuid import UUID
    from app.services.appointment_service import appointment_service, format_appointment_confirmation
    
    try:
        if not appointment_id:
            return "Necesito el ID de la cita que quieres reprogramar."
        
        if not new_date_str:
            return "Necesito saber la nueva fecha."
        
        try:
            apt_uuid = UUID(appointment_id)
        except ValueError:
            return f"El ID de cita '{appointment_id}' no es válido."
        
        date_obj = datetime.strptime(new_date_str, "%Y-%m-%d").date()
        
        if new_time_str:
            time_obj = datetime.strptime(new_time_str, "%H:%M").time()
            new_start = datetime.combine(date_obj, time_obj, tzinfo=timezone.utc)
        else:
            new_start = datetime.combine(date_obj, datetime.min.time(), tzinfo=timezone.utc)
        
        appointment = await appointment_service.reschedule_appointment(apt_uuid, new_start)
        
        return f"✅ *¡Cita Reprogramada!*\n\n📆 Nueva fecha: {appointment.start_time.strftime('%d/%m/%Y')}\n⏰ Nueva hora: {appointment.start_time.strftime('%H:%M')}\n\n¿Necesitas algo más?"
        
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Error al reprogramar cita: {e}")
        return "Tuve un problema al reprogramar la cita. ¿Podrías intentar de nuevo?"


async def cancel_appointment_tool(
    appointment_id: str,
    reason: str = None,
    phone: str = None
) -> str:
    """
    Cancela una cita existente.
    
    Args:
        appointment_id: ID de la cita a cancelar
        reason: Razón de cancelación (opcional)
        phone: Número de teléfono del usuario
    
    Returns:
        Mensaje de confirmación
    """
    from uuid import UUID
    from app.services.appointment_service import appointment_service
    
    try:
        if not appointment_id:
            return "Necesito el ID de la cita que quieres cancelar."
        
        try:
            apt_uuid = UUID(appointment_id)
        except ValueError:
            return f"El ID de cita '{appointment_id}' no es válido."
        
        await appointment_service.cancel_appointment(apt_uuid, reason)
        
        return "✅ *¡Cita Cancelada!*\n\nTu cita ha sido cancelada correctamente. ¿Te gustaría agendar una nueva visita o buscar otras propiedades?"
        
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Error al cancelar cita: {e}")
        return "Tuve un problema al cancelar la cita. ¿Podrías intentar de nuevo?"


async def get_my_appointments(phone: str = None) -> str:
    """
    Obtiene las citas programadas del usuario.
    
    Args:
        phone: Número de teléfono del usuario
    
    Returns:
        Lista de citas formateada
    """
    from uuid import UUID
    from app.services.appointment_service import appointment_service, format_appointment_list
    from app.db.repository import UserRepository
    from app.db.models import User
    from app.db.session import async_session_factory

    try:
        if not phone:
            return "No tengo tu información de contacto."
        
        async with async_session_factory() as session:
            user_repo = UserRepository(User, session)
            user = await user_repo.get_by_phone(phone)
            
            if not user:
                return "No tienes citas programadas."
            
            appointments = await appointment_service.get_user_appointments(user.id, upcoming=True)
            
            return format_appointment_list(appointments)
            
    except Exception as e:
        logger.error(f"Error al obtener citas: {e}")
        return "Tuve un problema al obtener tus citas."


async def request_human_assistance(phone: str = None, reason: str = "user_requested") -> str:
    """
    Transfiere la conversación a un agente humano.
    
    Args:
        phone: Número de teléfono del usuario
        reason: Razón por la cual el usuario pide hablar con un humano
    
    Returns:
        Confirmación del handoff
    """
    from app.services.handoff_service import handoff_service
    
    try:
        if not phone:
            return "No tengo tu información de contacto para transferirte."
        
        result = await handoff_service.trigger_handoff(phone=phone, reason=reason)
        
        if result.get("success"):
            return result.get("message", "Un agente humano te contactará pronto. Gracias por tu paciencia.")
        else:
            return "Tuve un problema al transferirte. Un agente te contactará lo antes posible."
            
    except Exception as e:
        logger.error(f"Error en request_human_assistance: {e}")
        return "Un agente humano te contactará pronto. Gracias por tu paciencia."


async def get_property_images(property_id: str) -> str:
    """Muestra imágenes de una propiedad por su ID (o referencia). Devuelve JSON string con images."""
    import json
    
    try:
        # Try integer ID first
        try:
            int_id = int(property_id)
            if 1 <= int_id <= 1000:
                from app.db.repository import BaseRepository
                from app.db.models import Property
                from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
                from sqlalchemy.orm import sessionmaker
                from app.core.config import get_settings
                settings = get_settings()
                engine = create_async_engine(settings.DATABASE_URL, echo=False)
                async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                async with async_session_factory() as session:
                    repo = BaseRepository(Property, session)
                    prop = await repo.get(int_id)
                    if prop and getattr(prop, "images", None):
                        return json.dumps({"images": prop.images})
                await engine.dispose()
        except Exception:
            pass
        # Try UUID via service
        try:
            from uuid import UUID
            # Normalize input to string; if it's a UUID object, convert to string
            if isinstance(property_id, UUID):
                id_str = str(property_id)
            else:
                id_str = str(property_id)
            prop_uuid = UUID(id_str) if id_str is not None else None
            from app.services.property_service import property_service
            if prop_uuid:
                images = await property_service.get_property_images(id_str)  # type: ignore
            else:
                images = []
            if images:
                return json.dumps({"images": images})
        except Exception:
            pass
        return json.dumps({"images": []})
    except Exception as e:
        logger.error(f"Error en get_property_images: {e}")
        return json.dumps({"images": []})


TOOL_FUNCTIONS = {
    "search_properties": search_properties,
    "get_property_details": get_property_details,
    "recommend_properties": recommend_properties,
    "update_user_preferences": update_user_preferences,
    "get_user_preferences": get_user_preferences,
    "save_lead_info": save_lead_info,
    "schedule_visit": schedule_visit,
    "reschedule_appointment": reschedule_appointment_tool,
    "cancel_appointment": cancel_appointment_tool,
    "get_my_appointments": get_my_appointments,
    "request_human_assistance": request_human_assistance,
    "refine_search": refine_search,
    "get_property_images": get_property_images,
}


def format_property_details(prop) -> str:
    """
    Formatea los detalles de una propiedad específica.
    """
    if not prop:
        return "No encontré esa propiedad. ¿Quieres buscar otras opciones?"
    
    return format_property(prop)


async def execute_tool(tool_name: str, arguments: dict, phone: str = None) -> str:
    """
    Ejecuta una herramienta por nombre con sus argumentos.
    
    Args:
        tool_name: Nombre de la herramienta
        arguments: Argumentos de la herramienta
        phone: Número de teléfono del usuario (para algunas herramientas)
    
    Returns:
        Resultado de la ejecución como string
    """
    if tool_name not in TOOL_FUNCTIONS:
        return f"Herramienta '{tool_name}' no encontrada."
    
    func = TOOL_FUNCTIONS[tool_name]
    
    try:
        if phone and tool_name in ["update_user_preferences", "get_user_preferences", "save_lead_info"]:
            arguments["phone"] = phone
        
        if tool_name == "search_properties":
            result = await func(arguments)
        elif tool_name == "recommend_properties":
            result = await func(arguments)
        elif tool_name == "get_property_details":
            result = await func(**arguments)
        elif tool_name in ["schedule_visit", "reschedule_appointment", "cancel_appointment", "get_my_appointments", "request_human_assistance"]:
            result = await func(phone=phone, **arguments)
        else:
            result = await func(**arguments)
        
        return result
    except TypeError as e:
        logger.error(f"Error de tipos en {tool_name}: {e}")
        return f"Error al ejecutar {tool_name}: argumentos inválidos."
    except Exception as e:
        logger.error(f"Error ejecutando {tool_name}: {e}")
        return f"Error al ejecutar {tool_name}: {str(e)}"


__all__ = [
    "search_properties",
    "get_property_details", 
    "recommend_properties",
    "update_user_preferences",
    "get_user_preferences",
    "save_lead_info",
    "schedule_visit",
    "reschedule_appointment_tool",
    "cancel_appointment_tool",
    "get_my_appointments",
    "request_human_assistance",
    "format_property_list",
    "format_property",
    "execute_tool",
    "TOOL_FUNCTIONS",
]

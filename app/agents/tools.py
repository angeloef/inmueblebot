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
from app.utils.sanitizer import sanitize_criteria, sanitize_property_id, sanitize_text, sanitize_date_input, sanitize_time_input


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
    cur = _get_attr(prop, "currency", "USD")
    bedrooms = _get_attr(prop, "bedrooms")
    bathrooms = _get_attr(prop, "bathrooms")
    area_m2 = _get_attr(prop, "area_m2")
    description = _get_attr(prop, "description")

    # Defensive: force price to int to prevent scientific notation ($1.2E+5)
    try:
        price = int(float(str(price)))
    except (ValueError, TypeError):
        price = 0

    if cur != "USD":
        currency_label = cur
    else:
        currency_label = ""
    
    if prop_type == "alquiler":
        price_str = f"${price:,}/mes" if not currency_label else f"{currency_label} ${price:,}/mes"
    else:
        price_str = f"${price:,}" if not currency_label else f"{currency_label} ${price:,}"

    title = title[:60] + "..." if len(title) > 60 else title

    if currency_label:
        location_display = f"{location} | {currency_label}"
    else:
        location_display = location

    features = []
    if bedrooms:
        features.append(f"{bedrooms} hab")
    if bathrooms:
        features.append(f"{bathrooms} baños")
    if area_m2:
        features.append(f"{area_m2}m²")
    features_str = " | ".join(features) if features else "Sin especificar"

    lines = [
        f"🏠 {title}",
        f"💰 {price_str} | {location_display}",
        f"📐 {features_str}",
    ]

    if description:
        lines.append(f"📝 {description[:300]}")

    lines.append("")
    lines.append(f"ID: {prop_id}")

    return "\n".join(lines)


def format_property_list(properties: List) -> str:
    """
    Formatea una lista de propiedades en texto legible para WhatsApp.
    Formato minimalista, una línea por propiedad.
    
    Args:
        properties: Lista de objetos Property o dicts
    
    Returns:
        String formateado con los detalles de cada propiedad
    """
    if not properties:
        return "No encontré propiedades que coincidan con tu búsqueda."
    
    lines = []
    lines.append(f"Encontré {len(properties)} propiedades:\n")

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
        # Defensive: force price to int to prevent scientific notation ($1.2E+5)
        try:
            price = int(float(str(price)))
        except (ValueError, TypeError):
            price = 0
        
        cur = _get_attr(prop, "currency", "USD")
        prop_type = _get_attr(prop, "type", "venta")
        if cur != "USD":
            currency_prefix = f"{cur} "
        else:
            currency_prefix = ""
        if prop_type == "alquiler":
            price_str = f"{currency_prefix}${price:,}/mes"
        else:
            price_str = f"{currency_prefix}${price:,}"

        bedrooms = _get_attr(prop, "bedrooms")
        bathrooms = _get_attr(prop, "bathrooms")
        area_m2 = _get_attr(prop, "area_m2")

        features = []
        if bedrooms:
            features.append(f"{bedrooms} hab")
        if bathrooms:
            features.append(f"{bathrooms} baños")
        if area_m2:
            features.append(f"{area_m2}m²")
        features_str = " | ".join(features) if features else "Sin info"

        location = _get_attr(prop, "location", "Sin ubicación")

        # Minimalist one-line format: 🏠 Title | $Price | N hab | Location | ID:N
        bedroom_str = ""
        if bedrooms:
            bedroom_str = f" {bedrooms} hab |"
        else:
            bedroom_str = " |"
        line = f"🏠 {title} | {price_str}{bedroom_str} {location} | ID:{prop_id}"

        lines.append(line)
    
    return "\n".join(lines)


def _get_attr(obj, attr: str, default=None):
    """Helper para obtener atributo de dict u objeto."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


async def search_properties(criteria: Dict[str, Any], phone: str = None) -> str:
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
            - operation_type: Tipo de operacion (venta o alquiler) - DEFAULT alquiler
            - limit: Numero de resultados (default 8)
            - sort_by: Ordenamiento (price_desc, price_asc, newest) - DEFAULT price_desc

    Returns:
        String formateado con las propiedades encontradas o mensaje de sin resultados
    """
    logger.info("=" * 60)
    logger.info("[TOOL] search_properties LLAMADO")
    logger.info(f"[TOOL] Criterios crudos recibidos: {criteria}")
    logger.info("=" * 60)
    
    try:
        # SANITIZAR criterios de búsqueda
        criteria = sanitize_criteria(criteria)
        
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
        else:
            # Default to "alquiler" (rental) when user doesn't specify
            # Most users contact the bot looking to rent, not buy
            search_criteria["operation_type"] = "alquiler"
            logger.info("[TOOL] No operation_type specified — defaulting to 'alquiler'")
        
        # Pass sort_by if provided (price_desc, price_asc, newest)
        if criteria.get("sort_by"):
            search_criteria["sort_by"] = criteria["sort_by"]
            logger.info(f"[TOOL] Sort by: '{search_criteria['sort_by']}'")
        
        # Handle price_tier for vague budget terms (economico, normal, premium)
        price_tier = criteria.get("price_tier")
        if price_tier:
            try:
                from app.agents.budget_tiers import get_budget_tiers
                tiers = await get_budget_tiers()
                logger.info(f"[TOOL] price_tier='{price_tier}' -> tiers: low_max={tiers['low_max']}, med_max={tiers['med_max']}")
                if price_tier == "economico":
                    search_criteria["budget_max"] = tiers["low_max"]
                    search_criteria["sort_by"] = "price_desc"
                elif price_tier == "normal":
                    search_criteria["budget_min"] = tiers["low_max"] + 1
                    search_criteria["budget_max"] = tiers["med_max"]
                elif price_tier == "premium":
                    search_criteria["budget_min"] = tiers["med_max"] + 1
            except Exception as e:
                logger.warning(f"[TOOL] Could not resolve price_tier '{price_tier}': {e}")
        
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
        
        # Save compressed property objects to Redis (id+title only) — saves ~160 bytes/property in context
        if phone and properties:
            try:
                prop_list = []
                for prop in properties:
                    original_id = _get_attr(prop, "original_id", None)
                    prop_list.append({
                        "id": str(original_id) if original_id else str(_get_attr(prop, "id", "")),
                        "title": _get_attr(prop, "title", ""),
                    })
                await memory_manager.update_context_field(phone, "last_shown_properties", prop_list)
                logger.info(f"[TOOL] Saved {len(prop_list)} properties to last_shown_properties (compressed)")
            except Exception as e:
                logger.warning(f"[TOOL] Could not save last_shown_properties: {e}")

        # If no results, try fallback searches with relaxed criteria
        if not properties:
            logger.info("[TOOL] No results found — trying fallback searches")
            
            # Fallback 1: +30% budget_max, keep same criteria
            fb1_criteria = dict(search_criteria)
            if fb1_criteria.get("budget_max"):
                fb1_criteria["budget_max"] = int(fb1_criteria["budget_max"] * 1.3)
            logger.info(f"[TOOL] Fallback 1: +30% budget -> {fb1_criteria.get('budget_max')}")
            fb1_results = await property_service.search_properties(fb1_criteria)
            
            # Fallback 2: same operation_type + property_type, remove location + budget
            fb2_criteria = {"operation_type": search_criteria.get("operation_type", "alquiler")}
            if search_criteria.get("property_type"):
                fb2_criteria["property_type"] = search_criteria["property_type"]
            logger.info(f"[TOOL] Fallback 2: no location/budget, type={fb2_criteria.get('property_type')}")
            fb2_results = await property_service.search_properties(fb2_criteria)
            
            # Fallback 3: only operation_type
            fb3_criteria = {"operation_type": search_criteria.get("operation_type", "alquiler")}
            logger.info(f"[TOOL] Fallback 3: only operation_type='{fb3_criteria['operation_type']}'")
            fb3_results = await property_service.search_properties(fb3_criteria)
            
            # Build response
            parts = [f"No encontr\u00e9 {search_criteria.get('property_type', 'propiedades')} en {search_criteria.get('location', 'esa zona')} con esos filtros exactos. Pero tengo alternativas:\n"]
            
            if fb1_results:
                budget_str = f" (hasta ${fb1_criteria.get('budget_max', 0):,})" if fb1_criteria.get("budget_max") else ""
                parts.append(f"\ud83d\udd31 Subiendo un poco el presupuesto{budget_str}:")
                parts.append(format_property_list(fb1_results))
                parts.append("")
            
            if fb2_results:
                parts.append(f"\ud83d\udd31 {fb2_criteria.get('property_type', 'Propiedades').capitalize()} en cualquier zona:")
                parts.append(format_property_list(fb2_results))
                parts.append("")
            
            if fb3_results:
                op_type = fb3_criteria.get("operation_type", "alquiler")
                parts.append(f"\ud83d\udd31 Todas las opciones en {op_type}:")
                parts.append(format_property_list(fb3_results))
            
            return "\n".join(parts)
        
        return format_property_list(properties)
        
    except Exception as e:
        logger.error(f"Error en busqueda de propiedades: {e}")
        return "Tuve un problema al buscar propiedades. Podrias intentar con otros criterios?"


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
        # SANITIZAR property_id
        property_id = sanitize_property_id(property_id)
        
        # Validate format — catch clearly hallucinated IDs early
        is_numeric = property_id.isdigit()
        is_uuid_like = len(property_id) == 36 and property_id.count('-') == 4
        if not is_numeric and not is_uuid_like:
            logger.warning(f"[get_property_details] ⚠️ Posible ID alucinado: '{property_id}'")
            return (f"El ID '{property_id}' no es válido. "
                    f"Usá el ID numérico exacto que aparece en <last_results>. "
                    f"NUNCA inventes IDs.")

        prop = None
        
        # Try integer ID first - use the integer 'id' field directly
        try:
            int_id = int(property_id)
            if 1 <= int_id <= 100:
                logger.info(f"[get_property_details] Buscando por integer ID: {int_id}")
                # Use the service with direct ID lookup
                from app.db.repository import BaseRepository
                from app.db.models import Property
                from app.db.session import async_session_factory
                
                async with async_session_factory() as session:
                    repo = BaseRepository(Property, session)
                    prop = await repo.get(int_id)  # Direct integer ID lookup
                
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
            budget_val = prefs['budget_max']
            try:
                budget_val = int(float(str(budget_val)))
            except (ValueError, TypeError):
                pass
            parts.append(f"💰 Presupuesto: hasta ${budget_val:,}")
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
    Agenda una visita a una propiedad.
    
    GUÍA PARA EL LLM:
    - Intenta enviar la fecha en formato DD/MM/YYYY cuando sea posible (ej: "29/04/2026")
    - También soporta expresiones naturales: "mañana a las 15hs", "el viernes a las 10 de la mañana"
    - Si date_str o time_str viene vacío pero hay contexto previo, úsalo
    - Si no puedes determinar la fecha/hora, PREGUNTA al usuário antes de llamar
    
    Esta función pode receber:
    - property_id: ID de la propiedad (número o UUID)
    - date_str: "29/04/2026", "mañana", "el viernes", etc
    - time_str: "15:00", "a las 15hs", "10am", etc (opcional)
    - phone: Número de teléfono del usuário
    
    Returns:
        Mensaje de confirmación ou mensaje de erro/ambigüedad
        
    NOTA: Esta función verifica disponibilidad en Google Calendar antes de agendar.
    """
    logger.info("=" * 60)
    logger.info(f"[schedule_visit] SOLICITADO")
    logger.info(f"[schedule_visit] Input: property_id={property_id}, date_str={date_str}, time_str={time_str}")
    logger.info("=" * 60)
    
    try:
        # SANITIZAR property_id y inputs de fecha/hora
        property_id = sanitize_property_id(property_id)
        if date_str:
            date_str = sanitize_date_input(date_str)
        if time_str:
            time_str = sanitize_time_input(time_str)
        
        if not property_id:
            return "Necesito saber qué propiedad quieres visitar."
        
        # Validate property_id format — catch clearly hallucinated IDs early
        # Valid formats: integer strings ("6"), UUIDs, or numeric references
        is_numeric = property_id.isdigit()
        is_uuid_like = len(property_id) == 36 and property_id.count('-') == 4
        if not is_numeric and not is_uuid_like:
            logger.warning(f"[schedule_visit] ⚠️ Posible ID alucinado por el LLM: '{property_id}' — no es numérico ni UUID")
            # Return a clear message telling the LLM to use IDs from context
            return (f"El ID '{property_id}' no es válido. "
                    f"Usá el ID numérico exacto que aparece en <last_results> como ID=6 o ID=1. "
                    f"NUNCA inventes IDs. Revisá el contexto de la conversación para encontrar el ID correcto.")
        
        if not date_str:
            return "¿Para qué fecha te conviene la visita? Dime algo como 'mañana a las 15', 'el viernes a las 10', o 'el 28 de abril'."
        
        # Resolve property_id BEFORE parsing datetime
        prop_uuid = None
        prop_int_id = None
        try:
            int_id = int(property_id)
            if 1 <= int_id <= 1000:
                prop = await property_service.get_property_details(str(int_id))
                if prop:
                    prop_uuid = prop.id
                    prop_int_id = prop.id
                    property_obj = prop
        except (ValueError, TypeError):
            pass
        
        if not prop_uuid:
            try:
                prop_uuid = UUID(property_id)
            except ValueError:
                return f"El ID de propiedad '{property_id}' no es válido."
            prop = await property_service.get_property_details(str(prop_uuid))
            if not prop:
                return f"No encontré la propiedad con ID '{property_id}'."
            prop_int_id = prop.id
            property_obj = prop
        
        # Combine date_str and time_str for parsing
        combined_input = f"{date_str} {time_str or ''}".strip()
        
        # Use robust Argentine timezone parser
        from app.utils.date_parser import parse_spanish_datetime, format_datetime_argentina, validate_future
        from app.services.appointment_service import appointment_service, format_appointment_confirmation
        from app.db.repository import UserRepository
        from app.db.models import User
        from app.db.session import async_session_factory
        logger.info(f"[schedule_visit] Input: date_str='{date_str}', time_str='{time_str}', combined='{combined_input}'")
        
        parsed_dt, parse_error = parse_spanish_datetime(combined_input)
        
        # Log what the LLM sent vs what was parsed for debugging
        logger.info(f"[schedule_visit] LLM sent: date_str='{date_str}', time_str='{time_str}', combined='{combined_input}'")
        logger.info(f"[schedule_visit] Parser returned: parsed_dt={parsed_dt}, parse_error={parse_error}")
        if parsed_dt:
            logger.info(f"[schedule_visit] PARSED: {format_datetime_argentina(parsed_dt)}")
        
        if parse_error:
            # If parsing failed, ask user for clarification
            logger.warning(f"[schedule_visit] Parse error: {parse_error}")
            return parse_error
        
        # Validate it's in the future
        is_valid, validation_error = validate_future(parsed_dt, min_minutes=30)
        if not is_valid:
            logger.warning(f"[schedule_visit] Validation error: {validation_error}")
            # Check if the user's original input was a natural language date
            # that got incorrectly converted by the LLM to a numeric date
            import re as _re_date
            is_numeric_date = bool(_re_date.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_str or ''))
            if is_numeric_date:
                return (f"La fecha '{date_str} {time_str or ''}' ya pasó. "
                        f"REINTENTÁ pasando la fecha TAL CUAL la dijo el usuario, sin convertirla a números. "
                        f"Por ejemplo, si el usuario dijo 'dentro de 4 días', usá date_str='dentro de 4 días'.")
            return validation_error
        
        start_datetime = parsed_dt
        logger.info(f"[schedule_visit] Parsed datetime: {format_datetime_argentina(start_datetime)}")
        
        logger.info(f"[schedule_visit] Parsed date: {date_str} + {time_str} -> {start_datetime.strftime('%Y-%m-%d %H:%M')}")
        
        # Get user in separate session
        user = None
        async with async_session_factory() as session:
            try:
                user_repo = UserRepository(User, session)
                user = await user_repo.get_by_phone(phone)
                if not user:
                    return "No te encontré en el sistema. ¿Podrías darme tu nombre?"
                logger.info(f"[schedule_visit] User found: {user.id}")
            except Exception as e:
                logger.error(f"[schedule_visit] Error getting user: {e}")
                return f"Tuve un problema al buscarte en el sistema. ¿Podrías intentar de nuevo?"
        
        # Create appointment in separate session
        if user:
            try:
                logger.info(f"[schedule_visit] Calling create_appointment with check_calendar=True")
                result = await appointment_service.create_appointment(
                    user_id=user.id,
                    property_id=prop_int_id,
                    start_time=start_datetime,
                    type="visit"
                )
            except Exception as e:
                logger.error(f"[schedule_visit] Error creating appointment: {e}")
                return "Tuve un problema técnico al agendar. ¿Podrías intentar en unos minutos?"
            
            
            logger.info(f"[schedule_visit] result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")
            logger.info(f"[schedule_visit] result.get('success'): {result.get('success') if isinstance(result, dict) else 'N/A'}")
            
            if not isinstance(result, dict) or not result.get("success"):
                # Either error dict or unexpected type - handle gracefully
                if isinstance(result, dict):
                    msg = result.get("message", "Horario no disponible")
                    suggestions = result.get("suggested_times", [])
                    if suggestions:
                        lines = [f"- {s.get('formatted') or s.get('datetime', '')}" for s in suggestions[:3]]
                        return f"⚠️ {msg}\n\n🎯 Horarios disponibles:\n" + "\n".join(lines) + "\n\n¿Alguna?"
                    return f"⚠️ {msg}\n\n¿Qué otro horario te conviene?"
                return f"⚠️ No se pudo completar la agenda.\n\n¿Qué otro horario te conviene?"
            
            # Success - format confirmation
            appointment = result.get("appointment")
            if appointment:
                property_title = getattr(property_obj, "title", "Propiedad") if hasattr(property_obj, "title") else "Propiedad"
                return format_appointment_confirmation(appointment, property_title)
            
            return "Tuve un problema al procesar tu solicitud. ¿Podrías intentar de nuevo?"
            
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
    from datetime import datetime
    from uuid import UUID
    from app.services.appointment_service import appointment_service, format_appointment_confirmation
    from app.db.session import async_session_factory
    from app.db.models import Appointment as AppointmentModel
    from sqlalchemy import select
    import pytz
    from app.utils.date_parser import parse_spanish_datetime, get_argentina_now

    try:
        apt_uuid = None
        
        # Try to parse the appointment_id as UUID
        if appointment_id:
            try:
                apt_uuid = UUID(appointment_id)
            except ValueError:
                logger.warning(f"[reschedule] ⚠️ LLM pasó ID inválido '{appointment_id}' — buscando cita más reciente del usuario")
                apt_uuid = None
        
        # If no valid UUID, try to find the user's most recent appointment automatically
        if not apt_uuid and phone:
            try:
                from app.db.models import User
                async with async_session_factory() as db:
                    user_repo_q = select(User).where(User.whatsapp_phone == phone)
                    user_result = await db.execute(user_repo_q)
                    user = user_result.scalar_one_or_none()
                    if user:
                        apt_q = (
                            select(AppointmentModel)
                            .where(AppointmentModel.user_id == user.id)
                            .where(AppointmentModel.status.in_(["scheduled", "confirmed"]))
                            .order_by(AppointmentModel.created_at.desc())
                            .limit(1)
                        )
                        apt_result = await db.execute(apt_q)
                        latest_apt = apt_result.scalar_one_or_none()
                        if latest_apt:
                            apt_uuid = latest_apt.id
                            logger.info(f"[reschedule] Auto-resolved appointment: {apt_uuid}")
            except Exception as e:
                logger.warning(f"[reschedule] Could not auto-resolve appointment: {e}")
        
        if not apt_uuid:
            return "Necesito el ID de la cita que quieres reprogramar."
        
        # Fetch current appointment data to use as reference
        current_apt = None
        async with async_session_factory() as db:
            try:
                current_apt = await db.get(AppointmentModel, apt_uuid)
            except Exception:
                pass
        
        # If no new_date_str provided, use existing appointment's date
        if not new_date_str and current_apt:
            arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
            existing_local = current_apt.start_time.astimezone(arg_tz)
            new_date_str = existing_local.strftime("%Y-%m-%d")
            logger.info(f"[reschedule] No new date provided, using existing: {new_date_str}")
        
        if not new_date_str:
            return "Necesito saber la nueva fecha."
        
        # Parse date with multiple format fallbacks:
        # 1. Try YYYY-MM-DD (current behavior)
        # 2. Try DD/MM/YYYY
        # 3. Try natural language via parse_spanish_datetime (mañana, hoy, próximo martes, etc.)
        date_obj = None
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"]:
            try:
                date_obj = datetime.strptime(new_date_str.strip(), fmt).date()
                logger.info(f"[reschedule] Parsed date '{new_date_str}' with format {fmt} -> {date_obj}")
                break
            except ValueError:
                continue

        if date_obj is None:
            # Try natural language parsing (handles "mañana", "hoy", "próximo martes", etc.)
            try:
                parsed_dt, error_msg = parse_spanish_datetime(new_date_str)
                if parsed_dt:
                    date_obj = parsed_dt.date()
                    logger.info(f"[reschedule] Natural language parsed '{new_date_str}' -> {date_obj}")
                else:
                    return (
                        f"No pude entender la fecha '{new_date_str}'. "
                        f"Por favor usá formato como '12/05/2026' o 'próximo martes'."
                    )
            except Exception:
                return (
                    f"No pude entender la fecha '{new_date_str}'. "
                    f"Por favor usá formato como '12/05/2026' o 'próximo martes'."
                )
        
        # If no new_time_str, use existing appointment's time
        if not new_time_str and current_apt:
            arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
            existing_local = current_apt.start_time.astimezone(arg_tz)
            new_time_str = existing_local.strftime("%H:%M")
            logger.info(f"[reschedule] No new time provided, using existing: {new_time_str}")
        
        arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
        if new_time_str:
            time_obj = datetime.strptime(new_time_str, "%H:%M").time()
            # Contextual hour interpretation: if existing apt is PM and user says "7", prefer 19:00 over 07:00
            if current_apt and time_obj.hour < 12:
                arg_tz_inner = pytz.timezone('America/Argentina/Buenos_Aires')
                existing_local = current_apt.start_time.astimezone(arg_tz_inner)
                if existing_local.hour >= 12:
                    # Existing apt is PM — interpret user's hour as PM too
                    time_obj = time_obj.replace(hour=time_obj.hour + 12)
                    logger.info(f"[reschedule] Contextual PM interpretation: existing={existing_local.hour}:00, new={time_obj.hour}:00")
            new_start = arg_tz.localize(datetime.combine(date_obj, time_obj))
        else:
            new_start = arg_tz.localize(datetime.combine(date_obj, datetime.min.time()))
        
        appointment = await appointment_service.reschedule_appointment(apt_uuid, new_start)
        
        return format_appointment_confirmation(appointment, action_type='reschedule')
        
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


def _to_public_image_urls(raw_images: list, property_id: str) -> list:
    """
    Convierte data:URI a URLs públicas del endpoint /media/property/{id}/{index}.
    WhatsApp no acepta data URIs — necesita URLs HTTPS públicas.
    """
    from app.core.config import get_settings
    base = get_settings().API_BASE_URL.rstrip("/")
    public = []
    for i, img in enumerate(raw_images):
        if isinstance(img, str) and (img.startswith("data:") or not img.startswith("http")):
            # Data URI or raw base64 — serve via media endpoint
            public.append(f"{base}/media/property/{property_id}/{i}")
        elif isinstance(img, str) and ("localhost" in img or "127.0.0.1" in img):
            # Route ALL localhost/internal URLs through the media endpoint
            # (the media endpoint handles decoding / placeholding seamlessly)
            path = f"/media/property/{property_id}/{i}"
            public.append(f"{base}{path}")
        else:
            public.append(img)
    return public


async def get_property_images(property_id: str) -> str:
    """Muestra imágenes de una propiedad por su ID (o referencia). Devuelve JSON string con images."""
    import json

    try:
        # Validate format — catch clearly hallucinated IDs early
        is_numeric = property_id.isdigit()
        is_uuid_like = len(property_id) == 36 and property_id.count('-') == 4
        if not is_numeric and not is_uuid_like:
            logger.warning(f"[get_property_images] ⚠️ Posible ID alucinado: '{property_id}'")
            return json.dumps({"images": [], "error": f"ID '{property_id}' no válido — usá un ID numérico del contexto"})

        # Try integer ID first
        try:
            int_id = int(property_id)
            if 1 <= int_id <= 1000:
                from app.db.repository import BaseRepository
                from app.db.models import Property
                from app.db.session import async_session_factory as _sf
                async with _sf() as session:
                    repo = BaseRepository(Property, session)
                    prop = await repo.get(int_id)
                    if prop and getattr(prop, "images", None):
                        images = _to_public_image_urls(prop.images, str(int_id))
                        return json.dumps({"images": images})
        except Exception:
            pass
        # Try UUID via service
        try:
            from uuid import UUID
            id_str = str(property_id) if not isinstance(property_id, UUID) else str(property_id)
            prop_uuid = UUID(id_str)
            from app.services.property_service import property_service
            images = await property_service.get_property_images(id_str)  # type: ignore
            if images:
                images = _to_public_image_urls(images, id_str)
                return json.dumps({"images": images})
        except Exception:
            pass
        # Fallback: return empty — placeholder URLs don't work (WhatsApp can't fetch /static/)
        return json.dumps({"images": [], "message": "No se encontraron imágenes para esta propiedad."})
    except Exception as e:
        logger.error(f"Error en get_property_images: {e}")
        return json.dumps({"images": []})


async def get_faq_answer(question: str = None, phone: str = None) -> str:
    """
    Responde preguntas frecuentes (FAQ) sobre la inmobiliaria.
    
    Args:
        question: Pregunta del usuario (ej: "¿A qué hora abren?", "¿Aceptan tarjetas?")
        phone: Número de teléfono del usuario
    
    Returns:
        Respuesta de FAQ o mensaje de "no encontrado"
    """
    from app.services.faq_service import faq_service

    if not question or not question.strip():
        return "¿Qué querés saber? Preguntame sobre horarios, formas de pago, financiación, o cualquier otra duda."

    query = question.strip()
    logger.info(f"[FAQ] get_faq_answer called with question: '{query}'")

    try:
        matches = await faq_service.search_faqs(query=query)

        if not matches:
            logger.info(f"[FAQ] No FAQ matches for: '{query}'")
            return "NO_FAQ_MATCH"

        # Format the best matches for the LLM to use
        lines = [f"Encontré {len(matches)} respuestas relacionadas:\n"]
        for i, faq in enumerate(matches, 1):
            lines.append(f"--- FAQ #{i} ---")
            lines.append(f"P: {faq.question}")
            lines.append(f"R: {faq.answer}")
            if faq.category:
                lines.append(f"Categoría: {faq.category}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as e:
        logger.error(f"[FAQ] Error in get_faq_answer: {e}")
        return "NO_FAQ_MATCH"


async def compare_properties(property_ids: list) -> str:
    """
    Compara 2-3 propiedades en una tabla para que el usuario decida.
    
    Args:
        property_ids: Lista de IDs de propiedades a comparar (2-3 máximo)
    
    Returns:
        String con tabla comparativa formateada
    """
    if not property_ids:
        return "No especificaste ninguna propiedad para comparar."
    
    if len(property_ids) > 3:
        property_ids = property_ids[:3]
    
    from app.db.repository import BaseRepository
    from app.db.models import Property
    from app.db.session import async_session_factory
    
    props = []
    for pid in property_ids:
        try:
            int_id = int(pid)
            async with async_session_factory() as session:
                repo = BaseRepository(Property, session)
                prop = await repo.get(int_id)
                if prop:
                    props.append(prop)
        except (ValueError, Exception) as e:
            logger.warning(f"[compare_properties] Error fetching property {pid}: {e}")
    
    if not props:
        return "No encontré las propiedades especificadas para comparar."
    
    # Build comparison table
    def safe(val, default="—"):
        return val if val is not None else default
    
    def price_fmt(prop) -> str:
        price = getattr(prop, "price", 0)
        try:
            price = int(float(str(price)))
        except (ValueError, TypeError):
            price = 0
        op_type = getattr(prop, "type", "venta") or "venta"
        cur = getattr(prop, "currency", "USD")
        prefix = "" if cur == "USD" else f"{cur} "
        if op_type == "alquiler":
            return f"{prefix}${price:,}/mes"
        return f"{prefix}${price:,}"
    
    # Headers
    headers = ["Característica"] + [getattr(p, "title", f"Propiedad {i+1}")[:20] for i, p in enumerate(props)]
    
    # Build rows
    rows = [
        ("💰 Precio", [price_fmt(p) for p in props]),
        ("📐 Tamaño", [f"{safe(getattr(p, 'area_m2', None))}m²" if getattr(p, 'area_m2', None) else "—" for p in props]),
        ("🛏️ Dormitorios", [f"{safe(getattr(p, 'bedrooms', None))} hab" if getattr(p, 'bedrooms', None) else "—" for p in props]),
        ("🚿 Baños", [f"{safe(getattr(p, 'bathrooms', None))}" if getattr(p, 'bathrooms', None) else "—" for p in props]),
        ("🚗 Cochera", ["Sí" if getattr(p, 'parking', False) else "No" for p in props]),
        ("📌 Zona", [safe(getattr(p, 'location', None), "—") for p in props]),
        ("📋 Tipo", [safe(getattr(p, 'property_type', None), "—") for p in props]),
    ]
    
    # Format table
    col_widths = [len(h) for h in headers]
    for row_name, vals in rows:
        col_widths[0] = max(col_widths[0], len(row_name))
        for i, v in enumerate(vals):
            col_widths[i + 1] = max(col_widths[i + 1], len(v))
    
    # Clamp widths
    col_widths = [min(w, 30) for w in col_widths]
    
    def pad(text, width):
        text = str(text)
        if len(text) > width:
            return text[:width-1] + "…"
        return text.ljust(width)
    
    table_lines = ["Aquí tenés la comparación:\n"]
    # Header row
    table_lines.append("  " + " | ".join(pad(h, w) for h, w in zip(headers, col_widths)))
    # Separator
    table_lines.append("  " + "-|-".join("-" * w for w in col_widths))
    # Data rows
    for row_name, vals in rows:
        cells = [pad(row_name, col_widths[0])] + [pad(v, w) for v, w in zip(vals, col_widths[1:])]
        table_lines.append("  " + " | ".join(cells))
    
    return "\n".join(table_lines)


TOOL_FUNCTIONS = {
    "search_properties": search_properties,
    "compare_properties": compare_properties,
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
    "get_faq_answer": get_faq_answer,
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
            result = await func(arguments, phone=phone)
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
    "compare_properties",
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

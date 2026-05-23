"""
Herramientas del agente de bienes raíces.
Funciones async que pueden ser llamadas por el LLM via tool calling.
"""
import json
import re
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
    cur = _get_attr(prop, "currency", "ARS")
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
    lines.append("")
    lines.append("¿Queres que te muestre las fotos de esta propiedad? O preferirias ver los detalles de otra?")

    return "\n".join(lines)


def format_property_list(properties: List, criteria: dict = None) -> str:
    """
    Formatea una lista de propiedades en texto legible para WhatsApp.
    Usa estilo A8 (Recepcionista Experta): header dinámico con criterios de búsqueda,
    luego propiedades listadas con ubicación, precio y ambientes.

    Args:
        properties: Lista de objetos Property o dicts
        criteria: Dict opcional con search_criteria (location, property_type, bedrooms, etc.)
                  para generar un header dinámico

    Returns:
        String formateado con los detalles de cada propiedad
    """
    if not properties:
        return "No encontré propiedades que coincidan con tu búsqueda."

    lines = []

    # ── Dynamic header based on search criteria ──
    if criteria:
        # Map property_type to gendered Spanish
        pt = criteria.get("property_type", "").lower()
        if pt in ("casa",):
            noun = "casas"
            article = "las"
        elif pt in ("departamento",):
            noun = "departamentos"
            article = "los"
        elif pt in ("terreno",):
            noun = "terrenos"
            article = "los"
        elif pt in ("oficina",):
            noun = "oficinas"
            article = "las"
        elif pt in ("local",):
            noun = "locales"
            article = "los"
        elif pt in ("galpon", "galpón"):
            noun = "galpones"
            article = "los"
        else:
            noun = "propiedades"
            article = "las"

        # Bedrooms — detect actual range from properties
        bedrooms = criteria.get("bedrooms")
        if bedrooms and properties:
            # Compute actual min/max bedrooms from the results
            actual_beds = []
            for p in properties:
                b = _get_attr(p, "bedrooms", None)
                if b is not None:
                    actual_beds.append(int(b))
            actual_beds = sorted(set(actual_beds))
            if len(actual_beds) >= 2:
                # Show range: "3 y 4 dormitorios" instead of just "3"
                bed_str = f" de {' y '.join(str(b) for b in actual_beds)} dormitorio{'s' if len(actual_beds) > 1 or any(b > 1 for b in actual_beds) else ''}"
            else:
                bed_str = f" de {bedrooms} dormitorio{'s' if bedrooms > 1 else ''}" if bedrooms else ""
        else:
            bed_str = f" de {bedrooms} dormitorio{'s' if bedrooms and bedrooms > 1 else ''}" if bedrooms else ""

        # Location
        location = criteria.get("location", "")

        # Operation type
        op = criteria.get("operation_type", "alquiler")

        _single = len(properties) == 1
        if _single:
            # Singular: "Este es el terreno que tenemos disponible:"
            _art_sing = {"terrenos": "el terreno", "casas": "la casa",
                         "departamentos": "el departamento", "oficinas": "la oficina",
                         "locales": "el local", "galpones": "el galpón"}.get(noun, f"la {noun[:-1]}" if noun else "la propiedad")
            _demo_sing = "Esta" if article == "las" else "Este"
            if location:
                header = f"{_demo_sing} es {_art_sing}{bed_str} en {location}:"
            else:
                header = f"{_demo_sing} es {_art_sing}{bed_str} que tenemos disponible:"
        elif location and noun:
            demo = "Estas" if article == "las" else "Estos"
            header = f"{demo} son {article} {noun}{bed_str} en {location}:"
        elif noun:
            demo = "Estas" if article == "las" else "Estos"
            header = f"{demo} son {article} {noun}{bed_str} que tenemos disponibles:"
        else:
            header = "Estas son las propiedades que tenemos disponibles:"

        lines.append(header)
        lines.append("")
    else:
        lines.append(f"Encontré {len(properties)} propiedades:\n")

    # ── Property lines ──
    for i, prop in enumerate(properties, 1):
        # Extract structured data
        bedrooms = _get_attr(prop, "bedrooms")
        bathrooms = _get_attr(prop, "bathrooms")
        area = _get_attr(prop, "area_m2")
        prop_type = _get_attr(prop, "type", "venta")
        category = _get_attr(prop, "category", "")
        location = _get_attr(prop, "location", "Sin ubicación")
        
        # ── Type label ──
        _cat_labels = {"departamento": "Departamento", "casa": "Casa", "terreno": "Terreno"}
        cat_label = _cat_labels.get(category.lower() if category else "", "Propiedad")
        
        # ── Zone from extra_data.zone, or parse from location ──
        extra_raw = _get_attr(prop, "extra_data", None)
        if isinstance(extra_raw, dict):
            zone = extra_raw.get("zone", "")
        elif isinstance(extra_raw, str):
            try:
                extra_raw = json.loads(extra_raw)
                zone = extra_raw.get("zone", "") if isinstance(extra_raw, dict) else ""
            except (json.JSONDecodeError, TypeError):
                zone = ""
        else:
            zone = ""
        if not zone:
            loc_parts = [p.strip() for p in location.split(",")]
            zone = loc_parts[1] if len(loc_parts) >= 2 else loc_parts[0]
        
        # ── Price ──
        price = _get_attr(prop, "price", 0)
        try:
            price = int(float(str(price)))
        except (ValueError, TypeError):
            price = 0
        cur = _get_attr(prop, "currency", "ARS")
        if prop_type == "alquiler":
            price_str = f"${price:,}/mes" if cur == "USD" else f"{cur} ${price:,}/mes"
        else:
            price_str = f"${price:,}" if cur == "USD" else f"{cur} ${price:,}"
        
        # ── Build segments with | separators ──
        # Segment 1: {Tipo} en {zona} - {beds} amb
        if bedrooms:
            seg1 = f"{cat_label} en {zone} - {bedrooms} amb"
        else:
            seg1 = f"{cat_label} en {zone}"
        
        # Segment 2: price
        seg2 = price_str
        
        # Segment 3: bathrooms
        if bathrooms:
            seg3 = f"{bathrooms} baño{'s' if bathrooms > 1 else ''}"
        else:
            seg3 = ""
        
        # Segment 4: m²
        if area:
            seg4 = f"{area}m²"
        else:
            seg4 = ""
        
        # Segment 5: ID
        _oid = _get_attr(prop, "original_id", None)
        _pid = str(_oid) if _oid else str(_get_attr(prop, "id", f"prop-{i}"))[:8]
        seg5 = f"ID: {_pid}"
        
        parts = [seg1, seg2]
        if seg3:
            parts.append(seg3)
        if seg4:
            parts.append(seg4)
        parts.append(seg5)
        
        line = "📍 " + " | ".join(parts)
        lines.append(line)

    # ── Footer: helpful, personality-driven, mentions what else they can refine ──
    if criteria:
        # Detect what criteria the user could still add to narrow down
        missing = []
        if not criteria.get("budget_max") and not criteria.get("budget_min"):
            missing.append("presupuesto")
        if not criteria.get("bedrooms"):
            missing.append("cantidad de ambientes")
        if not criteria.get("bathrooms"):
            missing.append("baños")
        
        lines.append("")
        if missing:
            hint = ", ".join(missing)
            lines.append(
                f"Indicame el ID o la dirección si te interesó alguno y te paso más detalles. "
                f"También podés decirme si tenés alguna preferencia más, como {hint}, "
                f"y ajusto la búsqueda."
            )
        else:
            lines.append(
                "Indicame el ID o la dirección si te interesó alguno y te paso más detalles."
            )
    else:
        lines.append("")
        lines.append("¿Te interesa alguna?")

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
            - sort_by: Ordenamiento (price_asc, price_desc, newest) — DEFAULT price_asc

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
        
        # Normalize location using hybrid parser
        if criteria.get("location"):
            raw_loc = criteria["location"].strip()
            from app.core.hybrid.location import location_parser

            loc_result = await location_parser.parse(raw_loc, {})
            if loc_result.value:
                search_criteria["location"] = loc_result.value
                logger.info(
                    "[TOOL] Location: raw=%r -> parsed=%r (parser=%s, conf=%.2f)",
                    raw_loc,
                    loc_result.value,
                    loc_result.parser_used,
                    loc_result.confidence,
                )
            else:
                search_criteria["location"] = raw_loc
                logger.info("[TOOL] Location parser fallo, usando raw: %r", raw_loc)
        
        if criteria.get("budget_max"):
            raw_budget = int(criteria["budget_max"])
            # Expand +20%: user's budget is a TARGET, not a hard cap.
            # This surfaces options slightly above what they said while still being relevant.
            search_criteria["budget_max"] = int(raw_budget * 1.20)
            logger.info(f"[TOOL] Budget max: {raw_budget} → expanded to {search_criteria['budget_max']} (+20%)")

        if criteria.get("budget_min"):
            # Only apply explicit budget_min; never derive a floor from budget_max.
            # Cheaper options should always appear — user may take something better value.
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
        # No default: omitting operation_type returns all properties (alquiler + venta)
        
        # Pass sort_by if provided (price_desc, price_asc, newest)
        if criteria.get("sort_by"):
            search_criteria["sort_by"] = criteria["sort_by"]
            logger.info(f"[TOOL] Sort by: '{search_criteria['sort_by']}'")
        
        # Handle price_tier for vague budget terms (economico, normal, premium)
        price_tier = criteria.get("price_tier")
        if price_tier:
            try:
                from app.core.hybrid.budget import budget_parser

                ctx = {
                    "city": search_criteria.get("location", "desconocida"),
                    "median_price": 500,
                }
                budget_result = await budget_parser.parse(price_tier, ctx)
                if budget_result.value and isinstance(budget_result.value, dict):
                    bv = budget_result.value
                    if "budget_min" in bv:
                        search_criteria["budget_min"] = bv["budget_min"]
                    if "budget_max" in bv:
                        search_criteria["budget_max"] = bv["budget_max"]
                        search_criteria["sort_by"] = "price_asc"
                    logger.info(
                        "[TOOL] Budget tier %r -> %s (parser=%s, conf=%.2f)",
                        price_tier,
                        bv,
                        budget_result.parser_used,
                        budget_result.confidence,
                    )
            except Exception as e:
                logger.warning(f"[TOOL] Could not resolve price_tier '{price_tier}': {e}")
        
        # Ensure a reasonable result set: default 10 (matching TOOL_DEFINITIONS default)
        search_criteria["limit"] = max(criteria.get("limit", 10), 2)
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
            
            # Fallback 1: +30% budget_max, keep all other criteria
            fb1_criteria = dict(search_criteria)
            if fb1_criteria.get("budget_max"):
                fb1_criteria["budget_max"] = int(fb1_criteria["budget_max"] * 1.3)
            logger.info(f"[TOOL] Fallback 1: +30% budget -> {fb1_criteria.get('budget_max')}")
            fb1_results = await property_service.search_properties(fb1_criteria)
            
            # Fallback 2: same criteria, remove budget only (keep location, bedrooms, etc.)
            fb2_criteria = dict(search_criteria)
            fb2_criteria.pop("budget_max", None)
            fb2_criteria.pop("budget_min", None)
            logger.info(f"[TOOL] Fallback 2: remove budget, keep location={fb2_criteria.get('location')}")
            fb2_results = await property_service.search_properties(fb2_criteria)
            
            # Deduplicate: track property IDs across fallbacks
            seen_ids = set()
            def _dedup(results):
                unique = []
                for p in results:
                    pid = str(getattr(p, "id", "")) or str(getattr(p, "external_id", ""))
                    if pid and pid in seen_ids:
                        continue
                    if pid:
                        seen_ids.add(pid)
                    unique.append(p)
                return unique
            
            fb1_results = _dedup(fb1_results)
            fb2_results = _dedup(fb2_results)

            # Fallback 3: drop operation_type entirely — shows available properties of same
            # physical type regardless of alquiler/venta. Covers cases where type=NULL in DB.
            op_type = search_criteria.get("operation_type") or search_criteria.get("type")
            fb3_criteria = {k: v for k, v in search_criteria.items()
                            if k not in ("operation_type", "type", "budget_max", "budget_min")}
            logger.info(f"[TOOL] Fallback 3: drop operation_type, keep property_type={fb3_criteria.get('property_type')}")
            fb3_results = await property_service.search_properties(fb3_criteria)
            fb3_results = _dedup(fb3_results)

            MAX_ALTERNATIVES = 3

            # Show best fallback with results (closest to original query)
            if fb1_results:
                budget_str = f" (hasta ${fb1_criteria.get('budget_max', 0):,})" if fb1_criteria.get("budget_max") else ""
                parts = [
                    f"No encontré {search_criteria.get('property_type', 'propiedades')} en {search_criteria.get('location', 'esa zona')} con esos filtros exactos. Pero tengo estas alternativas:\n",
                    f"🔱 Subiendo un poco el presupuesto{budget_str}:",
                ]
                parts.append(format_property_list(fb1_results[:MAX_ALTERNATIVES], fb1_criteria))
                return "\n".join(parts)
            elif fb2_results:
                parts = [
                    f"No encontré {search_criteria.get('property_type', 'propiedades')} en {search_criteria.get('location', 'esa zona')} con esos filtros exactos. Pero tengo estas alternativas:\n",
                    f"🔱 Opciones sin filtro de presupuesto:",
                ]
                parts.append(format_property_list(fb2_results[:MAX_ALTERNATIVES], fb2_criteria))
                return "\n".join(parts)
            elif fb3_results:
                # Found properties of the right type but not the requested operation_type
                op_label = f"en {op_type}" if op_type else ""
                pt_label = search_criteria.get("property_type", "propiedades")
                parts = [
                    f"Por el momento no tenemos {pt_label} disponibles {op_label}. Estas son las que tenemos disponibles:\n",
                ]
                parts.append(format_property_list(fb3_results[:MAX_ALTERNATIVES], fb3_criteria))
                return "\n".join(parts)
            else:
                # No results from any fallback — signal LLM to ask user for adjustments
                logger.info("[TOOL] All fallbacks returned 0 results — returning NO_RESULTS_ASK_MORE signal")
                return "NO_RESULTS_ASK_MORE"
        
        return format_property_list(properties, search_criteria)
        
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
    Obtiene los detalles de una propiedad específica por su ID o nombre.
    Soporta:
    - Integer ID (1, 2, 3... from seed data)
    - UUID (database primary key)  
    - Referencia ("opcion 5", "la primera")
    - Nombre o dirección ("San Martín 850", "casa centro") — búsqueda difusa
    
    Args:
        property_id: ID de la propiedad (integer 1-50, UUID, nombre o referencia)
    
    Returns:
        String formateado con los detalles de la propiedad o lista de candidatos
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
        
        prop = None
        
        # Try integer ID first
        if is_numeric:
            try:
                int_id = int(property_id)
                if 1 <= int_id <= 1000:
                    logger.info(f"[get_property_details] Buscando por integer ID: {int_id}")
                    from app.db.repository import BaseRepository
                    from app.db.models import Property
                    from app.db.session import async_session_factory
                    
                    async with async_session_factory() as session:
                        repo = BaseRepository(Property, session)
                        prop = await repo.get(int_id)
                    
                    if prop:
                        logger.info(f"[get_property_details] Encontrada por ID: {prop.id} - {prop.title}")
                        return format_property(prop)
            except Exception as e:
                logger.warning(f"[get_property_details] Integer lookup failed: {e}")
        
        # If not found, try UUID
        if not prop and is_uuid_like:
            try:
                prop_uuid = UUID(property_id)
                prop = await property_service.get_property_details(prop_uuid)
            except (ValueError, Exception) as e:
                logger.warning(f"[get_property_details] UUID lookup failed: {e}")
        
        # If numeric UUID failed AND input looks like a name/address → fuzzy search
        if not prop and not is_numeric:
            logger.info(f"[get_property_details] Buscando por nombre/dirección: '{property_id}'")
            candidates = await property_service.search_properties({
                "title_search": property_id,
                "limit": 5,
                "sort_by": "price_desc",
            })
            
            if not candidates:
                return (
                    f"No encontré ninguna propiedad que coincida con '{property_id}'. "
                    "¿Podrías darme más detalles? ¿Recordás el ID o alguna dirección exacta?"
                )
            
            # If exactly one match, return details
            if len(candidates) == 1:
                logger.info(f"[get_property_details] Coincidencia exacta por nombre: {candidates[0].title}")
                return format_property(candidates[0])
            
            # Multiple matches — return list for LLM to ask user
            logger.info(f"[get_property_details] {len(candidates)} candidatos encontrados por nombre")
            lines = [f"Encontré varias propiedades que coinciden con '{property_id}'. ¿Cuál de estas es?:\n"]
            for i, p in enumerate(candidates, 1):
                pid = p.original_id or p.id
                price = int(float(str(getattr(p, "price", 0))))
                loc = getattr(p, "location", "")
                op = getattr(p, "type", "venta")
                price_str = f"${price:,}/mes" if op == "alquiler" else f"${price:,}"
                lines.append(f"{i}. {p.title} | {price_str} | {loc} | ID:{pid}")
            
            return "\n".join(lines)
        
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
        
        return "✨ *Basado en tus preferencias, te recomiendo:*\n\n" + format_property_list(properties, criteria)
        
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
    phone: str = None,
    client_name: str = None
) -> str:
    """
    Agenda una visita a una propiedad.

    GUÍA PARA EL LLM:
    - Llamar esta función en cuanto tengas property_id y date_str, AUNQUE NO TENGAS client_name.
    - La función guarda la fecha/hora y pide el nombre ella sola — no lo hagas en texto primero.
    - Intenta enviar la fecha en formato DD/MM/YYYY cuando sea posible (ej: "29/04/2026")
    - También soporta expresiones naturales: "mañana a las 15hs", "el viernes a las 10 de la mañana"
    - Si date_str o time_str viene vacío pero hay contexto previo, úsalo
    - Si no podés determinar la fecha/hora, PREGUNTÁ al usuario antes de llamar (pero si tenés fecha, llamá aunque falte el nombre)

    Esta función pode receber:
    - property_id: ID de la propiedad (número o UUID)
    - date_str: "29/04/2026", "mañana", "el viernes", etc
    - time_str: "15:00", "a las 15hs", "10am", etc (opcional)
    - phone: Número de teléfono del usuário
    - client_name: Nombre y apellido del usuario (OBLIGATORIO si no se conoce)

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
        
        # Fix common typos in Spanish day names before parsing
        _TYPO_MAP = {
            "vienes": "viernes", "vienres": "viernes", "vienes": "viernes",
            "lunes": "lunes",  # correct, but keep for completeness
            "martes": "martes",
            "juves": "jueves", "juves": "jueves",
            "miercoles": "miércoles", "mièrcoles": "miércoles",
            "sabado": "sábado",
            "domingo": "domingo",
        }
        def _fix_typos(s: str) -> str:
            if not s:
                return s
            words = s.lower().split()
            fixed = [_TYPO_MAP.get(w, w) for w in words]
            return " ".join(fixed)
        date_str = _fix_typos(date_str or "")
        time_str = _fix_typos(time_str or "")

        # Combine date_str and time_str for parsing
        combined_input = f"{date_str} {time_str}".strip()

        from app.core.hybrid.date import date_parser as hybrid_date_parser
        from app.utils.date_parser import format_datetime_argentina, validate_future, get_argentina_now
        from app.services.appointment_service import appointment_service, format_appointment_confirmation
        from app.db.repository import UserRepository
        from app.db.models import User
        from app.db.session import async_session_factory
        logger.info(f"[schedule_visit] Input: date_str='{date_str}', time_str='{time_str}', combined='{combined_input}'")

        # ── Pre-check: if the date falls on a non-working day, warn proactively ──
        # This prevents the "ask for time → reject Sunday" back-and-forth.
        # We check before the full hybrid parse because the parser may return an
        # "ambiguous time" error before we ever get to check the day of the week.
        from app.utils.date_parser import _parse_date_advanced
        _raw_date, _ = _parse_date_advanced(combined_input.lower(), get_argentina_now())
        if _raw_date:
            _wd = _raw_date.weekday()
            if _wd == 6:
                logger.info(f"[schedule_visit] Pre-check: date {_raw_date} is a Sunday — rejecting early")
                # Still save pending scheduling so the LLM context preserves the property
                if phone and date_str:
                    try:
                        await memory_manager.save_pending_scheduling(
                            phone=phone,
                            property_id=str(property_id),
                            date_str=date_str,
                            time_str=time_str
                        )
                    except Exception:
                        pass
                return (
                    f"Los domingos no realizamos visitas. "
                    f"Nuestro horario de atención es de lunes a sábado de 9:00 a 18:00 hs. "
                    f"¿Qué otro día te viene bien?"
                )
        # ── End pre-check ──

        # Hybrid date parsing: LLM first, regex fallback (controlled by PARSER_DATE env var)
        parse_ctx = {"date_str": date_str, "time_str": time_str, "reference_dt": get_argentina_now()}
        date_result = await hybrid_date_parser.parse(combined_input, parse_ctx)
        parsed_dt = date_result.value
        parse_error = date_result.error

        logger.info(f"[schedule_visit] Parser returned: parsed_dt={parsed_dt}, parse_error={parse_error}")
        if parsed_dt:
            logger.info(f"[schedule_visit] PARSED: {format_datetime_argentina(parsed_dt)}")
        
        if parse_error:
            # Save pending scheduling info so the date persists even though we're asking for time.
            # Without this, when the user replies with the time, the LLM reconstructs the tool call
            # from chat history and may substitute 'mañana' for the original 'el viernes'.
            if phone and date_str:
                try:
                    await memory_manager.save_pending_scheduling(
                        phone=phone,
                        property_id=str(property_id),
                        date_str=date_str,
                        time_str=time_str
                    )
                    logger.info(f"[schedule_visit] Pending scheduling saved (time ambiguous): property={property_id}, date={date_str}")
                except Exception as e:
                    logger.warning(f"[schedule_visit] No se pudo guardar pending scheduling (parse_error): {e}")
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

        # ── Business hours validation: lunes-sábado 9:00-18:00 hora Argentina ──
        _weekday = start_datetime.weekday()  # 0=Lun, 6=Dom
        _hour = start_datetime.hour
        if _weekday == 6:  # Domingo
            return (
                "Los domingos no realizamos visitas. "
                "Nuestro horario de atención es de lunes a sábado de 9:00 a 18:00 hs. "
                "¿Qué otro día te viene bien?"
            )
        if not (9 <= _hour < 18):
            return (
                f"El horario de las {start_datetime.strftime('%H:%M')} hs está fuera de nuestro horario de atención "
                f"(lunes a sábado de 9:00 a 18:00 hs). "
                f"¿A qué hora del día preferís la visita?"
            )

        logger.info(f"[schedule_visit] Parsed date: {date_str} + {time_str} -> {start_datetime.strftime('%Y-%m-%d %H:%M')}")
        
        # Get user in separate session
        user = None
        async with async_session_factory() as session:
            try:
                user_repo = UserRepository(User, session)
                user = await user_repo.get_by_phone(phone)
                if not user:
                    return "No te encontré en el sistema. ¿Podrías darme tu nombre y apellido?"
                logger.info(f"[schedule_visit] User found: {user.id}, name={user.name!r}")

                # ── Nombre obligatorio antes de agendar ──────────────────────
                effective_name = client_name or user.name
                if not effective_name or not effective_name.strip():
                    # Guardar fecha/hora en Redis para que el próximo turno las tenga disponibles.
                    # Sin esto, cuando el usuario responde con su nombre, el LLM no tiene la fecha
                    # en el contexto estructurado y la omite al reconstruir la llamada a schedule_visit.
                    if phone and date_str:
                        try:
                            await memory_manager.save_pending_scheduling(
                                phone=phone,
                                property_id=str(property_id),
                                date_str=date_str,
                                time_str=time_str
                            )
                            logger.info(f"[schedule_visit] Pending scheduling saved: property={property_id}, date={date_str}, time={time_str}")
                        except Exception as e:
                            logger.warning(f"[schedule_visit] No se pudo guardar pending scheduling: {e}")
                    return (
                        "Antes de confirmar la visita necesito tu nombre y apellido. "
                        "¿Me los decís?"
                    )

                # Si el usuario no tenía nombre guardado, guardarlo ahora
                if not user.name and effective_name:
                    try:
                        await user_repo.update(user.id, name=effective_name.strip())
                        await session.commit()
                        logger.info(f"[schedule_visit] Nombre guardado: {effective_name!r} para {phone}")
                    except Exception as e:
                        logger.warning(f"[schedule_visit] No se pudo guardar el nombre: {e}")

            except Exception as e:
                logger.error(f"[schedule_visit] Error getting user: {e}")
                return "Tuve un problema al buscarte en el sistema. ¿Podrías intentar de nuevo?"

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
                        # Embed first suggestion as hidden comment so LLM can confirm it on next "si"
                        first_dt = suggestions[0].get("datetime", "")  # e.g. "2026-05-23 17:00"
                        hidden = ""
                        if first_dt:
                            _d = first_dt.split(" ")[0] if " " in first_dt else first_dt
                            _t = first_dt.split(" ")[1] if " " in first_dt else ""
                            hidden = (
                                f"\n\n<!--ALTERNATIVES_PROPOSED:"
                                f" si el usuario confirma, llamá schedule_visit("
                                f"property_id={property_id}, date_str=\"{_d}\", time_str=\"{_t}\")-->"
                            )
                        return f"⚠️ {msg}\n\n🎯 Horarios disponibles:\n" + "\n".join(lines) + "\n\n¿Alguna?" + hidden
                    return f"⚠️ {msg}\n\n¿Qué otro horario te conviene?" 
                return f"⚠️ No se pudo completar la agenda.\n\n¿Qué otro horario te conviene?"
            
            # Success - format confirmation
            appointment = result.get("appointment")
            if appointment:
                property_title = getattr(property_obj, "title", "Propiedad") if hasattr(property_obj, "title") else "Propiedad"
                # ── Notificación al dashboard ────────────────────────────
                try:
                    from app.services.notification_service import notification_service
                    from app.utils.date_parser import format_datetime_argentina
                    apt_type = getattr(appointment, "type", "visit")
                    dt_str = format_datetime_argentina(appointment.start_time) if hasattr(appointment, "start_time") else ""
                    if apt_type == "call":
                        await notification_service.call_scheduled(phone=phone, datetime_str=dt_str, event_id=getattr(appointment, "id", None))
                    else:
                        await notification_service.visit_scheduled(
                            phone=phone,
                            property_title=property_title,
                            datetime_str=dt_str,
                            property_id=prop_int_id,
                            event_id=getattr(appointment, "id", None),
                        )
                except Exception as _ne:
                    logger.debug(f"[schedule_visit] Notif error (non-fatal): {_ne}")
                # Clear pending scheduling state so next turn doesn't re-trigger the scheduling nudge
                if phone:
                    try:
                        await memory_manager.clear_pending_scheduling(phone)
                        logger.info(f"[schedule_visit] Pending scheduling cleared for {phone}")
                    except Exception as _ce:
                        logger.warning(f"[schedule_visit] Could not clear pending scheduling: {_ce}")
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
        
        # If no valid UUID, try to find upcoming appointments for this user
        if not apt_uuid and phone:
            try:
                from app.db.models import User
                from datetime import timezone as tz
                async with async_session_factory() as db:
                    user_repo_q = select(User).where(User.whatsapp_phone == phone)
                    user_result = await db.execute(user_repo_q)
                    user = user_result.scalar_one_or_none()
                    if user:
                        now_utc = datetime.now(tz.utc)
                        apt_q = (
                            select(AppointmentModel)
                            .where(AppointmentModel.user_id == user.id)
                            .where(AppointmentModel.status == "confirmed")
                            .where(AppointmentModel.start_time > now_utc)
                            .order_by(AppointmentModel.start_time.asc())
                        )
                        apt_result = await db.execute(apt_q)
                        upcoming_apts = list(apt_result.scalars().all())
                        
                        if len(upcoming_apts) == 1:
                            apt_uuid = upcoming_apts[0].id
                            logger.info(f"[reschedule] Auto-resolved single upcoming appointment: {apt_uuid}")
                        elif len(upcoming_apts) > 1:
                            # Multiple upcoming — list them so the LLM can ask the user which one
                            lines = ["Tienes varias citas próximas. ¿Cuál te gustaría reprogramar?", ""]
                            import pytz
                            arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
                            for i, apt in enumerate(upcoming_apts, 1):
                                start = apt.start_time
                                if start.tzinfo is not None:
                                    start_local = start.astimezone(arg_tz)
                                else:
                                    start_local = arg_tz.localize(start)
                                date_str = start_local.strftime("%d/%m/%Y")
                                time_str = start_local.strftime("%H:%M")
                                lines.append(f"{i}. 📆 {date_str} a las {time_str}")
                            lines.append("")
                            lines.append("Decime el número de la cita que quieras cambiar.")
                            message = "\n".join(lines)
                            # Append hidden UUID mapping for LLM consumption
                            id_lines = []
                            for i, apt in enumerate(upcoming_apts, 1):
                                id_lines.append(f"<!--ID:{i}:{apt.id}-->")
                            if id_lines:
                                message += "\n" + "\n".join(id_lines)
                            return message
            except Exception as e:
                logger.warning(f"[reschedule] Could not auto-resolve appointment: {e}")
        
        if not apt_uuid:
            return "No encontré citas futuras para reprogramar. ¿Querés agendar una nueva visita?"
        
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
        
        # Stage 1: Try numeric date formats directly (no LLM cost, handles "12/05/2026")
        date_obj = None
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"]:
            try:
                date_obj = datetime.strptime(new_date_str.strip(), fmt).date()
                logger.info(f"[reschedule] Numeric format {fmt}: '{new_date_str}' -> {date_obj}")
                break
            except ValueError:
                continue

        # Stage 2: Natural language dates via hybrid parser (LLM first, code fallback)
        if date_obj is None:
            if not new_date_str.strip():
                return "Necesito saber la nueva fecha."

            from app.core.hybrid.date import date_parser as hybrid_date_parser

            parse_ctx = {"date_str": new_date_str, "time_str": new_time_str}
            date_result = await hybrid_date_parser.parse(new_date_str, parse_ctx)

            if date_result and date_result.value:
                date_obj = date_result.value.date()
                logger.info(
                    "[reschedule] Hybrid parser '%s' -> %s (parser=%s, conf=%.2f)",
                    new_date_str,
                    date_obj,
                    date_result.parser_used,
                    date_result.confidence,
                )
            elif date_result and date_result.error:
                return date_result.error
            else:
                return (
                    f"No pude entender la fecha '{new_date_str}'. "
                    f"Por favor usa formato como '12/05/2026' o 'proximo martes'."
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

        # ── Notificación al dashboard ────────────────────────────────
        try:
            from app.services.notification_service import notification_service
            from app.utils.date_parser import format_datetime_argentina
            dt_str = format_datetime_argentina(appointment.start_time) if hasattr(appointment, "start_time") else ""
            await notification_service.visit_rescheduled(
                phone=phone or "",
                property_title="Visita",
                datetime_str=dt_str,
                event_id=getattr(appointment, "id", None),
            )
        except Exception as _ne:
            logger.debug(f"[reschedule] Notif error (non-fatal): {_ne}")

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
    from datetime import datetime, timezone as tz
    from app.services.appointment_service import appointment_service
    from app.db.session import async_session_factory
    from app.db.models import Appointment as AppointmentModel, User
    from sqlalchemy import select
    
    try:
        apt_uuid = None
        
        # Try to parse the appointment_id as UUID
        if appointment_id:
            try:
                apt_uuid = UUID(appointment_id)
            except ValueError:
                logger.warning(f"[cancel] ⚠️ LLM pasó ID inválido '{appointment_id}' — buscando citas futuras del usuario")
                apt_uuid = None
        
        # If no valid UUID, try to find upcoming appointments for this user
        if not apt_uuid and phone:
            try:
                async with async_session_factory() as db:
                    user_q = select(User).where(User.whatsapp_phone == phone)
                    user_result = await db.execute(user_q)
                    user = user_result.scalar_one_or_none()
                    if user:
                        now_utc = datetime.now(tz.utc)
                        apt_q = (
                            select(AppointmentModel)
                            .where(AppointmentModel.user_id == user.id)
                            .where(AppointmentModel.status == "confirmed")
                            .where(AppointmentModel.start_time > now_utc)
                            .order_by(AppointmentModel.start_time.asc())
                        )
                        apt_result = await db.execute(apt_q)
                        upcoming_apts = list(apt_result.scalars().all())
                        
                        if len(upcoming_apts) == 1:
                            apt_uuid = upcoming_apts[0].id
                            logger.info(f"[cancel] Auto-resolved single upcoming appointment: {apt_uuid}")
                        elif len(upcoming_apts) > 1:
                            lines = ["Tienes varias citas próximas. ¿Cuál te gustaría cancelar?", ""]
                            for i, apt in enumerate(upcoming_apts, 1):
                                start = apt.start_time
                                date_str = start.strftime("%d/%m/%Y")
                                time_str = start.strftime("%H:%M")
                                lines.append(f"{i}. 📆 {date_str} a las {time_str} — ID: `{apt.id}`")
                            lines.append("")
                            lines.append("Decime el número o el ID de la cita que quieras cancelar.")
                            return "\n".join(lines)
            except Exception as e:
                logger.warning(f"[cancel] Could not auto-resolve appointment: {e}")
        
        if not apt_uuid:
            return "No encontré citas futuras para cancelar. ¿Querés agendar una nueva visita?"
        
        await appointment_service.cancel_appointment(apt_uuid, reason)

        # ── Notificación al dashboard ────────────────────────────────
        try:
            from app.services.notification_service import notification_service
            await notification_service.visit_cancelled(
                phone=phone or "",
                property_title="Visita",
                reason=reason or "",
                event_id=apt_uuid,
            )
        except Exception as _ne:
            logger.debug(f"[cancel] Notif error (non-fatal): {_ne}")

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

            # Fetch property titles for display
            from app.db.models import Property
            from sqlalchemy import select
            prop_ids = list({a.property_id for a in appointments})
            property_titles = {}
            if prop_ids:
                try:
                    prop_result = await session.execute(
                        select(Property.id, Property.title).where(Property.id.in_(prop_ids))
                    )
                    for row in prop_result.all():
                        property_titles[row[0]] = row[1]
                except Exception as _pe:
                    logger.warning(f"[get_my_appointments] Error fetching property titles: {_pe}")

            return format_appointment_list(appointments, property_titles)
            
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

        # ── Notificación al dashboard ────────────────────────────────
        try:
            from app.services.notification_service import notification_service
            await notification_service.handoff_requested(phone=phone, reason=reason)
        except Exception as _ne:
            logger.debug(f"[handoff] Notif error (non-fatal): {_ne}")

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
        cur = getattr(prop, "currency", "ARS") or "ARS"
        prefix = "USD " if cur == "USD" else ""
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


async def execute_tool(tool_name: str, arguments: dict, phone: str = None):
    """
    Ejecuta una herramienta por nombre con sus argumentos.

    v2.0: Returns a typed dataclass (ToolResult) instead of a raw string.
    Call .to_json() for the LLM context, .user_message for the user response.

    Args:
        tool_name: Nombre de la herramienta
        arguments: Argumentos de la herramienta
        phone: Número de teléfono del usuario (para algunas herramientas)

    Returns:
        One of: SearchResult, DetailResult, ScheduleResult, etc.
        All have .to_json() -> str and .user_message -> str
    """
    if tool_name not in TOOL_FUNCTIONS:
        from app.agents.tool_results import SimpleResult
        return SimpleResult(
            action="error",
            success=False,
            user_message=f"Herramienta '{tool_name}' no encontrada.",
        )

    func = TOOL_FUNCTIONS[tool_name]

    try:
        if phone and tool_name in ["update_user_preferences", "get_user_preferences", "save_lead_info"]:
            arguments["phone"] = phone

        if tool_name == "search_properties":
            raw = await func(arguments, phone=phone)
        elif tool_name == "recommend_properties":
            raw = await func(arguments)
        elif tool_name == "get_property_details":
            raw = await func(**arguments)
        elif tool_name in ["schedule_visit", "reschedule_appointment", "cancel_appointment", "get_my_appointments", "request_human_assistance"]:
            raw = await func(phone=phone, **arguments)
        else:
            raw = await func(**arguments)

        return _wrap_tool_result(tool_name, raw, arguments)

    except TypeError as e:
        logger.error(f"Error de tipos en {tool_name}: {e}")
        from app.agents.tool_results import SimpleResult
        return SimpleResult(
            action="error",
            success=False,
            user_message=f"Error al ejecutar {tool_name}: argumentos inválidos.",
        )
    except Exception as e:
        logger.error(f"Error ejecutando {tool_name}: {e}")
        from app.agents.tool_results import SimpleResult
        return SimpleResult(
            action="error",
            success=False,
            user_message=f"Error al ejecutar {tool_name}: {str(e)}",
        )


def _wrap_tool_result(tool_name: str, raw: str, arguments: dict):
    """v2.0: Wrap a raw string tool result in a typed dataclass.

    Extracts structured data from the raw string where possible.
    For now, the user_message IS the raw string (backward compat).
    The LLM receives both the structured metadata AND the user_message.
    """
    from app.agents.tool_results import (
        SearchResult, DetailResult, ScheduleResult,
        AppointmentListResult, AppointmentActionResult,
        ImageResult, FAQResult, SimpleResult,
        PropertySummary,
    )

    if tool_name in ("search_properties", "refine_search", "recommend_properties"):
        # Extract property count from formatted output (counts 📍 markers)
        prop_count = raw.count("📍") if raw else 0
        return SearchResult(
            properties=[],  # structured extraction deferred to later phase
            total_count=prop_count,
            criteria_applied=arguments,
            fallback_applied="NO_RESULTS" not in raw if raw else True,
            user_message=raw,
        )

    if tool_name == "get_property_details":
        return DetailResult(
            property=None,  # structured extraction deferred
            description="",
            image_count=0,
            user_message=raw,
        )

    if tool_name == "schedule_visit":
        # Parse the raw string for status signals
        status: str = "needs_date"
        if "Cita Agendada" in raw or "<!--CONFIRMED:" in raw:
            status = "confirmed"
        elif "domingo" in raw.lower() or "fuera de horario" in raw.lower():
            status = "rejected"
        elif "nombre" in raw.lower() and "apellido" in raw.lower():
            status = "needs_name"
        elif "hora" in raw.lower():
            status = "needs_time"

        return ScheduleResult(
            status=status,
            property_id=str(arguments.get("property_id", "")),
            date=arguments.get("date_str"),
            time=arguments.get("time_str"),
            user_message=raw,
        )

    if tool_name in ("reschedule_appointment", "cancel_appointment"):
        action = "rescheduled" if tool_name == "reschedule_appointment" else "cancelled"
        success = "Cita Reprogramada" in raw or "Cita Cancelada" in raw or "<!--CONFIRMED:" in raw
        return AppointmentActionResult(
            action=action,
            success=success,
            appointment_id=arguments.get("appointment_id", ""),
            user_message=raw,
        )

    if tool_name == "get_my_appointments":
        return AppointmentListResult(
            appointments=[],
            count=raw.count("<!--ID:") if raw else 0,
            user_message=raw,
        )

    if tool_name == "get_property_images":
        # Parse the JSON result to extract actual image URLs
        image_urls = []
        count = 0
        try:
            parsed = json.loads(raw)
            image_urls = parsed.get("images", [])
            count = len(image_urls)
        except (json.JSONDecodeError, TypeError):
            pass
        return ImageResult(
            property_id=str(arguments.get("property_id", "")),
            image_urls=image_urls,
            count=count,
            user_message=raw,
        )

    if tool_name == "get_faq_answer":
        has_answer = bool(raw and raw.strip() and
                         "no tengo información" not in raw.lower() and
                         raw.strip() not in ("{}", "[]"))
        return FAQResult(
            question=arguments.get("question", ""),
            answer=raw,
            found=has_answer,
            user_message=raw,
        )

    # Default: SimpleResult for handoff, preferences, etc.
    return SimpleResult(
        action=tool_name,
        success=True,
        user_message=raw,
    )


__all__ = [
    "search_properties",
    "get_property_images",
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

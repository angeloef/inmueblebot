"""Schedule a visit to view a property.

The scheduling specialist handles all field gathering. This tool is
called ONLY when all data is confirmed — it validates and registers.
"""

import re


async def schedule_visit(
    property_id: int = 0,
    nombre: str = "",
    telefono: str = "",
    dia: str = "",
    horario: str = "",
    consulta: str = "",
) -> str:
    """Register a visit request for a property. Called only when confirmed."""
    # Validate required fields (specialist should have gathered these already)
    missing = []
    if not property_id:
        missing.append("ID de propiedad")
    if not nombre:
        missing.append("nombre")
    if not telefono:
        missing.append("teléfono")
    
    if missing:
        return (
            f"⚠️ Faltan datos para confirmar: {', '.join(missing)}. "
            f"El especialista debe recolectarlos antes de llamar a schedule_visit."
        )
    
    # Validate time is within operating hours
    if horario:
        time_valid, time_msg = _validate_time(horario, dia)
        if not time_valid:
            return time_msg
    
    lines = [
        "✅ ¡Visita agendada!",
        "",
        f"🏠 Propiedad: #{property_id}",
        f"👤 Nombre: {nombre}",
        f"📱 Teléfono: {telefono}",
    ]
    if dia:
        lines.append(f"📅 Día: {dia}")
    if horario:
        lines.append(f"🕐 Horario: {horario}")
    if consulta:
        lines.append(f"💬 Consulta: {consulta}")
    
    lines.append("")
    lines.append(
        "Te vamos a confirmar por WhatsApp en las próximas 24-48 hs "
        "con la dirección exacta y horario coordinado. ¡Gracias!"
    )
    
    return "\n".join(lines)


def _validate_time(horario: str, dia: str = "") -> tuple[bool, str]:
    """Validate that the time is within operating hours.
    
    Operating hours:
    - Mon-Fri: 09:00-12:00 and 15:00-18:00
    - Sat: 09:00-12:00
    - Sun: closed
    
    Returns (is_valid, error_message).
    """
    horario_lower = horario.lower().strip()
    
    # Check if it's a Saturday — only morning available
    dia_lower = dia.lower().strip() if dia else ""
    is_saturday = any(d in dia_lower for d in ["sábado", "sabado", "saturday"])
    
    # Parse known time formats
    # "8pm", "20:00", "20hs", "8 de la noche", "noche", "tarde", "mañana", etc.
    
    # Broad time-of-day categories
    if horario_lower in ("mañana", "manana", "maã±ana"):
        return True, ""
    if horario_lower in ("tarde",):
        return True, ""
    if horario_lower in ("noche", "madrugada"):
        return False, (
            "⏰ Lo siento, no hacemos visitas de noche. Nuestros horarios son "
            "09:00-12:00 y 15:00-18:00 (sábados solo 09:00-12:00). "
            "¿Te sirve a las 16:00?"
        )
    
    # Try to extract hour
    hour = None
    # "8pm", "8 pm", "8:00pm"
    m = re.search(r"(\d{1,2})\s*(?::(\d{2}))?\s*(pm|am|p\.m\.|a\.m\.)", horario_lower)
    if m:
        h = int(m.group(1))
        is_pm = "p" in m.group(3) if m.group(3) else False
        if is_pm and h != 12:
            h += 12
        elif not is_pm and h == 12:
            h = 0
        hour = h
    else:
        # "20:00", "20hs", "20"
        m = re.search(r"(\d{1,2})[:h]", horario_lower)
        if m:
            hour = int(m.group(1))
        else:
            m = re.match(r"^(\d{1,2})$", horario_lower)
            if m:
                h = int(m.group(1))
                # Assume 1-7 = PM, 8-12 = AM (unless > 12, then it's 24h)
                if h <= 7:
                    hour = h + 12
                elif h <= 12:
                    hour = h
                elif h <= 23:
                    hour = h
    
    if hour is not None:
        if is_saturday and hour >= 12:
            return False, (
                f"⏰ Los sábados solo hacemos visitas de 09:00 a 12:00. "
                f"¿Te sirve a las 10:00 del sábado, o preferís un día de semana a las {horario}?"
            )
        if hour < 9:
            return False, (
                f"⏰ Nuestro horario comienza a las 09:00. ¿Te sirve a las 09:00 o preferís más tarde?"
            )
        if 12 <= hour < 15:
            return False, (
                f"⏰ De 12:00 a 15:00 estamos cerrados. ¿Te sirve a las 15:00 o preferís otro horario?"
            )
        if hour >= 18:
            return False, (
                f"⏰ Nuestro último turno es a las 18:00. ¿Te sirve a las 16:00 o preferís más temprano?"
            )
        return True, ""
    
    # Unrecognized format — accept it (specialist should have validated)
    return True, ""

"""Schedule a visit to view a property — creates Appointment in DB + Google Calendar.

The scheduling specialist handles all field gathering. This tool is
called ONLY when all data is confirmed — it validates and persists.
"""

import re
from datetime import datetime, timezone, timedelta
from uuid import UUID

from loguru import logger

from app.db.session import async_session_factory
from app.db.models import User, Property
from app.db.repository import UserRepository
from app.services.appointment_service import appointment_service, format_appointment_confirmation
from app.utils.date_parser import format_datetime_argentina, get_argentina_now


async def schedule_visit(
    property_id: int = 0,
    nombre: str = "",
    telefono: str = "",
    dia: str = "",
    horario: str = "",
    consulta: str = "",
) -> str:
    """Register a visit in the DB. Called by the scheduling specialist when all fields are confirmed.

    Args:
        property_id: The numeric ID of the property.
        nombre: Full name of the interested person.
        telefono: Contact phone number.
        dia: Natural language day expression (e.g., "viernes", "mañana").
        horario: Natural language time (e.g., "tarde", "15:00", "a las 10").
        consulta: Any additional question or note.
    """
    # ── Validate required fields ────────────────────────────────
    missing = []
    if not property_id:
        missing.append("ID de propiedad")
    if not nombre:
        missing.append("nombre")
    if not telefono:
        missing.append("teléfono")
    if not dia:
        missing.append("día")

    if missing:
        return (
            f"⚠️ Faltan datos para confirmar: {', '.join(missing)}. "
            f"El especialista debe recolectarlos antes de llamar a schedule_visit."
        )

    # ── Parse date/time ─────────────────────────────────────────
    combined_input = f"{dia} {horario}".strip()
    now = get_argentina_now()

    from app.core.hybrid.date import date_parser as hybrid_date_parser

    parse_ctx = {
        "date_str": dia,
        "time_str": horario,
        "reference_dt": now,
    }
    date_result = await hybrid_date_parser.parse(combined_input, parse_ctx)
    parsed_dt = date_result.value

    if not parsed_dt:
        # Fallback: try basic Spanish day name + time parsing
        parsed_dt = _parse_simple_date(dia, horario, now)

    if not parsed_dt:
        return (
            f"No pude entender la fecha '{dia} {horario}'. "
            f"¿Podés ser más específico? Por ejemplo: 'viernes 14:00' o 'mañana a la tarde'."
        )

    start_datetime = parsed_dt

    # ── Business hours check ────────────────────────────────────
    weekday = start_datetime.weekday()
    hour = start_datetime.hour
    if weekday == 6:
        return (
            "Los domingos no realizamos visitas. Nuestro horario es "
            "lunes a sábado de 9:00 a 18:00 hs. ¿Qué otro día te viene bien?"
        )
    if not (9 <= hour < 18):
        return (
            f"El horario de las {start_datetime.strftime('%H:%M')} hs está fuera de nuestro "
            f"horario de atención (9:00 a 18:00 hs). ¿A qué hora preferís?"
        )

    # ── Look up or create user ──────────────────────────────────
    async with async_session_factory() as session:
        user_repo = UserRepository(User, session)
        user = await user_repo.get_by_phone(telefono)

        if not user:
            # Create minimal user
            try:
                from uuid import uuid4 as _uuid4
                user = User(
                    id=_uuid4(),
                    whatsapp_phone=telefono,
                    name=nombre.strip(),
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info(f"[schedule_visit] New user created: {user.id} phone={telefono}")
            except Exception as e:
                logger.error(f"[schedule_visit] Failed to create user: {e}")
                return "Tuve un problema al registrarte. ¿Podrías intentar de nuevo?"

        # Update name if missing
        if not user.name and nombre:
            try:
                await user_repo.update(user.id, name=nombre.strip())
                await session.commit()
                logger.info(f"[schedule_visit] Name updated for {telefono}: {nombre}")
            except Exception as e:
                logger.warning(f"[schedule_visit] Could not update name: {e}")

    # ── Create appointment ──────────────────────────────────────
    try:
        result = await appointment_service.create_appointment(
            user_id=user.id,
            property_id=property_id,
            start_time=start_datetime,
            type="visit",
            notes=consulta or None,
            user_phone=telefono,
        )
    except Exception as e:
        logger.error(f"[schedule_visit] create_appointment failed: {e}")
        return "Tuve un problema técnico al agendar. ¿Podrías intentar en unos minutos?"

    if not isinstance(result, dict) or not result.get("success"):
        msg = result.get("message", "Horario no disponible") if isinstance(result, dict) else "Error al agendar"
        suggestions = result.get("suggested_times", []) if isinstance(result, dict) else []
        if suggestions:
            lines = [f"- {s.get('formatted', str(s))}" for s in suggestions[:3]]
            return f"⚠️ {msg}\n\n🎯 Horarios disponibles:\n" + "\n".join(lines) + "\n\n¿Alguno te sirve?"
        return f"⚠️ {msg}\n\n¿Qué otro horario te conviene?"

    # ── Success ─────────────────────────────────────────────────
    appointment = result.get("appointment")
    if appointment:
        # Send dashboard notification
        try:
            from app.services.notification_service import notification_service
            await notification_service.visit_scheduled(
                phone=telefono,
                property_title=f"Propiedad #{property_id}",
                datetime_str=format_datetime_argentina(appointment.start_time)
                if hasattr(appointment, "start_time") else dia,
                property_id=property_id,
                event_id=getattr(appointment, "id", None),
            )
        except Exception:
            logger.debug("[schedule_visit] Notification send failed (non-fatal)")

        return format_appointment_confirmation(appointment, f"Propiedad #{property_id}")

    # ── Fallback confirmation (no appointment object) ───────────
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


def _parse_simple_date(dia: str, horario: str, now: datetime) -> datetime | None:
    """Simple fallback date parser for common Spanish expressions."""
    dia_lower = dia.lower().strip()
    horario_lower = horario.lower().strip()

    # Map day names to offsets from today
    day_map = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5,
        "domingo": 6,
    }

    target_weekday = None
    for name, offset in day_map.items():
        if name in dia_lower:
            target_weekday = offset
            break

    if target_weekday is None and "mañana" in dia_lower:
        target_weekday = (now.weekday() + 1) % 7
    elif target_weekday is None and "hoy" in dia_lower:
        target_weekday = now.weekday()

    if target_weekday is None:
        return None

    # Calculate days until target weekday
    current = now.weekday()
    days_ahead = target_weekday - current
    if days_ahead <= 0:
        days_ahead += 7

    target_date = now + timedelta(days=days_ahead)

    # Parse time
    hour = 16  # default afternoon
    minute = 0

    time_map = {
        "mañana": 10, "manana": 10,
        "tarde": 16,
        "noche": 18,
    }

    for name, h in time_map.items():
        if name in horario_lower:
            hour = h
            break

    # Try numeric time: "15:00", "15hs", "15", "8pm"
    m = re.search(r"(\d{1,2})[:h]?\s*(pm|am)?", horario_lower)
    if m:
        h = int(m.group(1))
        is_pm = m.group(2) == "pm" if m.group(2) else False
        if is_pm and h != 12:
            h += 12
        elif not is_pm and h == 12:
            h = 0
        if 0 <= h <= 23:
            hour = h

    return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

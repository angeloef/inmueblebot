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
    # ── Step 1: require the fields needed to parse/validate the slot ─────────
    # property_id + día + horario define the slot; nombre is checked LATER so an
    # out-of-hours or invalid time is rejected IMMEDIATELY, not after we've made
    # the user hand over their name. `telefono` is never required — identity comes
    # from the session (WhatsApp/BSUID), not a number typed into the chat.
    if not property_id:
        return "Para agendar la visita necesito saber qué propiedad te interesa. ¿Cuál querés visitar?"
    if not dia:
        return "¡Genial! ¿Qué día te gustaría la visita?"
    if not horario or not horario.strip():  # None-safe (LLM JSON may send null)
        return "¿En qué horario te gustaría la visita?"

    # ── Step 2: parse date/time ─────────────────────────────────────────────
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

    # ── Roll forward if the parsed datetime is already in the past ──
    # e.g. "el sábado a las 11" cuando HOY es sábado y esa hora ya pasó → próximo sábado.
    try:
        if start_datetime <= now:
            start_datetime = start_datetime + timedelta(days=7)
    except TypeError:
        # tz-aware vs naive mismatch — normalize to compare
        from app.utils.date_parser import get_argentina_now as _ar_now
        if start_datetime.tzinfo is None:
            start_datetime = start_datetime.replace(tzinfo=_ar_now().tzinfo)
        if start_datetime <= _ar_now():
            start_datetime = start_datetime + timedelta(days=7)

    # ── Step 3: business-hours gate (reject BEFORE asking for the name) ──────
    # Windows + timezone come from the tenant (FAQ-documented hours): Lun–Vie
    # 9–18, Sáb 9–13, Dom cerrado by default. One source of truth.
    from app.core.tenancy import resolve_tenant_id
    from app.routers.v3.scheduling.utils import (
        load_tenant_hours,
        is_within_business_hours,
        describe_hours,
    )

    windows, _tz = await load_tenant_hours(resolve_tenant_id())
    hours_desc = describe_hours(windows)

    if start_datetime.weekday() not in windows:
        return (
            f"Ese día no realizamos visitas. Nuestro horario es {hours_desc}. "
            f"¿Qué otro día te viene bien?"
        )
    if not is_within_business_hours(start_datetime, windows):
        return (
            f"El horario de las {start_datetime.strftime('%H:%M')} hs está fuera de nuestro "
            f"horario de atención ({hours_desc}). ¿A qué hora preferís?"
        )

    # ── Step 3b: availability check (reject taken slots BEFORE asking name) ──
    # Checks the local DB conflict + Google Calendar (when configured). Fail-open:
    # returns available=True on any error, so a check failure never blocks booking.
    avail = await appointment_service.check_slot_availability(property_id, start_datetime)
    if not avail.get("available", True):
        suggestions = avail.get("suggested_times", [])
        if suggestions:
            lines = [f"- {s.get('formatted', str(s))}" for s in suggestions[:3]]
            return (
                "Ese horario ya está reservado. 🎯 Tengo disponibles:\n"
                + "\n".join(lines)
                + "\n\n¿Alguno te sirve?"
            )
        return "Ese horario ya está reservado. ¿Qué otro horario te conviene?"

    # ── Step 4: now require the name ────────────────────────────────────────
    if not nombre:
        return "¡Perfecto! ¿Me pasás tu nombre así dejo la visita confirmada?"

    # ── Resolve the user by SESSION identity (never the typed phone) ────
    # Identity comes from the webhook — BSUID first (stable, Meta migration), phone
    # as fallback — so a number the user types can't spawn a phantom/duplicate lead.
    # The typed `telefono`, if any, is stored only as a contact detail.
    from app.core.identity import get_current_contact
    _contact = get_current_contact()
    session_phone = _contact.get("phone")
    session_bsuid = _contact.get("bsuid")

    async with async_session_factory() as session:
        user_repo = UserRepository(User, session)
        user = None
        if session_bsuid:
            user = await user_repo.get_by_bsuid(session_bsuid)
        if not user and session_phone:
            user = await user_repo.get_by_phone(session_phone)
        # Last resort (e.g. admin /simulate with no session context): the typed phone.
        if not user and not session_phone and telefono:
            user = await user_repo.get_by_phone(telefono)

        if not user:
            try:
                from uuid import uuid4 as _uuid4
                identity_phone = session_phone or telefono
                extra: dict = {}
                if telefono and telefono != identity_phone:
                    extra["contact_phone"] = telefono
                user = User(
                    id=_uuid4(),
                    whatsapp_phone=identity_phone or None,
                    bsuid=session_bsuid or None,
                    name=nombre.strip() if nombre else None,
                    extra_data=extra or None,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info(
                    f"[schedule_visit] New user created: {user.id} "
                    f"phone={identity_phone} bsuid={session_bsuid}"
                )
            except Exception as e:
                logger.error(f"[schedule_visit] Failed to create user: {e}")
                return "Tuve un problema al registrarte. ¿Podrías intentar de nuevo?"
        else:
            # Backfill BSUID (column) / contact phone / name onto the canonical session user.
            update_fields: dict = {}
            if session_bsuid and user.bsuid != session_bsuid:
                update_fields["bsuid"] = session_bsuid
            if telefono and user.whatsapp_phone and telefono != user.whatsapp_phone:
                extra = dict(user.extra_data or {})
                if extra.get("contact_phone") != telefono:
                    extra["contact_phone"] = telefono
                    update_fields["extra_data"] = extra
            if not user.name and nombre:
                update_fields["name"] = nombre.strip()
            if update_fields:
                try:
                    await user_repo.update(user.id, **update_fields)
                    await session.commit()
                except Exception as e:
                    logger.warning(f"[schedule_visit] Could not backfill user: {e}")

    # ── Create appointment ──────────────────────────────────────
    try:
        result = await appointment_service.create_appointment(
            user_id=user.id,
            property_id=property_id,
            start_time=start_datetime,
            type="visit",
            notes=consulta or None,
            user_phone=user.whatsapp_phone or user.bsuid or "Unknown",
        )
    except Exception as e:
        logger.error(f"[schedule_visit] create_appointment failed: {e}")
        return await _handoff_on_failure(property_id, nombre, dia, horario)

    if not isinstance(result, dict) or not result.get("success"):
        # Technical failure (DB/RLS/unexpected) — NEVER confirm; hand off to a human
        # rather than leaking the error or telling the user to "try again later".
        if isinstance(result, dict) and result.get("error_type") == "technical":
            return await _handoff_on_failure(property_id, nombre, dia, horario)

        # Slot taken / not available — re-ask with concrete suggestions.
        msg = result.get("message", "Ese horario no está disponible") if isinstance(result, dict) else "Ese horario no está disponible"
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
                phone=user.whatsapp_phone or user.bsuid or "Unknown",
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


async def _handoff_on_failure(property_id: int, nombre: str, dia: str, horario: str) -> str:
    """Hand the booking off to a human when persistence fails.

    Per product decision: never confirm a visit that didn't persist. On a technical
    failure we escalate to a human agent (best-effort) and tell the user a person will
    finish coordinating — we do NOT say "agendada".
    """
    detail = f"Visita pedida — propiedad {property_id}, {nombre or 'sin nombre'}, {dia} {horario}".strip()
    try:
        from app.tools.v2.request_human_assistance import request_human_assistance
        await request_human_assistance(reason="booking_failed", message=detail)
    except Exception:
        logger.debug("[schedule_visit] request_human_assistance failed (non-fatal)")
    return (
        "Tuve un inconveniente para dejar la visita registrada en el sistema. "
        "Ya avisé a uno de nuestros asesores para que coordine con vos los últimos detalles. "
        "¡Disculpá la demora!"
    )


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

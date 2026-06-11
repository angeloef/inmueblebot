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


def _fallback_confirmation(
    *,
    property_id: int,
    prop_title: str | None,
    prop_address: str | None,
    nombre: str,
    dia: str,
    horario: str,
    consulta: str,
    roll_note: str,
    start_datetime,
) -> str:
    """Confirmation text for a booking that persisted but returned no appointment object.

    Reached only when ``create_appointment`` returned ``{"success": True}`` without an
    object. Emits the same ``<!--CONFIRMED:YYYY-MM-DD HH:MM-->`` structural marker as
    format_appointment_confirmation (plan #5) so the engine's ``booking_succeeded`` is
    True and Path 0b surfaces this confirmation instead of discarding it. The datetime
    comes from the parsed ``start_datetime`` (authoritative), not the raw dia/horario.
    """
    lines: list[str] = []
    if roll_note:
        lines.extend([roll_note, ""])
    lines.extend([
        "✅ ¡Visita agendada!",
        "",
        f"🏠 Propiedad: {prop_title or f'#{property_id}'}",
    ])
    if prop_address:
        lines.append(f"📍 Dirección: {prop_address}")
    lines.append(f"👤 Nombre: {nombre}")
    if dia:
        lines.append(f"📅 Día: {dia}")
    if horario:
        lines.append(f"🕐 Horario: {horario}")
    if consulta:
        lines.append(f"💬 Consulta: {consulta}")
    lines.append("")
    lines.append(
        "Te vamos a confirmar por WhatsApp en las próximas 24-48 hs "
        "con el horario coordinado. ¡Gracias!"
    )
    lines.append("")
    lines.append(f"<!--CONFIRMED:{start_datetime.strftime('%Y-%m-%d %H:%M')}-->")
    return "\n".join(lines)


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

    # ── Cross-check: a named weekday that contradicts an explicit date ──
    # "lunes 09/06" when 09/06 is actually a Tuesday is ambiguous — silently
    # picking one is how users end up at the wrong day. Ask which they meant.
    _named_wd = _named_weekday(dia)
    _explicit_d = _explicit_date_in(dia, now)
    if _named_wd is not None and _explicit_d is not None and _explicit_d.weekday() != _named_wd:
        return (
            f"Una aclaración para no equivocarme: el {_explicit_d.strftime('%d/%m')} cae "
            f"{_DAY_NAMES_ES[_explicit_d.weekday()]}, no {_DAY_NAMES_ES[_named_wd]}. "
            f"¿Coordinamos para el {_explicit_d.strftime('%d/%m')} o para el próximo "
            f"{_DAY_NAMES_ES[_named_wd]}?"
        )

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
    # The user must be TOLD when this happens (they said a past date and got a
    # different one). A named weekday / relative expression ("el lunes", "mañana")
    # rolls to the next weekly occurrence (+7); a bare explicit calendar date
    # ("08/06") that already passed rolls to next year, not +7 (which would land
    # on an unrelated weekday).
    roll_note: str | None = None
    if _is_past(start_datetime, now):
        original_dt = start_datetime
        has_weekday = _named_weekday(dia) is not None
        has_explicit = _explicit_date_in(dia, now) is not None
        if has_explicit and not has_weekday:
            try:
                start_datetime = start_datetime.replace(year=start_datetime.year + 1)
            except ValueError:  # Feb 29 → next year has no Feb 29
                start_datetime = start_datetime + timedelta(days=365)
        else:
            start_datetime = start_datetime + timedelta(days=7)
        logger.warning(
            f"[schedule_visit] past date rolled forward: {original_dt} → {start_datetime} "
            f"(input dia='{dia}' horario='{horario}')"
        )
        roll_note = (
            "ℹ️ La fecha que me pasaste ya había pasado, así que coordiné la visita "
            f"para el {_format_day_date(start_datetime)}. Si preferís otro día, decime."
        )

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

    # Localize to the tenant's timezone so the weekday/hour gate uses the tenant's
    # local wall clock (the parser localizes to Buenos_Aires; honor the tenant tz here).
    try:
        import zoneinfo
        _ttz = zoneinfo.ZoneInfo(_tz)
        if start_datetime.tzinfo is None:
            start_datetime = start_datetime.replace(tzinfo=_ttz)
        else:
            start_datetime = start_datetime.astimezone(_ttz)
    except Exception:
        pass

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

    # ── Step 4: now require a PLAUSIBLE name ────────────────────────────────
    if not nombre:
        return "¡Perfecto! ¿Me pasás tu nombre así dejo la visita confirmada?"
    if _looks_like_slot_value(nombre):
        # The captured "name" is actually a day/time/affirmation ("el viernes",
        # "tarde", "sí") — don't store it as the person's name.
        return "Perdón, ¿me decís tu nombre? Así dejo la visita agendada a tu nombre."

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

    # ── Resolve the real property title + address for the confirmation ──────
    prop_title, prop_address = await _load_property_title_address(property_id)

    # ── Success ─────────────────────────────────────────────────
    appointment = result.get("appointment")
    if appointment:
        # Send dashboard notification
        try:
            from app.services.notification_service import notification_service
            await notification_service.visit_scheduled(
                phone=user.whatsapp_phone or user.bsuid or "Unknown",
                property_title=prop_title or f"Propiedad #{property_id}",
                datetime_str=format_datetime_argentina(appointment.start_time)
                if hasattr(appointment, "start_time") else dia,
                property_id=property_id,
                event_id=getattr(appointment, "id", None),
            )
        except Exception as notif_exc:
            logger.warning(
                f"[schedule_visit] dashboard notification failed (non-fatal): "
                f"appointment={getattr(appointment, 'id', None)} property={property_id} err={notif_exc}"
            )

        return format_appointment_confirmation(
            appointment,
            property_title=prop_title or f"Propiedad #{property_id}",
            address=prop_address,
            note_prefix=roll_note,
        )

    # ── Fallback confirmation (no appointment object, but success) ──────
    # create_appointment returned success without an object. Emit the CONFIRMED
    # marker (plan #5) so the engine treats this as a real booking instead of
    # discarding it and telling the user "estoy recopilando los detalles".
    return _fallback_confirmation(
        property_id=property_id,
        prop_title=prop_title,
        prop_address=prop_address,
        nombre=nombre,
        dia=dia,
        horario=horario,
        consulta=consulta,
        roll_note=roll_note,
        start_datetime=start_datetime,
    )


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

    # Parse time — no silent default: if we can't read a time, return None so the
    # caller re-asks instead of booking a guessed hour the user never said.
    hour: int | None = None
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
        period = m.group(2)
        if period == "pm" and h != 12:
            h += 12
        elif period == "am" and h == 12:
            h = 0
        elif period is None and 1 <= h <= 7:
            # Bare hour 1–7 → PM. Business hours are 9–18, so "a las 3" means 15:00,
            # never 03:00 (which the hours gate would reject and confuse the user).
            h += 12
        if 0 <= h <= 23:
            hour = h

    if hour is None:
        return None

    return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ── Date/name validation helpers ──────────────────────────────────────────────

_DAY_NAMES_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

_WEEKDAY_TO_INT = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}

_EXPLICIT_DATE_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b")

# Words that are NEVER a person's name (slot values, affirmations, fillers).
_NON_NAME_WORDS = {
    "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado",
    "sabado", "domingo", "mañana", "manana", "tarde", "noche", "hoy", "mediodía",
    "mediodia", "si", "sí", "no", "ok", "okay", "dale", "listo", "gracias",
    "hola", "buenas", "porfa", "porfavor",
}


def _named_weekday(text: str) -> int | None:
    """Return the weekday int (Mon=0) named in text, or None."""
    t = (text or "").lower()
    for name, wd in _WEEKDAY_TO_INT.items():
        if name in t:
            return wd
    return None


def _explicit_date_in(text: str, now: datetime):
    """Return a date for an explicit DD/MM[/YYYY] found in text, else None."""
    m = _EXPLICIT_DATE_RE.search(text or "")
    if not m:
        return None
    try:
        day, month = int(m.group(1)), int(m.group(2))
        year = m.group(3)
        if year:
            year = int(year)
            if year < 100:
                year += 2000
        else:
            year = now.year
        from datetime import date as _date
        return _date(year, month, day)
    except (ValueError, TypeError):
        return None


def _is_past(dt: datetime, now: datetime) -> bool:
    """tz-safe '<= now' comparison."""
    try:
        return dt <= now
    except TypeError:
        d = dt if dt.tzinfo else dt.replace(tzinfo=now.tzinfo)
        n = now if now.tzinfo else now.replace(tzinfo=d.tzinfo)
        return d <= n


def _format_day_date(dt: datetime) -> str:
    """'lunes 15/06' for a user-facing date confirmation."""
    return f"{_DAY_NAMES_ES[dt.weekday()]} {dt.strftime('%d/%m')}"


def _looks_like_slot_value(name: str) -> bool:
    """True if the captured 'name' is actually a day/time/affirmation, not a name."""
    n = (name or "").strip().lower()
    if not n:
        return False
    if re.search(r"\d", n):  # contains digits → a time or date, not a name
        return True
    if _named_weekday(n) is not None:
        return True
    return n in _NON_NAME_WORDS


async def _load_property_title_address(property_id: int) -> tuple[str | None, str | None]:
    """Fetch (title, address) for the property so the confirmation can show both.

    Returns (None, None) on any error — the caller falls back to "Propiedad #N".
    """
    try:
        async with async_session_factory() as session:
            from sqlalchemy import select as _select
            row = (await session.execute(
                _select(Property.title, Property.location).where(Property.id == property_id)
            )).first()
            if row:
                return row[0], row[1]
    except Exception as exc:
        logger.debug(f"[schedule_visit] could not load property {property_id}: {exc}")
    return None, None

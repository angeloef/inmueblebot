"""Shared helpers for v2 tools."""

import pytz

_WD = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_ARG_TZ = pytz.timezone("America/Argentina/Buenos_Aires")


def _to_arg(dt):
    """Convert a tz-aware (or naive) datetime to Argentina time for display."""
    if dt is None:
        return dt
    if dt.tzinfo is not None:
        return dt.astimezone(_ARG_TZ)
    return _ARG_TZ.localize(dt)


async def resolve_session_user(session):
    """Resolve the User for the current turn's session identity (BSUID-first → phone).

    Returns None if no identity in context or no matching user. NEVER uses a phone
    typed by the user — identity comes from the webhook (see app/core/identity.py).
    """
    from app.core.identity import get_current_contact
    from app.db.models import User
    from app.db.repository import UserRepository

    repo = UserRepository(User, session)
    c = get_current_contact() or {}
    user = None
    if c.get("bsuid"):
        user = await repo.get_by_bsuid(c["bsuid"])
    if not user and c.get("phone"):
        user = await repo.get_by_phone(c["phone"])
    return user


def fmt_appt(a) -> str:
    """One-line human description of an appointment (weekday dd/mm a las HH:MM · propiedad N).

    Converts UTC timestamps to Argentina time (ART, UTC-3) for display.
    """
    dt = _to_arg(a.start_time)
    wd = _WD[dt.weekday()]
    return f"{wd} {dt.strftime('%d/%m a las %H:%M')} (propiedad {a.property_id})"


def pick_appointment(appts, cual: str):
    """Pick one appointment from a list using a free-text hint (weekday / dd/mm / property id).

    Returns (appointment, None) if resolved, or (None, listing_text) to disambiguate.
    """
    if not appts:
        return None, "No tenés visitas agendadas."
    if len(appts) == 1:
        return appts[0], None
    cl = (cual or "").lower()
    for a in appts:
        dt = _to_arg(a.start_time)
        wd = _WD[dt.weekday()]
        if cl and (wd in cl or str(a.property_id) in cl or dt.strftime("%d/%m") in cl
                   or dt.strftime("%d") in cl.split()):
            return a, None
    lines = "\n".join(f"  {i}. {fmt_appt(a)}" for i, a in enumerate(appts, 1))
    return None, ("Tenés varias visitas agendadas. ¿Cuál?\n" + lines)

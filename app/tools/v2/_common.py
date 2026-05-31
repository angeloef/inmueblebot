"""Shared helpers for v2 tools."""

_WD = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


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
    """One-line human description of an appointment (weekday dd/mm a las HH:MM · propiedad N)."""
    wd = _WD[a.start_time.weekday()]
    return f"{wd} {a.start_time.strftime('%d/%m a las %H:%M')} (propiedad {a.property_id})"


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
        wd = _WD[a.start_time.weekday()]
        if cl and (wd in cl or str(a.property_id) in cl or a.start_time.strftime("%d/%m") in cl
                   or a.start_time.strftime("%d") in cl.split()):
            return a, None
    lines = "\n".join(f"  {i}. {fmt_appt(a)}" for i, a in enumerate(appts, 1))
    return None, ("Tenés varias visitas agendadas. ¿Cuál?\n" + lines)

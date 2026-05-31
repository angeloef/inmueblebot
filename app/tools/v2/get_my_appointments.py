"""List the current user's upcoming visits — resolved by session identity (BSUID/phone)."""

from loguru import logger

from app.db.session import async_session_factory
from app.tools.v2._common import resolve_session_user, fmt_appt


async def get_my_appointments() -> str:
    """Devuelve las visitas futuras del usuario de la sesión. Sin parámetros."""
    try:
        from app.services.appointment_service import appointment_service
        async with async_session_factory() as session:
            user = await resolve_session_user(session)
            if not user:
                return "No tenés visitas agendadas todavía. ¿Querés coordinar una?"
            appts = await appointment_service.get_user_appointments(user.id, upcoming=True)
            if not appts:
                return "No tenés visitas agendadas. ¿Querés coordinar una?"
            appts = sorted(appts, key=lambda a: a.start_time)
            lines = "\n".join(f"  • {fmt_appt(a)}" for a in appts)
            n = len(appts)
            return f"Tenés {n} visita{'s' if n != 1 else ''} agendada{'s' if n != 1 else ''}:\n{lines}"
    except Exception as e:
        logger.error(f"[get_my_appointments] {e}")
        return "Tuve un problema al consultar tus visitas. ¿Probás de nuevo?"

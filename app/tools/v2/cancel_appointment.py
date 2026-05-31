"""Cancel one of the user's upcoming visits (auto-resolve single; disambiguate if many)."""

from loguru import logger

from app.db.session import async_session_factory
from app.tools.v2._common import resolve_session_user, pick_appointment, fmt_appt


async def cancel_appointment(cual: str = "", motivo: str = "") -> str:
    """Cancela una visita del usuario.

    Args:
        cual: Pista para elegir cuál cancelar si hay varias (día, dd/mm, o id de propiedad).
        motivo: Razón opcional de la cancelación.
    """
    try:
        from app.services.appointment_service import appointment_service
        async with async_session_factory() as session:
            user = await resolve_session_user(session)
            if not user:
                return "No encontré visitas agendadas a tu nombre para cancelar."
            appts = sorted(
                await appointment_service.get_user_appointments(user.id, upcoming=True),
                key=lambda a: a.start_time,
            )
            if not appts:
                return "No tenés visitas agendadas para cancelar."
            target, disambig = pick_appointment(appts, cual)
            if disambig:
                return disambig
            desc = fmt_appt(target)
            target_id = target.id

        await appointment_service.cancel_appointment(target_id, reason=motivo or "Cancelada por el cliente")
        return f"Listo, cancelé tu visita del {desc}. ¿Querés coordinar otra?"
    except Exception as e:
        logger.error(f"[cancel_appointment] {e}")
        return f"No pude cancelar la visita: {e}"

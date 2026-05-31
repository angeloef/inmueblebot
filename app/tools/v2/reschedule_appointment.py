"""Reschedule one of the user's upcoming visits to a new day/time."""

from datetime import timedelta

from loguru import logger

from app.db.session import async_session_factory
from app.tools.v2._common import resolve_session_user, pick_appointment
from app.utils.date_parser import get_argentina_now, format_datetime_argentina


async def reschedule_appointment(dia: str = "", horario: str = "", cual: str = "") -> str:
    """Reprograma una visita del usuario a una nueva fecha/hora.

    Args:
        dia: Nuevo día (ej: "jueves", "martes 02/06", "mañana").
        horario: Nuevo horario (ej: "15:00", "a las 3 de la tarde").
        cual: Pista para elegir cuál reprogramar si hay varias (día actual / id de propiedad).
    """
    try:
        from app.services.appointment_service import appointment_service
        from app.core.hybrid.date import date_parser as hybrid_date_parser

        async with async_session_factory() as session:
            user = await resolve_session_user(session)
            if not user:
                return "No encontré visitas agendadas a tu nombre para reprogramar."
            appts = sorted(
                await appointment_service.get_user_appointments(user.id, upcoming=True),
                key=lambda a: a.start_time,
            )
            if not appts:
                return "No tenés ninguna visita agendada para cambiar. ¿Querés coordinar una nueva?"
            target, disambig = pick_appointment(appts, cual)
            if disambig:
                return disambig
            target_id = target.id
            old_time = target.start_time

        if not dia and not horario:
            return "¿Para qué día y horario querés reprogramarla?"

        now = get_argentina_now()
        # If only the time changed, keep the original day.
        from app.utils.date_parser import format_datetime_argentina  # noqa
        combined = f"{dia} {horario}".strip()
        res = await hybrid_date_parser.parse(
            combined, {"date_str": dia, "time_str": horario, "reference_dt": now}
        )
        new_dt = res.value
        if not new_dt:
            return f"No pude entender la nueva fecha '{combined}'. Decime día y hora, ej: 'jueves 15:00'."
        if new_dt <= now:
            new_dt = new_dt + timedelta(days=7)
        if new_dt.weekday() == 6 or not (9 <= new_dt.hour < 18):
            return ("Ese horario está fuera de nuestra atención (lunes a sábado, 9:00 a 18:00 hs). "
                    "¿Qué otro día y hora te sirve?")

        new_appt = await appointment_service.reschedule_appointment(target_id, new_dt)
        return (f"Listo, reprogramé tu visita para el {format_datetime_argentina(new_appt.start_time)}. "
                f"Un agente te va a contactar para confirmar.")
    except Exception as e:
        logger.error(f"[reschedule_appointment] {e}")
        return f"No pude reprogramar la visita: {e}"

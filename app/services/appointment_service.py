"""
Servicio de Citas y Turnos.
Maneja la creación, modificación y cancelación de citas para visitas a propiedades.
"""
from datetime import datetime, timezone as tz, timedelta
from uuid import UUID, uuid4
from typing import Optional
from loguru import logger
import pytz

from app.db.models import Appointment
from app.db.models import User
from app.db.models import Property
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session_factory

from app.services.calendar_service import calendar_service


class AppointmentService:
    """
    Servicio asíncrono para gestionar citas y turnos de visitas.
    
    Funcionalidades:
    - Crear citas para visitas a propiedades
    - Obtener citas por ID o usuario
    - Reprogramar citas
    - Cancelar citas
    - Prevenir doble reserva en mismo horario
    - Actualizar lead_score al agendar
    
    TODO: Integración futura con Google Calendar
    """
    
    DEFAULT_VISIT_DURATION = timedelta(hours=1)
    
    def __init__(self):
        pass
    
    def _get_session(self) -> AsyncSession:
        return async_session_factory()
    
    async def create_appointment(
        self,
        user_id: UUID,
        property_id: int,
        start_time: datetime,
        type: str = "visit",
        notes: str = None,
        user_phone: str = None,
        check_calendar: bool = True
    ) -> dict:
        """
        Crea una nueva cita para visitar una propiedad.
        
        Returns dict with:
        - success: bool
        - message: str (confirmation or error)
        - appointment: Appointment if success
        - confirmed_datetime: str (ISO format) if success
        - suggested_times: list of dicts if busy {datetime, formatted}
        """
        db = self._get_session()
        try:
            start_time = self._ensure_timezone(start_time)
            
            if start_time < datetime.now(tz.utc):
                return {
                    "success": False,
                    "message": "La fecha y hora ya pasaron. Por favor selecciona una fecha futura.",
                    "suggested_times": []
                }
            
            # Check local database conflict
            conflict = await self._check_conflict(db, property_id, start_time)
            if conflict:
                logger.warning(f"[Create Appointment] Slot occupied: property={property_id}, time={start_time}")
                suggestions = await self._get_suggested_times(property_id, start_time, db)
                return {
                    "success": False,
                    "message": "Ese horario ya está ocupado. ¿Te alguna de estas opciones?",
                    "suggested_times": suggestions
                }
            
            # Check Google Calendar availability if configured
            calendar_event_id = None
            logger.info(f"[Create Appointment] check_calendar={check_calendar}, calendar_service.is_configured={calendar_service.is_configured}")
            if check_calendar and not calendar_service.is_configured:
                logger.warning("[Appointment] ⚠️ Google Calendar NOT configured — appointment will be DB-only (no calendar sync)")
            if check_calendar and calendar_service.is_configured:
                result = await db.execute(select(Property).where(Property.id == property_id))
                property_obj = result.scalar_one_or_none()
                property_title = property_obj.title if property_obj else f"Propiedad {property_id}"
                
                cal_check = await calendar_service.check_availability(
                    property_id=property_id,
                    date_str=start_time.strftime("%Y-%m-%d"),
                    time_str=start_time.strftime("%H:%M"),
                    duration_hours=1
                )
                logger.info(f"[Create Appointment] Calendar check: available={cal_check.get('available')}, error={cal_check.get('error')}")
                
                if not cal_check.get("available", True):
                    suggestions = await self._get_suggested_times(property_id, start_time, db)
                    return {
                        "success": False,
                        "message": f"Horario ocupado en Google Calendar por otro evento.",
                        "suggested_times": suggestions
                    }
                
                # Create Google Calendar event
                end_time = start_time + self.DEFAULT_VISIT_DURATION
                cal_result = await calendar_service.create_visit_event(
                    user_phone=user_phone or "Unknown",
                    property_id=property_id,
                    property_title=property_title,
                    start_time=start_time,
                    end_time=end_time,
                    notes=notes
                )
                
                if cal_result.get("success"):
                    calendar_event_id = cal_result.get("event_id")
                    logger.info(f"[Appointment] Created Google Calendar event: {calendar_event_id}")
            
            end_time = start_time + self.DEFAULT_VISIT_DURATION
            
            appointment = Appointment(
                id=uuid4(),
                user_id=user_id,
                property_id=property_id,
                start_time=start_time,
                end_time=end_time,
                type=type,
                status="confirmed",
                notes=notes,
                calendar_event_id=calendar_event_id
            )
            
            db.add(appointment)
            await db.commit()
            await db.refresh(appointment)
            
            await self._update_user_score(user_id, db)
            
            logger.info(f"Cita creada: {appointment.id} calendar_event_id={calendar_event_id}")
            
            calendar_note = ""
            if check_calendar and not calendar_service.is_configured:
                calendar_note = "\n\n⚠️ Nota: La sincronización con el calendario no está disponible. La cita se registró en nuestro sistema."
            
            return {
                "success": True,
                "message": f"Cita agendada exitosamente{calendar_note}",
                "appointment": appointment,
                "confirmed_datetime": start_time.isoformat()
            }
        except Exception as e:
            await db.rollback()
            logger.error(f"Error al crear cita: {e}")
            return {
                "success": False,
                "message": str(e),
                "suggested_times": []
            }
        finally:
            await db.close()
    
    async def _get_suggested_times(
        self,
        property_id,
        requested_time: datetime,
        db: AsyncSession,
        num_suggestions: int = 3
    ) -> list:
        """Generate suggested alternative times (timezone-aware)."""
        suggestions = []
        arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
        
        # Ensure requested_time is timezone-aware
        if requested_time.tzinfo is None:
            requested_time = arg_tz.localize(requested_time)
        
        # Try: same day -1 hour, +1 hour, next day same hour
        test_times_local = [
            requested_time - timedelta(hours=1),
            requested_time + timedelta(hours=1),
            requested_time + timedelta(days=1),
        ]
        
        now = datetime.now(arg_tz)
        
        for test_time in test_times_local[:num_suggestions]:
            # Skip if in the past (compare in Argentina timezone)
            if test_time < now:
                continue
            
            # Check local DB conflict
            conflict = await self._check_conflict(db, property_id, test_time)
            if conflict:
                continue
            
            # Check if reasonable hours (7am-8pm Argentina)
            if test_time.hour < 7 or test_time.hour > 20:
                continue
            
            suggestions.append({
                "datetime": test_time.isoformat(),
                "formatted": test_time.strftime("%d/%m/%Y a las %H:%M")
            })
        
        return suggestions
    
    async def get_appointment(self, appointment_id: UUID) -> Optional[Appointment]:
        """Obtiene una cita por su ID."""
        db: AsyncSession = self._get_session()
        try:
            result = await db.execute(
                select(Appointment).where(Appointment.id == appointment_id)
            )
            return result.scalar_one_or_none()
        finally:
            await db.close()
    
    async def reschedule_appointment(
        self,
        appointment_id: UUID,
        new_start_time: datetime,
        sync_calendar: bool = True
    ) -> Appointment:
        """
        Reprograma una cita: cancela la vieja y crea una nueva.
        
        Args:
            appointment_id: ID de la cita a reprogramar
            new_start_time: Nueva fecha y hora
            sync_calendar: Sincronizar con Google Calendar
        
        Returns:
            Nueva cita creada
        
        Raises:
            ValueError: Si la cita no existe, la fecha ya pasó, o hay conflicto
        """
        db: AsyncSession = self._get_session()
        
        try:
            # 1. Fetch old appointment
            result = await db.execute(
                select(Appointment).where(Appointment.id == appointment_id)
            )
            old_appointment = result.scalar_one_or_none()
            
            if not old_appointment:
                raise ValueError("No encontré esa cita. ¿Podrías verificar el ID?")
            
            if old_appointment.status == "cancelled":
                raise ValueError("No se puede reprogramar una cita cancelada.")
            
            new_start_time = self._ensure_timezone(new_start_time)
            
            if new_start_time < datetime.now(tz.utc):
                raise ValueError("La nueva fecha y hora ya pasaron. Por favor selecciona una fecha futura.")
            
            conflict = await self._check_conflict(
                db, old_appointment.property_id, new_start_time
            )
            if conflict:
                raise ValueError("Ya existe otra cita en ese horario. Por favor elige otro momento.")
            
            # 2. Cancel old appointment
            old_appointment.status = "cancelled"
            old_appointment.updated_at = datetime.now(tz.utc)
            logger.info(f"[Appointment] Marked old appointment {old_appointment.id} as cancelled for reschedule")
            
            # 3. Cancel old Google Calendar event
            old_calendar_event_id = old_appointment.calendar_event_id
            if sync_calendar and calendar_service.is_configured and old_calendar_event_id:
                cal_cancel = await calendar_service.cancel_visit(
                    event_id=old_calendar_event_id,
                    reason="Reprogramada por el cliente"
                )
                if cal_cancel.get("success"):
                    logger.info(f"[Appointment] Cancelled old Google Calendar event: {old_calendar_event_id}")
                else:
                    logger.warning(f"[Appointment] Failed to cancel old calendar event: {cal_cancel.get('error')}")
            
            # 4. Create new appointment
            new_end_time = new_start_time + self.DEFAULT_VISIT_DURATION
            
            new_appointment = Appointment(
                id=uuid4(),
                user_id=old_appointment.user_id,
                property_id=old_appointment.property_id,
                start_time=new_start_time,
                end_time=new_end_time,
                type=old_appointment.type,
                status="confirmed",
                notes=old_appointment.notes,
                calendar_event_id=None,
            )
            db.add(new_appointment)
            await db.flush()  # Ensure new_appointment.id is available
            
            # 5. Create new Google Calendar event
            new_calendar_event_id = None
            if sync_calendar and calendar_service.is_configured:
                try:
                    prop_result = await db.execute(
                        select(Property).where(Property.id == old_appointment.property_id)
                    )
                    property_obj = prop_result.scalar_one_or_none()
                    property_title = property_obj.title if property_obj else f"Propiedad {old_appointment.property_id}"
                    
                    cal_result = await calendar_service.create_visit_event(
                        user_phone="Reprogramación",
                        property_id=old_appointment.property_id,
                        property_title=property_title,
                        start_time=new_start_time,
                        end_time=new_end_time,
                        notes=f"Cita reprogramada desde la original {old_appointment.id}"
                    )
                    
                    if cal_result.get("success"):
                        new_calendar_event_id = cal_result.get("event_id")
                        new_appointment.calendar_event_id = new_calendar_event_id
                        logger.info(f"[Appointment] Created new Google Calendar event: {new_calendar_event_id}")
                    else:
                        logger.warning(f"[Appointment] Failed to create new calendar event: {cal_result.get('error')}")
                except Exception as e:
                    logger.warning(f"[Appointment] Error creating new calendar event: {e}")
            
            await db.commit()
            await db.refresh(new_appointment)
            
            await self._update_user_score(old_appointment.user_id, db)
            
            logger.info(f"Cita reprogramada: {old_appointment.id} -> nueva {new_appointment.id} para {new_start_time}")
            
            return new_appointment
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error al reprogramar cita: {e}")
            raise
        finally:
            await db.close()
    
    async def cancel_appointment(
        self,
        appointment_id: UUID,
        reason: str = None,
        sync_calendar: bool = True
    ) -> bool:
        """
        Cancela una cita existente.
        
        Args:
            appointment_id: ID de la cita a cancelar
            reason: Razón opcional de cancelación
            sync_calendar: Sincronizar con Google Calendar
        
        Returns:
            True si se canceló correctamente
        
        Raises:
            ValueError: Si la cita no existe o ya está cancelada
        """
        db: AsyncSession = self._get_session()
        
        try:
            result = await db.execute(
                select(Appointment).where(Appointment.id == appointment_id)
            )
            appointment = result.scalar_one_or_none()
            
            if not appointment:
                raise ValueError("No encontré esa cita. ¿Podrías verificar el ID?")
            
            if appointment.status == "cancelled":
                raise ValueError("Esta cita ya está cancelada.")
            
            # Sync with Google Calendar if configured
            if sync_calendar and calendar_service.is_configured and appointment.calendar_event_id:
                cal_result = await calendar_service.cancel_visit(
                    event_id=appointment.calendar_event_id,
                    reason=reason or "Cancelada por el cliente"
                )
                
                if cal_result.get("success"):
                    logger.info(f"[Appointment] Cancelled Google Calendar event: {appointment.calendar_event_id}")
                else:
                    logger.warning(f"[Appointment] Failed to cancel calendar event: {cal_result.get('error')}")
            
            appointment.status = "cancelled"
            appointment.notes = f"{appointment.notes}\nCancelación: {reason}" if reason else appointment.notes
            appointment.updated_at = datetime.now(tz.utc)
            
            await db.commit()
            
            logger.info(f"Cita cancelada: {appointment_id}")
            
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Error al cancelar cita: {e}")
            raise
        finally:
            await db.close()
    
    async def get_user_appointments(
        self,
        user_id: UUID,
        upcoming: bool = True
    ) -> list[Appointment]:
        """
        Obtiene las citas de un usuario.
        
        Args:
            user_id: ID del usuario
            upcoming: Si True, solo retorna citas futuras
        
        Returns:
            Lista de citas
        """
        db: AsyncSession = self._get_session()
        
        try:
            query = select(Appointment).where(Appointment.user_id == user_id)
            
            if upcoming:
                query = query.where(
                    and_(
                        Appointment.start_time >= datetime.now(tz.utc),
                        Appointment.status == "confirmed"
                    )
                )
            else:
                query = query.order_by(Appointment.start_time.desc())
            
            result = await db.execute(query)
            return list(result.scalars().all())
            
        finally:
            await db.close()
    
    async def get_upcoming_appointments(self, user_id: UUID, limit: int = 3) -> list[Appointment]:
        """Obtiene las próximas citas agendadas o confirmadas de un usuario."""
        db = self._get_session()
        try:
            query = (
                select(Appointment)
                .where(Appointment.user_id == user_id)
                .where(Appointment.start_time > datetime.now(tz.utc))
                .where(Appointment.status.in_(["scheduled", "confirmed"]))
                .order_by(Appointment.start_time.asc())
                .limit(limit)
            )
            result = await db.execute(query)
            return list(result.scalars().all())
        finally:
            await db.close()
    
    async def _check_conflict(
        self,
        db: AsyncSession,
        property_id,
        start_time: datetime,
        exclude_appointment_id: UUID = None
    ) -> Optional[Appointment]:
        """Verifica si hay conflicto de horario (timezone-aware)."""
        # Ensure start_time is in UTC for comparison
        if start_time.tzinfo is not None:
            start_time_utc = start_time.astimezone(tz.utc)
        else:
            # If naive, assume it's Argentina time and convert
            arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
            start_time_utc = arg_tz.localize(start_time).astimezone(tz.utc)
        
        end_time_utc = start_time_utc + self.DEFAULT_VISIT_DURATION
        
        # Handle both int and UUID property_id
        prop_id = property_id if isinstance(property_id, int) else int(property_id)
        
        logger.info(f"[Conflict Check] property={prop_id}, start={start_time_utc} to {end_time_utc} (UTC)")
        
        query = select(Appointment).where(
            and_(
                Appointment.property_id == prop_id,
                Appointment.status == "confirmed",
                Appointment.start_time < end_time_utc,
                Appointment.end_time > start_time_utc
            )
        )
        
        if exclude_appointment_id:
            query = query.where(Appointment.id != exclude_appointment_id)
        
        result = await db.execute(query)
        conflict = result.scalar_one_or_none()
        
        if conflict:
            logger.info(f"[Conflict Check] CONFLICT found: {conflict.start_time} to {conflict.end_time}")
        
        return conflict
    
    async def _update_user_score(self, user_id: UUID, db: AsyncSession) -> None:
        """Actualiza el lead_score del usuario (+30 puntos por cita agendada)."""
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if user:
                user.lead_score = (user.lead_score or 0) + 30
                user.last_interaction = datetime.now(tz.utc)
                await db.commit()
                logger.info(f"Lead score actualizado para usuario {user_id}: +30 puntos")
        except Exception as e:
            logger.error(f"Error actualizando lead score: {e}")
    
    def _ensure_timezone(self, dt: datetime) -> datetime:
        """Asegura que el datetime tenga timezone.
        
        Los datetimes naive se asumen como hora de Argentina (UTC-3),
        consistente con _check_conflict().
        """
        if dt.tzinfo is None:
            arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
            return arg_tz.localize(dt)
        return dt


def format_appointment_confirmation(appointment: Appointment, property_title: str = None, action_type: str = 'new') -> str:
    """
    Formatea un mensaje de confirmación de cita para WhatsApp.
    
    Args:
        appointment: Cita a formatear
        property_title: Título de la propiedad (opcional)
        action_type: 'new' para cita nueva, 'reschedule' para reprogramación
    
    Returns:
        Mensaje formateado listo para enviar (incluye metadata estructurada para el LLM)
    """
    start = appointment.start_time
    
    # Convert from UTC (DB storage) to Argentina timezone for display
    import pytz
    arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')
    if start.tzinfo is not None:
        start_local = start.astimezone(arg_tz)
    else:
        start_local = arg_tz.localize(start)
    
    date_str = start_local.strftime("%d/%m/%Y")
    time_str = start_local.strftime("%H:%M")
    iso_datetime = start_local.strftime("%Y-%m-%d %H:%M")
    
    type_labels = {
        "visit": "visita",
        "signing": "firma de contrato",
        "meeting": "reunión"
    }
    type_label = type_labels.get(appointment.type, "cita")
    
    header = "📅 *¡Cita Reprogramada!*" if action_type == 'reschedule' else "📅 *¡Cita Agendada!*"
    
    lines = [
        header,
        "",
        f"✅ *Tipo:* {type_label}",
        f"📆 *Fecha:* {date_str}",
        f"⏰ *Hora:* {time_str}",
    ]
    
    if property_title:
        lines.append(f"🏠 *Propiedad:* {property_title}")
    
    lines.extend([
        "",
        "📝 *Nota:* Un agente te contactará para confirmar los detalles.",
        "",
        "¿Necesitas hacer algún cambio? Solo dime."
    ])
    
    message = "\n".join(lines)
    
    # Append structured metadata for LLM consumption (hidden from user)
    # Format: <!--CONFIRMED:{datetime}--> where datetime is YYYY-MM-DD HH:MM
    message += f"\n\n<!--CONFIRMED:{iso_datetime}-->"
    
    return message


def format_appointment_list(appointments: list[Appointment], property_titles: dict = None) -> str:
    """
    Formatea una lista de citas para WhatsApp.
    
    Args:
        appointments: Lista de citas
        property_titles: Dict {property_id: title} opcional
    
    Returns:
        Mensaje formateado
    """
    if not appointments:
        return "No tienes citas programadas upcoming."
    
    lines = ["📅 *Tus próximas citas:*", ""]
    arg_tz = pytz.timezone('America/Argentina/Buenos_Aires')

    for i, apt in enumerate(appointments, 1):
        start = apt.start_time
        # Convert from UTC (DB storage) to Argentina timezone for display
        if start.tzinfo is not None:
            start_local = start.astimezone(arg_tz)
        else:
            start_local = arg_tz.localize(start)
        date_str = start_local.strftime("%d/%m")
        time_str = start_local.strftime("%H:%M")

        prop_title = "Propiedad"
        if property_titles and apt.property_id in property_titles:
            prop_title = property_titles[apt.property_id]

        type_label = "visita" if apt.type == "visit" else apt.type

        lines.append(f"{i}. 📆 {date_str} a las {time_str} — {prop_title} ({type_label})")
        lines.append(f"   🔍 ID: `{apt.id}`")
        lines.append("")

    return "\n".join(lines)


appointment_service = AppointmentService()
"""
Notification Service.
Crea y gestiona notificaciones para el dashboard del agente inmobiliario.
Usa la tabla `notifications` en PostgreSQL (creada vía auto-migración en admin.py).
"""
from loguru import logger
from typing import Optional


# ── Tipos de notificación ─────────────────────────────────────────────────────

class NotifType:
    VISIT_SCHEDULED    = "visit_scheduled"
    VISIT_RESCHEDULED  = "visit_rescheduled"
    VISIT_CANCELLED    = "visit_cancelled"
    CALL_SCHEDULED     = "call_scheduled"
    HANDOFF_REQUESTED  = "handoff_requested"
    NEW_LEAD           = "new_lead"
    LEAD_QUALIFIED     = "lead_qualified"
    BOT_ERROR          = "bot_error"


class NotificationService:
    """
    Servicio de notificaciones del dashboard.
    Todos los métodos son async y usan async_session_factory.
    Falla silenciosamente para no interrumpir el flujo del bot.
    """

    async def create(
        self,
        type: str,
        title: str,
        body: str = "",
        phone: Optional[str] = None,
        metadata: dict = None,
    ) -> bool:
        """Inserta una notificación en la tabla `notifications`."""
        try:
            from app.db.session import async_session_factory
            from sqlalchemy import text
            import json

            meta_json = json.dumps(metadata or {})

            async with async_session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO notifications (type, title, body, phone, metadata)
                        VALUES (:type, :title, :body, :phone, CAST(:metadata AS jsonb))
                    """),
                    {
                        "type": type,
                        "title": title,
                        "body": body or "",
                        "phone": phone,
                        "metadata": meta_json,
                    }
                )
                await session.commit()

            logger.info(f"[Notif] {type}: {title}")
            return True

        except Exception as e:
            logger.warning(f"[Notif] No se pudo crear notificación '{type}': {e}")
            return False

    # ── Helpers por tipo ──────────────────────────────────────────────────────

    async def visit_scheduled(self, phone: str, property_title: str, datetime_str: str, property_id=None, event_id=None):
        client = f"...{phone[-8:]}" if phone else "?"
        await self.create(
            type=NotifType.VISIT_SCHEDULED,
            title="Nueva visita agendada",
            body=f"{property_title} · {datetime_str} · Cliente {client}",
            phone=phone,
            metadata={"property_id": str(property_id) if property_id else None, "datetime": datetime_str, "event_id": str(event_id) if event_id else None},
        )

    async def visit_rescheduled(self, phone: str, property_title: str, datetime_str: str, property_id=None, event_id=None):
        client = f"...{phone[-8:]}" if phone else "?"
        await self.create(
            type=NotifType.VISIT_RESCHEDULED,
            title="Visita reprogramada",
            body=f"{property_title} · nueva fecha {datetime_str} · Cliente {client}",
            phone=phone,
            metadata={"property_id": str(property_id) if property_id else None, "datetime": datetime_str, "event_id": str(event_id) if event_id else None},
        )

    async def visit_cancelled(self, phone: str, property_title: str, reason: str = "", property_id=None, event_id=None):
        client = f"...{phone[-8:]}" if phone else "?"
        await self.create(
            type=NotifType.VISIT_CANCELLED,
            title="Visita cancelada",
            body=f"{property_title} · Cliente {client}" + (f" · {reason}" if reason else ""),
            phone=phone,
            metadata={"property_id": str(property_id) if property_id else None, "reason": reason, "event_id": str(event_id) if event_id else None},
        )

    async def call_scheduled(self, phone: str, datetime_str: str, event_id=None):
        client = f"...{phone[-8:]}" if phone else "?"
        await self.create(
            type=NotifType.CALL_SCHEDULED,
            title="Nueva llamada agendada",
            body=f"{datetime_str} · Cliente {client}",
            phone=phone,
            metadata={"datetime": datetime_str, "event_id": str(event_id) if event_id else None},
        )

    async def handoff_requested(self, phone: str, reason: str = ""):
        client = f"...{phone[-8:]}" if phone else "?"
        await self.create(
            type=NotifType.HANDOFF_REQUESTED,
            title="Cliente solicita atención humana",
            body=f"Cliente {client}" + (f" · {reason}" if reason else ""),
            phone=phone,
            metadata={"reason": reason},
        )

    async def new_lead(self, phone: str):
        client = f"...{phone[-8:]}" if phone else "?"
        await self.create(
            type=NotifType.NEW_LEAD,
            title="Nuevo cliente registrado",
            body=f"Primer mensaje de {client}",
            phone=phone,
        )

    async def lead_qualified(self, phone: str, score: int, name: str = ""):
        client = name if name else (f"...{phone[-8:]}" if phone else "?")
        await self.create(
            type=NotifType.LEAD_QUALIFIED,
            title="Lead calificado",
            body=f"{client} · score {score}",
            phone=phone,
            metadata={"score": score},
        )

    async def bot_error(self, phone: str, error_summary: str):
        client = f"...{phone[-8:]}" if phone else "?"
        await self.create(
            type=NotifType.BOT_ERROR,
            title="Error del bot",
            body=f"Cliente {client} · {error_summary[:120]}",
            phone=phone,
            metadata={"error": error_summary},
        )


notification_service = NotificationService()

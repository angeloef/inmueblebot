"""
Helper para registrar eventos en ``activity_log``.

Regla de oro: **nunca** romper la operación principal. Si el log falla (tabla
ausente, DB intermitente), se loguea con ``logging`` y se sigue. El commit lo hace
el endpoint (este helper solo agrega la fila a la sesión / la inserta en la misma
transacción).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Acciones válidas — mantener en sync con el frontend (api.js ACTIVITY_META).
VALID_ACTIONS = frozenset(
    {
        "status_changed",
        "property_edited",
        "reassigned",
        "relation_linked",
        "relation_changed",
        "relation_unlinked",
    }
)


def log_activity(
    db: Session,
    *,
    tenant_id: UUID | str | None,
    entity_type: str,
    entity_id: str | int,
    action: str,
    actor: str = "dashboard",
    payload: dict[str, Any] | None = None,
) -> None:
    """Agrega un evento a la sesión sync (sin commitear). No levanta excepciones.

    El endpoint que llama es el responsable del ``db.commit()`` — así el log vive en
    la misma transacción que la operación de negocio.
    """
    if action not in VALID_ACTIONS:
        logger.warning("log_activity: acción desconocida=%s, se omite", action)
        return
    try:
        from app.db.models import ActivityLog

        db.add(
            ActivityLog(
                tenant_id=str(tenant_id) if tenant_id else None,
                entity_type=entity_type,
                entity_id=str(entity_id),
                action=action,
                actor=actor,
                payload=payload or {},
            )
        )
        db.flush()
    except Exception as exc:  # noqa: BLE001 — el log jamás debe abortar la operación
        logger.warning(
            "log_activity falló (entity=%s:%s action=%s): %s", entity_type, entity_id, action, exc
        )


async def log_activity_async(
    session: AsyncSession,
    *,
    tenant_id: UUID | str | None,
    entity_type: str,
    entity_id: str | int,
    action: str,
    actor: str = "dashboard",
    payload: dict[str, Any] | None = None,
) -> None:
    """Variante para endpoints async (sesión AsyncSession + raw SQL).

    Inserta en la misma transacción; el commit lo hace el endpoint. No levanta.
    """
    if action not in VALID_ACTIONS:
        logger.warning("log_activity_async: acción desconocida=%s, se omite", action)
        return
    import json

    try:
        await session.execute(
            text(
                "INSERT INTO activity_log "
                "(id, tenant_id, entity_type, entity_id, action, actor, payload, created_at) "
                "VALUES (gen_random_uuid(), :tenant_id, :entity_type, :entity_id, "
                ":action, :actor, CAST(:payload AS JSONB), NOW())"
            ),
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "action": action,
                "actor": actor,
                "payload": json.dumps(payload or {}),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "log_activity_async falló (entity=%s:%s action=%s): %s",
            entity_type,
            entity_id,
            action,
            exc,
        )

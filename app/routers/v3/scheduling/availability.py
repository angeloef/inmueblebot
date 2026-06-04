"""Thin availability wrapper over appointment_service.check_slot_availability.

Does NOT reimplement conflict logic. Delegates to the existing service and
remaps the response shape: suggested_times → suggestions.

Cross-tenant safety: RLS ContextVar is already set by the engine (step 0)
before this is ever called.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger


async def check_availability(
    property_id: int,
    proposed_dt: datetime,
    tenant_id=None,  # unused here — RLS is set via ContextVar by engine step 0
) -> dict:
    """Check whether a property/time slot is available.

    Delegates to appointment_service.check_slot_availability(property_id, proposed_dt)
    which returns {"available": bool, "suggested_times": [...]}.
    We remap suggested_times → suggestions.

    Fail-open: on any exception returns {"available": True, "suggestions": []}.
    """
    try:
        from app.services.appointment_service import appointment_service

        result = await appointment_service.check_slot_availability(
            property_id=property_id,
            start_time=proposed_dt,
        )
        return {
            "available": bool(result.get("available", True)),
            "suggestions": result.get("suggested_times", []),
        }
    except Exception as exc:
        logger.debug("[scheduling.availability] check_availability fail-open: {}", exc)
        return {"available": True, "suggestions": []}

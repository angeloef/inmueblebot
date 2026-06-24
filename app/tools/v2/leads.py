"""Lead capture + qualification tools (KA4).

Two thin CRUD tools over the existing ``user_episodes`` table — no new table.
A lead is a per-tenant durable record of a customer's interest, keyed by a
deterministic session_id ``lead:{identity}`` so re-capturing the same contact
*updates* the row instead of duplicating it (idempotent).

ponytail: leads ride on UserEpisode (it already has tenant_id + phone +
search_criteria + intent_outcome). If the dashboard ever needs a real lead
inbox with its own columns/filters, promote to a dedicated ``leads`` table —
the upgrade path is a model + migration, the tool surface stays the same.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from app.core.identity import get_current_contact, get_identity_key
from app.core.tenancy import resolve_tenant_id
from app.db.models.user_episode import UserEpisode
from app.db.session import async_session_factory

_LEAD_PREFIX = "lead:"


def _identity() -> tuple[str | None, str | None]:
    """(phone, bsuid) from the session context — never a number typed in chat."""
    c = get_current_contact() or {}
    return c.get("phone"), c.get("bsuid")


def score_lead(presupuesto_max: float, zona: str, urgencia: str, tipo: str) -> tuple[float, str]:
    """Heuristic lead score in [0,1] + tier ('hot'|'warm'|'cold').

    More signal = warmer: a concrete budget, a target zone, a property type and
    explicit urgency each push the score up. Pure heuristic — no LLM call.
    """
    score = 0.0
    if presupuesto_max and presupuesto_max > 0:
        score += 0.3
    if (zona or "").strip():
        score += 0.2
    if (tipo or "").strip():
        score += 0.2
    u = (urgencia or "").strip().lower()
    if any(w in u for w in ("alta", "urgente", "ya", "inmediat", "esta semana", "hoy")):
        score += 0.3
    elif any(w in u for w in ("media", "pronto", "este mes")):
        score += 0.15
    elif u:
        score += 0.05
    score = min(round(score, 2), 1.0)
    tier = "hot" if score >= 0.7 else "warm" if score >= 0.4 else "cold"
    return score, tier


async def _upsert_lead(payload: dict, summary: str, last_tool: str, intent_outcome: str) -> bool:
    """Insert or update the tenant-scoped lead row. Returns True on persist.

    tenant_id is set EXPLICITLY — RLS WITH CHECK rejects NULL (see
    tenant-id-insert-rls-trap). Without an identity we can't key the lead, so we
    skip persistence rather than write an unkeyable row.
    """
    phone, bsuid = _identity()
    identity = get_identity_key() or bsuid or phone
    if not identity:
        logger.warning("[leads] no session identity — lead not persisted")
        return False

    session_id = f"{_LEAD_PREFIX}{identity}"
    tenant_id = resolve_tenant_id()
    try:
        async with async_session_factory() as session:
            existing = (await session.execute(
                select(UserEpisode).where(
                    UserEpisode.tenant_id == tenant_id,
                    UserEpisode.session_id == session_id,
                )
            )).scalar_one_or_none()

            if existing is not None:
                merged = {**(existing.search_criteria or {}), **payload}
                existing.search_criteria = merged
                existing.summary = summary or existing.summary
                existing.last_tool_called = last_tool
                existing.intent_outcome = intent_outcome
            else:
                session.add(UserEpisode(
                    tenant_id=tenant_id,
                    phone=(phone or bsuid or identity)[:30],
                    bsuid=bsuid,
                    session_id=session_id,
                    summary=summary,
                    turn_count=0,
                    last_tool_called=last_tool,
                    search_criteria=payload,
                    intent_outcome=intent_outcome,
                ))
            await session.commit()
        return True
    except Exception as exc:
        # Non-fatal: a failed lead write must not break the customer's turn.
        logger.warning("[leads] could not persist lead: {}", str(exc))
        return False


async def capture_lead(
    nombre: str = "",
    operation: str = "",
    tipo: str = "",
    zona: str = "",
    presupuesto_max: float = 0,
    notas: str = "",
) -> str:
    """Register an interested customer as a lead (tenant-scoped, idempotent)."""
    payload = {
        "nombre": nombre,
        "operation": operation,
        "tipo": tipo,
        "zona": zona,
        "presupuesto_max": presupuesto_max,
        "notas": notas,
    }
    parts = [p for p in (tipo, f"en {zona}" if zona else "", operation) if p]
    summary = f"Lead: {nombre or 'contacto'} busca " + (" ".join(parts) or "propiedad")
    ok = await _upsert_lead(payload, summary, "capture_lead", "lead_new")
    if not ok:
        return "Anotado tu interés. Un asesor te va a contactar."
    return f"Listo, registré tu interés{(' , ' + nombre) if nombre else ''}. Un asesor de la inmobiliaria te va a contactar."


async def qualify_lead(
    presupuesto_max: float = 0,
    zona: str = "",
    urgencia: str = "",
    tipo: str = "",
) -> str:
    """Score a lead by budget/zone/urgency/type and persist the tier."""
    score, tier = score_lead(presupuesto_max, zona, urgencia, tipo)
    payload = {
        "presupuesto_max": presupuesto_max,
        "zona": zona,
        "urgencia": urgencia,
        "tipo": tipo,
        "lead_score": score,
        "lead_tier": tier,
    }
    summary = f"Lead {tier} (score {score})"
    await _upsert_lead(payload, summary, "qualify_lead", f"lead_{tier}")
    # Internal status string the engine can use; not necessarily shown verbatim.
    return f"Lead calificado: {tier} (score {score})."

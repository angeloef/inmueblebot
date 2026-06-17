"""plans.py — Catálogo central de planes SaaS (fuente única de verdad).

No dispersar ``if plan == 'profesional'`` por el código.
Toda decisión sobre qué incluye un tier se resuelve acá.

Tier order: basico < profesional < enterprise
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ── Tipos ─────────────────────────────────────────────────────────────────────

TierName = Literal["basico", "profesional", "enterprise"]

# Flags de feature — cada nombre es la clave de gating usada en require_plan().
Feature = Literal[
    "cobranzas",        # Gestión de alquileres + IPC (Pro+)
    "website",          # Sitio web con catálogo (Pro+)
    "weekly_report",    # Reporte semanal por WhatsApp (Pro+)
    "cold_leads",       # Seguimiento de leads fríos (Pro+)
    "visit_reminder",   # Recordatorio de visita 24h (Pro+)
    "multi_branch",     # Multi-sucursal (Enterprise)
    "documents",        # Documentos vinculados a clientes (Enterprise)
    "exec_reports",     # Reportes ejecutivos mensuales (Enterprise)
    "exports",          # Exportación CSV de datos (Enterprise)
    "api",              # API / integraciones custom (Enterprise)
]

_TIER_ORDER: dict[TierName, int] = {
    "basico": 0,
    "profesional": 1,
    "enterprise": 2,
}


@dataclass(frozen=True)
class PlanLimits:
    users: int | None          # None = ilimitado
    conversations_per_month: int | None
    properties: int | None


@dataclass(frozen=True)
class Plan:
    name: TierName
    display_name: str
    price_ars_monthly: float
    price_ars_annual_monthly: float   # precio mensual si paga anual (-20%)
    limits: PlanLimits
    features: frozenset[Feature]
    self_serve: bool                  # False = Enterprise (CTA ventas)

    def includes_feature(self, feature: Feature) -> bool:
        return feature in self.features

    def meets_min_tier(self, min_tier: TierName) -> bool:
        return _TIER_ORDER[self.name] >= _TIER_ORDER[min_tier]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "price_ars_monthly": self.price_ars_monthly,
            "price_ars_annual_monthly": self.price_ars_annual_monthly,
            "limits": {
                "users": self.limits.users,
                "conversations_per_month": self.limits.conversations_per_month,
                "properties": self.limits.properties,
            },
            "features": sorted(self.features),
            "self_serve": self.self_serve,
        }


# ── Catálogo ──────────────────────────────────────────────────────────────────

_PRO_FEATURES: frozenset[Feature] = frozenset({
    "cobranzas",
    "website",
    "weekly_report",
    "cold_leads",
    "visit_reminder",
})

_ENTERPRISE_FEATURES: frozenset[Feature] = _PRO_FEATURES | frozenset({
    "multi_branch",
    "documents",
    "exec_reports",
    "exports",
    "api",
})

CATALOG: dict[TierName, Plan] = {
    "basico": Plan(
        name="basico",
        display_name="Básico",
        price_ars_monthly=39_900.0,
        price_ars_annual_monthly=31_900.0,
        limits=PlanLimits(users=1, conversations_per_month=250, properties=50),
        features=frozenset(),
        self_serve=True,
    ),
    "profesional": Plan(
        name="profesional",
        display_name="Profesional",
        price_ars_monthly=84_900.0,
        price_ars_annual_monthly=67_900.0,
        limits=PlanLimits(users=5, conversations_per_month=600, properties=None),
        features=_PRO_FEATURES,
        self_serve=True,
    ),
    "enterprise": Plan(
        name="enterprise",
        display_name="Enterprise",
        price_ars_monthly=169_900.0,
        price_ars_annual_monthly=169_900.0,  # precio a medida; este es el mínimo publicado
        limits=PlanLimits(users=None, conversations_per_month=1_500, properties=None),
        features=_ENTERPRISE_FEATURES,
        self_serve=False,
    ),
}


# ── Helpers públicos ───────────────────────────────────────────────────────────

def get_plan(name: str | None) -> Plan | None:
    """Devuelve el Plan para un nombre de tier, o None si no existe."""
    if name is None:
        return None
    return CATALOG.get(name.lower())  # type: ignore[arg-type]


def get_plan_or_default(name: str | None, default: TierName = "profesional") -> Plan:
    """Devuelve el Plan o el default (para suscripciones legadas sin tier)."""
    return get_plan(name) or CATALOG[default]


def list_plans() -> list[dict]:
    """Lista el catálogo completo ordenado por tier (para GET /billing/plans)."""
    return [CATALOG[t].as_dict() for t in ("basico", "profesional", "enterprise")]

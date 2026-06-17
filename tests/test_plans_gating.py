"""test_plans_gating.py — Tests unitarios para el catálogo de planes y gating por tier.

Corre sin Postgres (lógica pura y ASGI offline).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.plans import (
    CATALOG,
    Plan,
    PlanLimits,
    get_plan,
    get_plan_or_default,
    list_plans,
)
from app.services.subscription_service import subscription_grants_access


# ── Catálogo ──────────────────────────────────────────────────────────────────


def test_catalog_has_three_tiers():
    assert set(CATALOG) == {"basico", "profesional", "enterprise"}


def test_tier_prices_are_correct():
    assert CATALOG["basico"].price_ars_monthly == 39_900.0
    assert CATALOG["profesional"].price_ars_monthly == 84_900.0
    assert CATALOG["enterprise"].price_ars_monthly == 169_900.0


def test_enterprise_not_self_serve():
    assert not CATALOG["enterprise"].self_serve


def test_basico_and_pro_are_self_serve():
    assert CATALOG["basico"].self_serve
    assert CATALOG["profesional"].self_serve


def test_basico_has_no_features():
    assert len(CATALOG["basico"].features) == 0


def test_profesional_features():
    plan = CATALOG["profesional"]
    assert plan.includes_feature("cobranzas")
    assert plan.includes_feature("weekly_report")
    assert not plan.includes_feature("exports")
    assert not plan.includes_feature("documents")


def test_enterprise_includes_all_pro_features():
    pro_features = CATALOG["profesional"].features
    ent_features = CATALOG["enterprise"].features
    assert pro_features.issubset(ent_features)


def test_enterprise_has_extra_features():
    assert CATALOG["enterprise"].includes_feature("exports")
    assert CATALOG["enterprise"].includes_feature("documents")
    assert CATALOG["enterprise"].includes_feature("exec_reports")


def test_meets_min_tier():
    basico = CATALOG["basico"]
    pro = CATALOG["profesional"]
    ent = CATALOG["enterprise"]

    assert basico.meets_min_tier("basico")
    assert not basico.meets_min_tier("profesional")
    assert not basico.meets_min_tier("enterprise")

    assert pro.meets_min_tier("basico")
    assert pro.meets_min_tier("profesional")
    assert not pro.meets_min_tier("enterprise")

    assert ent.meets_min_tier("basico")
    assert ent.meets_min_tier("profesional")
    assert ent.meets_min_tier("enterprise")


def test_get_plan_returns_none_for_unknown():
    assert get_plan("unknown") is None
    assert get_plan(None) is None


def test_get_plan_or_default_falls_back():
    plan = get_plan_or_default(None)
    assert plan.name == "profesional"

    plan2 = get_plan_or_default("garbage")
    assert plan2.name == "profesional"


def test_list_plans_order():
    plans = list_plans()
    assert [p["name"] for p in plans] == ["basico", "profesional", "enterprise"]


def test_plan_as_dict_structure():
    d = CATALOG["profesional"].as_dict()
    assert "limits" in d
    assert "features" in d
    assert "self_serve" in d
    assert d["self_serve"] is True


# ── Gating (sin DB) ───────────────────────────────────────────────────────────


def _make_sub(**kwargs):
    """Crea un mock de Subscription con valores por defecto."""
    sub = MagicMock()
    sub.status = kwargs.get("status", "active")
    sub.plan = kwargs.get("plan", "profesional")
    sub.trial_ends_at = kwargs.get("trial_ends_at", None)
    return sub


def _utcnow():
    return datetime.now(timezone.utc)


def test_grants_access_active():
    sub = _make_sub(status="active")
    assert subscription_grants_access(sub)


def test_grants_access_trial_valid():
    sub = _make_sub(status="trial", trial_ends_at=_utcnow() + timedelta(days=10))
    assert subscription_grants_access(sub)


def test_grants_access_trial_expired():
    sub = _make_sub(status="trial", trial_ends_at=_utcnow() - timedelta(seconds=1))
    assert not subscription_grants_access(sub)


def test_grants_access_paused():
    sub = _make_sub(status="paused")
    assert not subscription_grants_access(sub)


def test_grants_access_cancelled():
    sub = _make_sub(status="cancelled")
    assert not subscription_grants_access(sub)


def test_grants_access_none():
    assert not subscription_grants_access(None)


# ── Tier gating logic ─────────────────────────────────────────────────────────


def test_basico_cannot_access_exports():
    plan = CATALOG["basico"]
    assert not plan.includes_feature("exports")


def test_basico_cannot_access_documents():
    plan = CATALOG["basico"]
    assert not plan.includes_feature("documents")


def test_profesional_cannot_access_enterprise_features():
    plan = CATALOG["profesional"]
    assert not plan.includes_feature("exports")
    assert not plan.includes_feature("documents")
    assert not plan.includes_feature("exec_reports")


def test_enterprise_can_access_all():
    plan = CATALOG["enterprise"]
    for feature in ["cobranzas", "exports", "documents", "exec_reports", "multi_branch"]:
        assert plan.includes_feature(feature)  # type: ignore[arg-type]


# ── create_preapproval — no llama a MP, verifica lógica de precio y Enterprise ───


@pytest.mark.asyncio
async def test_create_preapproval_enterprise_raises():
    """Enterprise no es self-serve: debe lanzar SubscriptionConfigError."""
    from app.services.subscription_service import (
        SubscriptionConfigError,
        create_preapproval,
    )

    with pytest.raises(SubscriptionConfigError, match="no es self-serve"):
        await create_preapproval(uuid4(), "test@example.com", plan="enterprise")


def test_unknown_plan_falls_back_to_profesional_in_catalog():
    """get_plan_or_default con nombre inválido devuelve profesional (precio $84.900)."""
    plan = get_plan_or_default("garbage_plan")
    assert plan.name == "profesional"
    assert plan.price_ars_monthly == 84_900.0

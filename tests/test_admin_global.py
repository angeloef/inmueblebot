"""Tests del explorador global cross-tenant super-admin (plan 05).

Offline (sin DB): el gate de auth (401 sin credenciales), la validación de entidad
(404 entidad desconocida), la whitelist de campos (400 sin cambios / 422 inválido) y los
helpers puros de paginación/serialización. El aislamiento cross-tenant real (RLS) lo
cubre ``test_superadmin_cross_tenant.py`` (plan 04); acá probamos la capa de endpoint.
"""

from __future__ import annotations

import httpx
import pytest

from app.api.deps import require_superadmin
from app.api.routes.admin_global import (
    MAX_PAGE_SIZE,
    _paginate,
    _superadmin_actor,
    _with_tenant,
)
from app.services.activity_log_service import VALID_ACTIONS


# ── Helpers puros ────────────────────────────────────────────────────────────


def test_paginate_clamps_and_offsets() -> None:
    assert _paginate(1, 50) == (0, 50)
    assert _paginate(3, 50) == (100, 50)
    # page < 1 se normaliza a 1; page_size sobre el tope se clampa.
    assert _paginate(0, 50) == (0, 50)
    assert _paginate(2, MAX_PAGE_SIZE + 999) == (MAX_PAGE_SIZE, MAX_PAGE_SIZE)


def test_with_tenant_annotates_row() -> None:
    names = {"abc": "Inmobiliaria X"}
    out = _with_tenant({"id": 1}, "abc", names)
    assert out["tenant_id"] == "abc"
    assert out["tenant_name"] == "Inmobiliaria X"
    # tenant_id None ⇒ sin nombre, sin romper.
    out_none = _with_tenant({"id": 2}, None, names)
    assert out_none["tenant_id"] is None
    assert out_none["tenant_name"] is None


def test_superadmin_actor_formats() -> None:
    class _Acc:
        id = "11111111-1111-1111-1111-111111111111"

    assert _superadmin_actor(_Acc()) == f"superadmin:{_Acc.id}"
    # Sin account (ops global key) ⇒ actor genérico, nunca vacío.
    assert _superadmin_actor(None) == "superadmin:ops"


def test_superadmin_edited_is_valid_action() -> None:
    """El audit log debe aceptar la acción que emite cada PATCH super-admin."""
    assert "superadmin_edited" in VALID_ACTIONS


# ── Endpoint: auth gate + validación de entidad (offline) ────────────────────


async def _client() -> httpx.AsyncClient:
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_list_requires_auth() -> None:
    """Sin credenciales ⇒ 401 antes de tocar la DB (fail-closed)."""
    async with await _client() as client:
        resp = await client.get("/admin/global/clients")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_requires_auth() -> None:
    async with await _client() as client:
        resp = await client.patch("/admin/global/clients/abc", json={"name": "X"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_unknown_entity_404_when_authed() -> None:
    """Con super-admin simulado, una entidad desconocida ⇒ 404 (antes de la DB)."""
    from app.main import app

    app.dependency_overrides[require_superadmin] = lambda: None
    try:
        async with await _client() as client:
            resp = await client.patch("/admin/global/widgets/1", json={"x": 1})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(require_superadmin, None)


@pytest.mark.asyncio
async def test_patch_empty_update_400_when_authed() -> None:
    """Body sin campos válidos ⇒ 400 (no hay nada que editar), sin tocar la DB."""
    from app.main import app

    app.dependency_overrides[require_superadmin] = lambda: None
    try:
        async with await _client() as client:
            # 'foo' no está en la whitelist ⇒ exclude_unset deja updates vacío ⇒ 400.
            resp = await client.patch("/admin/global/clients/abc", json={"foo": "bar"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(require_superadmin, None)

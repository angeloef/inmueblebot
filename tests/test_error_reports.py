"""Tests del reporte de errores in-app + triage super-admin (plan 07).

Offline (sin DB): la redacción de credenciales en el ``context`` (criterio de aceptación
de seguridad), los helpers de saneo de tamaño, y los gates de auth — POST exige usuario
autenticado, GET/PATCH exigen super-admin. La persistencia real se apoya en el mismo
escape hatch RLS que cubren los tests de los planes 04/06.
"""

from __future__ import annotations

import httpx
import pytest

from app.api.routes.error_reports import (
    MAX_CONSOLE_TAIL,
    _sanitize_context,
    _should_redact,
)

# ── Redacción de credenciales (seguridad) ────────────────────────────────────


def test_should_redact_matches_credential_keys() -> None:
    for key in ("token", "access_token", "Authorization", "Cookie", "X-Api-Key", "password"):
        assert _should_redact(key) is True
    for key in ("route", "version", "user_agent", "message"):
        assert _should_redact(key) is False


def test_sanitize_context_redacts_nested_secrets() -> None:
    raw = {
        "route": "/clients",
        "version": "abc123",
        "headers": {"Authorization": "Bearer secret", "X-Api-Key": "k-123"},
        "token": "should-not-survive",
    }
    cleaned = _sanitize_context(raw)
    assert cleaned["route"] == "/clients"
    assert cleaned["version"] == "abc123"
    assert cleaned["headers"]["Authorization"] == "[redacted]"
    assert cleaned["headers"]["X-Api-Key"] == "[redacted]"
    assert cleaned["token"] == "[redacted]"
    # El secreto literal nunca aparece en el resultado serializado.
    import json

    assert "secret" not in json.dumps(cleaned)
    assert "k-123" not in json.dumps(cleaned)


def test_sanitize_context_trims_console_tail() -> None:
    raw = {"console_tail": [f"line-{i}" for i in range(100)]}
    cleaned = _sanitize_context(raw)
    assert len(cleaned["console_tail"]) == MAX_CONSOLE_TAIL
    # Conserva las últimas líneas (las más recientes/relevantes).
    assert cleaned["console_tail"][-1] == "line-99"


def test_sanitize_context_rejects_non_dict() -> None:
    assert _sanitize_context("not-a-dict") == {}
    assert _sanitize_context(None) == {}


def test_sanitize_context_drops_oversized_payload() -> None:
    raw = {"console_tail": ["x" * 2000 for _ in range(200)]}
    cleaned = _sanitize_context(raw)
    # Tras recortar console_tail, si aún excede el tope, se descarta y se marca.
    import json

    assert len(json.dumps(cleaned, default=str)) <= 9000


# ── Auth gates (offline) ─────────────────────────────────────────────────────


async def _client() -> httpx.AsyncClient:
    from app.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_create_requires_auth() -> None:
    """POST sin credenciales ⇒ 401 (usuario autenticado obligatorio)."""
    async with await _client() as client:
        resp = await client.post("/admin/error-reports", json={"message": "algo falló"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_requires_superadmin() -> None:
    """GET de triage sin credenciales ⇒ 401 antes de tocar la DB (fail-closed)."""
    async with await _client() as client:
        resp = await client.get("/admin/error-reports")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_requires_superadmin() -> None:
    async with await _client() as client:
        resp = await client.patch(
            "/admin/error-reports/00000000-0000-0000-0000-000000000000",
            json={"status": "resolved"},
        )
    assert resp.status_code == 401

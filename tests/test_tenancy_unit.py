"""Offline unit tests for the multi-tenancy primitives (V3 Phase 1 + 1.5).

No DB / Redis / LLM. Covers the tenant column registry, the ContextVar fallback,
tenant-namespaced Redis keys, Fernet token encryption, and the 3-way active_router
resolution (incl. legacy use_v2_router back-compat).
"""

from uuid import UUID

import pytest

from app.core import tenancy


# --- tenant column registry -------------------------------------------------------
def test_tenant_column_default_and_override():
    assert tenancy.tenant_column("users") == "tenant_id"
    assert tenancy.tenant_column("conversations") == "tenant_id"
    # contracts.tenant_id already means the renter → agency FK is org_id.
    assert tenancy.tenant_column("contracts") == "org_id"


def test_global_tables_not_scoped():
    assert "economic_indices" in tenancy.GLOBAL_TABLES
    assert "economic_indices" not in tenancy.TENANT_SCOPED_TABLES


def test_scoped_tables_match_known_set():
    assert {"users", "properties", "conversations", "messages", "appointments",
            "faq_entries", "contracts", "charges"}.issubset(tenancy.TENANT_SCOPED_TABLES)


# --- ContextVar fallback ----------------------------------------------------------
def test_resolve_falls_back_to_default_when_unset():
    tenancy.set_current_tenant(None)
    assert tenancy.resolve_tenant_id() == tenancy.default_tenant_id()


def test_set_and_resolve_explicit_tenant():
    tid = UUID("11111111-1111-1111-1111-111111111111")
    token = tenancy.set_current_tenant(tid)
    try:
        assert tenancy.resolve_tenant_id() == tid
        assert tenancy.get_current_tenant() == tid
    finally:
        tenancy.reset_current_tenant(token)
    assert tenancy.get_current_tenant() is None


def test_tenant_redis_key_namespaces_by_tenant():
    a = UUID("11111111-1111-1111-1111-111111111111")
    b = UUID("22222222-2222-2222-2222-222222222222")
    tok = tenancy.set_current_tenant(a)
    try:
        key_a = tenancy.tenant_redis_key("working", "sess1")
    finally:
        tenancy.reset_current_tenant(tok)
    tok = tenancy.set_current_tenant(b)
    try:
        key_b = tenancy.tenant_redis_key("working", "sess1")
    finally:
        tenancy.reset_current_tenant(tok)
    assert key_a != key_b
    assert key_a.startswith(str(a)) and "working:sess1" in key_a


# --- Fernet token encryption ------------------------------------------------------
@pytest.fixture()
def _with_key(monkeypatch):
    from cryptography.fernet import Fernet

    from app.core import config, crypto
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TENANT_TOKEN_ENCRYPTION_KEY", key)
    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()
    yield
    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()


def test_encrypt_decrypt_roundtrip(_with_key):
    from app.core import crypto
    secret = "EAAG_meta_access_token_example"
    ct = crypto.encrypt_secret(secret)
    assert ct and ct != secret  # ciphertext, not plaintext
    assert crypto.decrypt_secret(ct) == secret


def test_encrypt_none_and_empty(_with_key):
    from app.core import crypto
    assert crypto.encrypt_secret(None) is None
    assert crypto.encrypt_secret("") is None
    assert crypto.decrypt_secret(None) is None


def test_encryption_fails_closed_without_key(monkeypatch):
    from app.core import config, crypto
    monkeypatch.delenv("TENANT_TOKEN_ENCRYPTION_KEY", raising=False)
    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()
    assert crypto.encryption_available() is False
    with pytest.raises(crypto.EncryptionUnavailableError):
        crypto.encrypt_secret("x")
    config.get_settings.cache_clear()
    crypto._fernet.cache_clear()


# --- active_router resolution (Phase 1.5) -----------------------------------------
def _resolve_with_settings(monkeypatch, bot_cfg: dict, use_v2_env: bool):
    import app.agents.prompts as prompts
    from app.api.routes import webhook

    monkeypatch.setattr(prompts, "_get_cached_bot_settings", lambda: bot_cfg)

    class _S:
        USE_V2_ROUTER = use_v2_env

    return webhook._resolve_active_router(_S())


def test_active_router_explicit_values(monkeypatch):
    for val in ("v1", "v2", "v3"):
        assert _resolve_with_settings(monkeypatch, {"active_router": val}, False) == val


def test_active_router_backcompat_use_v2(monkeypatch):
    # No active_router key → fall back to legacy use_v2_router boolean.
    assert _resolve_with_settings(monkeypatch, {"use_v2_router": "true"}, False) == "v2"
    assert _resolve_with_settings(monkeypatch, {"use_v2_router": "false"}, True) == "v1"


def test_active_router_invalid_value_falls_back(monkeypatch):
    # Garbage value is ignored → legacy path; env USE_V2_ROUTER=True → v2.
    assert _resolve_with_settings(monkeypatch, {"active_router": "bogus"}, True) == "v2"

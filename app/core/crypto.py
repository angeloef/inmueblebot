"""Application-layer symmetric encryption for secrets at rest (V3 Phase 1).

Used for ``tenants.wa_access_token`` (each inmobiliaria's Meta access token). We store
ciphertext in Postgres and decrypt only in memory when sending WhatsApp messages, so the
plaintext token never lands in query logs, backups, or pg_dump output.

Key management:
- The Fernet key comes from ``settings.TENANT_TOKEN_ENCRYPTION_KEY`` (a Render secret).
- It is NEVER committed and NEVER derived from a hardcoded passphrase (no ``pgcrypto``).
- When the key is absent the helpers fail **closed** (raise) rather than silently storing
  plaintext — encryption is not optional for access tokens.

Generate a key once with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionUnavailableError(RuntimeError):
    """Raised when an encrypt/decrypt is attempted without a configured key."""


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().TENANT_TOKEN_ENCRYPTION_KEY
    if not key:
        raise EncryptionUnavailableError(
            "TENANT_TOKEN_ENCRYPTION_KEY is not set — cannot encrypt/decrypt secrets. "
            "Set it from a Render secret (Fernet key, urlsafe base64, 32 bytes)."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypt a secret to a urlsafe ciphertext string. ``None``/empty → ``None``."""
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str | None) -> str | None:
    """Decrypt a ciphertext produced by ``encrypt_secret``. ``None``/empty → ``None``.

    Raises ``EncryptionUnavailableError`` if no key; ``InvalidToken`` if the ciphertext
    is corrupt or was encrypted with a different key (surface this — never return garbage).
    """
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise InvalidToken(
            "Failed to decrypt secret — wrong TENANT_TOKEN_ENCRYPTION_KEY or corrupt data."
        ) from exc


def encryption_available() -> bool:
    """True if a key is configured (lets callers degrade gracefully without raising)."""
    return bool(get_settings().TENANT_TOKEN_ENCRYPTION_KEY)

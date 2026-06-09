from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_RESEND_URL = "https://api.resend.com/emails"


async def _send(to: str, subject: str, html: str) -> bool:
    settings = get_settings()
    if not settings.RESEND_API_KEY:
        logger.warning("[email] RESEND_API_KEY ausente — email a %s omitido (degradado)", to)
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.EMAIL_FROM,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
        if r.status_code >= 400:
            logger.error("[email] Resend falló (%s): %s", r.status_code, r.text)
            return False
        return True
    except Exception as exc:
        logger.error("[email] excepción enviando a %s: %s", to, exc)
        return False


async def send_verification_email(email: str, token: str) -> bool:
    url = f"{get_settings().PUBLIC_APP_URL}/verify-email?token={token}"
    return await _send(
        email,
        "Verificá tu cuenta en ViviendApp",
        f'<p>Confirmá tu email: <a href="{url}">{url}</a></p>',
    )


async def send_password_reset(email: str, token: str) -> bool:
    url = f"{get_settings().PUBLIC_APP_URL}/reset-password?token={token}"
    return await _send(
        email,
        "Restablecé tu contraseña",
        f'<p>Restablecé tu contraseña: <a href="{url}">{url}</a></p>',
    )

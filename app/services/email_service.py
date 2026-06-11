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


async def send_invite_email(to_email: str, agency_name: str, invite_url: str) -> bool:
    html = (
        f'<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">'
        f'<h2 style="color:#155f6f">Te invitaron a {agency_name}</h2>'
        f'<p>Fuiste invitado/a a unirte al equipo de <b>{agency_name}</b> en ViviendApp.</p>'
        f'<p>Hacé clic para crear tu cuenta y empezar:</p>'
        f'<p><a href="{invite_url}" '
        f'style="display:inline-block;background:#155f6f;color:#fff;padding:12px 24px;'
        f'border-radius:8px;text-decoration:none;font-weight:600">Aceptar invitación</a></p>'
        f'<p style="color:#6b7280;font-size:13px">Si no esperabas esta invitación, '
        f'podés ignorar este email. El enlace vence en 7 días.</p>'
        f'</div>'
    )
    return await _send(to_email, f"Te invitaron a {agency_name} en ViviendApp", html)

from __future__ import annotations

import html as _html_stdlib
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_RESEND_URL = "https://api.resend.com/emails"


async def _send(
    to: str,
    subject: str,
    html: str,
    *,
    reply_to: str | None = None,
    from_: str | None = None,
) -> bool:
    settings = get_settings()
    if not settings.RESEND_API_KEY:
        logger.warning("[email] RESEND_API_KEY ausente — email a %s omitido (degradado)", to)
        return False
    payload: dict = {
        "from": from_ or settings.EMAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = [reply_to]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                _RESEND_URL,
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
            )
        if r.status_code >= 400:
            logger.error("[email] Resend falló (%s): %s", r.status_code, r.text)
            return False
        return True
    except Exception as exc:
        logger.error("[email] excepción enviando a %s: %s", to, exc)
        return False


async def send_client_email(
    to: str,
    subject: str,
    body: str,
    *,
    reply_to: str | None = None,
) -> bool:
    """Envía un correo libre a un cliente de parte de la plataforma (reply-to = inmobiliaria)."""
    safe_body = _html_stdlib.escape(body).replace("\n", "<br>")
    safe_subject = _html_stdlib.escape(subject)
    html_content = (
        f'<div style="font-family:system-ui,sans-serif;max-width:600px;margin:0 auto;'
        f'color:#111827;line-height:1.6">'
        f"<p>{safe_body}</p>"
        f'<hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">'
        f'<p style="color:#6b7280;font-size:12px">'
        f"Este correo fue enviado a través de ViviendApp.</p>"
        f"</div>"
    )
    return await _send(to, safe_subject, html_content, reply_to=reply_to)


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


async def send_sales_inquiry_notification(
    to: str,
    contact_name: str,
    contact_email: str,
    tenant_name: str,
    phone: str | None,
    property_count: str | None,
    message: str | None,
) -> bool:
    """Notifica a ventas@viviendapp.com de una nueva consulta Enterprise."""
    import html as _h
    rows = [
        ("Nombre", contact_name),
        ("Email", contact_email),
        ("Inmobiliaria", tenant_name),
        ("Teléfono", phone or "—"),
        ("Propiedades/sucursales", property_count or "—"),
        ("Mensaje", message or "—"),
    ]
    body = "".join(f"<p><b>{_h.escape(k)}:</b> {_h.escape(str(v))}</p>" for k, v in rows)
    html = (
        f'<div style="font-family:system-ui,sans-serif;max-width:600px">'
        f'<h2 style="color:#155f6f">Nueva consulta Enterprise</h2>{body}'
        f'</div>'
    )
    return await _send(to, f"Consulta Enterprise — {_h.escape(contact_name)}", html)


async def send_delete_account_code(email: str, code: str) -> bool:
    import html as _h
    html = (
        f'<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto">'
        f'<h2 style="color:#dc2626">Confirmá el borrado de tu cuenta</h2>'
        f'<p>Recibimos una solicitud para <strong>borrar permanentemente</strong> '
        f'tu cuenta de ViviendApp y todos sus datos.</p>'
        f'<p style="font-size:14px;color:#374151">Tu código de confirmación:</p>'
        f'<div style="font-size:36px;font-weight:700;letter-spacing:8px;color:#111827;'
        f'background:#f3f4f6;padding:20px;border-radius:8px;text-align:center;margin:16px 0">'
        f'{_h.escape(code)}</div>'
        f'<p style="color:#6b7280;font-size:13px">El código vence en 15 minutos. '
        f'Si no solicitaste este borrado, ignorá este correo — tu cuenta sigue activa.</p>'
        f'<p style="color:#dc2626;font-size:13px"><strong>Esta acción es irreversible. '
        f'Todos tus datos se eliminarán de forma permanente.</strong></p>'
        f'</div>'
    )
    return await _send(email, "Confirmá el borrado de tu cuenta en ViviendApp", html)


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

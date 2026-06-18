---
id: 12
title: "Clientes — enviar correo desde la app (Resend), no mailto"
status: completed
priority: medium
area: backend+frontend
files:
  - app/services/email_service.py   # _send (Resend) + senders tipados → extender con reply_to + send_client_email
  - app/api/routes/                 # nuevo endpoint POST enviar correo a cliente
  - app/api/routes/admin.py         # (referencia) patrón de rutas tenant-scoped + activity_log
  - dashboard/src/Clients.jsx       # botón "Correo" (167) → modal de redacción
  - dashboard/src/api.js            # hook useSendClientEmail
related_existing:
  - app/services/activity_log (plan 03)   # registrar email_sent en el timeline del cliente
config:
  - RESEND_API_KEY, EMAIL_FROM (ya en app/core/config.py)
depends_on: []
decisiones:
  remitente: "from = EMAIL_FROM (plataforma); reply-to = email de la inmobiliaria/agente"
  log: "registrar en activity_log (action='email_sent')"
skills: ["fastapi-patterns", "python-testing", "react-patterns", "accessibility"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 12 — Enviar correo desde la app (no mailto)

## 1. Objetivo
Reemplazar el botón **"Correo"** del perfil de cliente (hoy abre `mailto:` → popup del cliente de correo del SO) por un **envío real desde la app**: modal de redacción (asunto + cuerpo) → backend envía vía **Resend** desde la plataforma con **reply-to de la inmobiliaria**, y queda registrado en el timeline del cliente.

## 2. Contexto necesario (estado actual real)
- **Hoy** — `Clients.jsx:167`: `onClick={() => client.email && window.open('mailto:'+client.email)}` (también hay `mailto:` en 159/187 como enlaces). Eso depende del cliente de correo local → el founder quiere enviar desde la app.
- **Backend ya tiene email** — `app/services/email_service.py`: `_send(to, subject, html)` pega a `https://api.resend.com/emails` con `RESEND_API_KEY`; si falta la key, degrada a no-op (loguea). Ya hay `send_verification_email`, `send_password_reset`, `send_invite_email`. **`_send` no soporta `reply_to` todavía** → hay que extenderlo.
- **Config** (`app/core/config.py`): `RESEND_API_KEY`, `EMAIL_FROM` presentes.
- **Auditoría**: existe `activity_log` (plan 03) → registrar el envío en la ficha del cliente.
- **Tenant scoping**: el endpoint corre con auth normal (titular/agente); el destinatario es un `user` (cliente) del tenant. El `reply-to` sale del email del account/inmobiliaria (ver `/auth/me`/tenant settings → `owner`/agente).

## 3. Plan secuencial

### Backend
- [ ] Extender `email_service._send(to, subject, html, *, reply_to=None, from_=None)` para pasar `reply_to`/`from` a Resend (campo `reply_to` de la API). No romper los senders existentes.
- [ ] `send_client_email(to, subject, body, *, reply_to)` — arma HTML simple (escapando el body; nada de inyección) y delega en `_send`.
- [ ] Endpoint `POST /clients/{client_id}/email` (auth normal, tenant-scoped): valida que el cliente pertenezca al tenant y tenga email; body `{subject, body}` con límites de tamaño; `reply_to` = email del account/inmobiliaria (no del request, server-side). Llama `send_client_email`. Si Resend está en no-op (sin key) → responder 503/“no configurado” claro (no fingir éxito).
- [ ] Emitir `activity_log` `action='email_sent'` (entity=client, actor=account, payload: subject + to). No loguear el cuerpo completo si trae PII innecesaria (guardar asunto + longitud).
- [ ] Tests: envío OK (mock Resend), cliente de otro tenant → 404/403, cliente sin email → 422, sin RESEND_API_KEY → degradado controlado, y que se escribe activity_log.

### Frontend
- [ ] Modal **"Enviar correo"** (reusar patrón modal + `useFocusTrap`): campos asunto + cuerpo, destinatario precargado (`client.email`, readonly), validación mínima. Botón enviar con estado de carga.
- [ ] Hook `useSendClientEmail` en `api.js` → `POST /clients/{id}/email`; toast éxito/error (incluye el caso “email no configurado”).
- [ ] `Clients.jsx:167`: el botón "Correo" abre el modal (no `mailto`). Deshabilitado si el cliente no tiene email. (Los enlaces de 159/187 pueden quedar como `mailto` de conveniencia o también abrir el modal — decidir en review; mínimo el botón de acción usa el flujo nuevo.)

## 4. Criterios de aceptación
- Desde el perfil del cliente se redacta y **envía** un correo sin salir de la app; llega vía Resend con `reply-to` de la inmobiliaria.
- El envío queda registrado en el timeline del cliente (`activity_log`).
- Sin RESEND_API_KEY el usuario ve un mensaje claro (no un falso “enviado”).
- Un cliente de otro tenant no es alcanzable (403/404); validación de asunto/cuerpo.
- `security-reviewer` aprueba (reply-to server-side, sin inyección en el HTML, scoping correcto).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns` (endpoint/schemas/validación), `python-testing` (mock de Resend, scoping), `react-patterns`, `accessibility` (modal con foco/teclado).
- **Agentes:** **security-reviewer** (reply-to no manipulable por el cliente, escape del cuerpo, tenant-scoping, rate-limit básico), **react-reviewer** (modal/estado de carga).
- **MCP:** ninguno (Resend es HTTP server-side; en tests se mockea).
- **Workflow:** extender email_service → endpoint + tests → modal frontend. Reusar activity_log (plan 03) y el patrón de rutas tenant-scoped.

## 6. Verificación
- `pytest` (envío mockeado, scoping, sin-key, activity_log) en Docker; `ruff`/`black`.
- `npm run build`; **Chrome MCP**: abrir cliente → "Correo" → modal → enviar → toast OK + entrada en el timeline. (Si el entorno de test no tiene RESEND_API_KEY, verificar el camino degradado y el mock en tests.)
- `security-reviewer` sobre el endpoint y `email_service`.

## 7. Bitácora (append-only)
- 2026-06-17 — Plan creado. Decisiones: from=EMAIL_FROM, reply-to=inmobiliaria (server-side), log en activity_log. Reusa email_service.py (extender con reply_to) y activity_log (plan 03).
- 2026-06-18 — Implementado. email_service: reply_to + send_client_email (html.escape en body Y subject). activity_log_service: email_sent en VALID_ACTIONS. admin.py: POST /clients/{id}/email (tenant-scoped, 503 sin key, log). Clients.jsx: SendEmailModal reemplaza mailto. Gates: ruff ✓, build ✓, 530 tests pass, security-reviewer HIGH (subject escape) corregido.

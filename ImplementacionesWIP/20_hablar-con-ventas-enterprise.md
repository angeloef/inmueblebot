---
id: 20
title: "Enterprise — 'Hablar con ventas': formulario in-app + WhatsApp directo"
status: completed
priority: medium
area: backend+frontend
files:
  - dashboard/src/Config.jsx        # 'Hablar con ventas' (hoy mailto estático, línea ~637)
  - app/api/routes/                 # nuevo endpoint solicitud de ventas (espeja error_reports)
  - app/services/email_service.py   # aviso a devs/ventas
  - dashboard/src/superadmin/SuperadminShell.jsx  # (opcional) ver solicitudes de ventas
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decisiones:
  flujo: "ambos — formulario in-app que nos llega (email + opcional pestaña superadmin) + opción WhatsApp directo"
skills: ["fastapi-patterns", "react-patterns", "python-testing", "accessibility"]
agents: ["react-reviewer", "security-reviewer"]
---

# Plan 20 — 'Hablar con ventas' (Enterprise)

## 1. Objetivo
Reemplazar el `mailto:` estático de "Hablar con ventas" por un **flujo CTA interactivo**: modal con formulario in-app (nos llega la solicitud) **y** opción de **WhatsApp directo**. Explica brevemente el proceso de contratación de Enterprise.

## 2. Contexto necesario (estado actual real)
- `Config.jsx` (~637) hoy: `<a href="mailto:ventas@viviendapp.com">Hablar con ventas</a>` — estático.
- Enterprise es **no self-serve** (plan 08): el catálogo lo marca `self_serve:false` y `subscribe` devuelve 409. Por eso necesita un canal de contacto.
- **Precedente**: `error_reports` (tenant crea → devs gestionan) — espejar para "sales leads".

## 3. Plan secuencial
- [ ] **Modal CTA** (al tocar "Hablar con ventas"): copy con los pasos del proceso Enterprise (a definir, breve) + formulario (nombre, inmobiliaria, teléfono, nº de propiedades/sucursales, mensaje) + botón "Enviar" + botón "WhatsApp directo" (abre `wa.me/<nuestro número>` en pestaña nueva).
- [ ] **Backend**: `POST /sales-inquiries` (auth normal, tenant-scoped) que persiste la solicitud y **avisa por email** a ventas/devs (reusar `email_service`). Validación + rate-limit.
- [ ] (Opcional) Pestaña/listado en `/superadmin` para ver las solicitudes (espeja `ErrorTriage`). Si no entra en budget, dejar al menos el email.
- [ ] Tests: crear solicitud (tenant), email disparado (mock), scoping; WhatsApp link correcto.

## 4. Criterios de aceptación
- "Hablar con ventas" abre un flujo claro; el formulario crea una solicitud que nos llega (email) y/o aparece en superadmin; el WhatsApp directo funciona.
- `security-reviewer` OK (validación, scoping, rate-limit).

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer**, **security-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (light+dark).

## 6. Verificación
- `pytest` (solicitud + email mock) en Docker; `npm run build`.
- Chrome MCP/Playwright: abrir modal, enviar formulario (toast OK), probar WhatsApp link.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Flujo: formulario in-app + WhatsApp (decisión del usuario). Espeja error_reports + email_service. Definir el copy del proceso Enterprise en preflight.
- 2026-06-19 — Implementado. Backend: modelo SalesInquiry + migración 0022 + ruta POST/GET/PATCH /sales-inquiries + email notification. Frontend: SalesModal en Config.jsx reemplaza mailto, botón WhatsApp directo. Superadmin: pestaña Ventas + SalesInquiries.jsx. Tests: 7 passed. Build: OK. Gates: ruff OK, pytest OK, vite build OK.

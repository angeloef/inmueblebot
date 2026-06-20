---
id: fix-envio-correo-cliente-con-email
status: completed
priority: P1
area: Backend + Frontend (Clients email)
files:
  - app/api/routes/admin.py
  - dashboard/src/Clients.jsx
endpoints:
  - POST /clients/{client_id}/email
depends_on: []
related_areas: [12_enviar-correo-desde-app]
skills: [fastapi-patterns]
agents: [silent-failure-hunter, fastapi-reviewer]
---

# 38 — Fix: "el cliente no tiene email registrado" cuando sí lo tiene

## 1. Objetivo
Al enviar correo desde la app a un cliente que **sí** tiene email, salta 422
"El cliente no tiene email registrado." Corregir la causa raíz (no maquillar el mensaje).
Plan 12 dejó el feature como `completed` pero el testing manual lo muestra roto.

## 2. Contexto necesario
- `app/api/routes/admin.py:2911-2940` — `send_email_to_client`. Hace:
  `SELECT id, email, name FROM users WHERE id=:cid AND tenant_id=:tid`. Si `email` es falsy → 422.
- Sospechas a verificar (la investigación ES la tarea):
  1. **El `client_id` que manda el front no es `users.id`.** Ver cómo `Clients.jsx` carga clientes
     (`dashboard/src/Clients.jsx`, drawer en `:172` `ClientDrawer`, acción email) y qué id pasa.
     Si los "clientes" del dashboard salen de otra fuente/tabla o de un id distinto, el `WHERE id`
     no matchea la fila con email (o matchea otra fila sin email).
  2. **El email vive en otra columna/JSON** (p.ej. `extra_data`, `contact`, `phone`-style) y no en
     `users.email`.
  3. **Scope de tenant**: si el cliente pertenece a una sucursal/sub-tenant, `tenant_id` resuelto
     no coincide. Ver `resolve_tenant_id()` y `billing_tenant_id` vs `tenant_id`.
- Confirmar contra un cliente real de prod (la DB local = prod, ver memoria `local-db-is-prod`):
  buscar el cliente que falló y ver dónde está realmente su email.

## 3. Plan secuencial
- [ ] Reproducir: identificar un cliente concreto con email y el `client_id` que el front envía.
- [ ] Diagnosticar cuál de las 3 hipótesis aplica (query directa a la DB).
- [ ] Corregir el origen: alinear el id que manda el front con el que consulta el endpoint, o leer el email de la columna correcta.
- [ ] Mantener el 422 solo para el caso legítimo (cliente realmente sin email).

## 4. Criterios de aceptación
- Enviar correo a un cliente con email → 200 y el mail sale (o 503 si Resend no está configurado, que es otro caso).
- Cliente genuinamente sin email → sigue dando 422 con el mensaje claro.
- No se rompe el registro en `activity_log` (admin.py:2959+).

## 5. Skills / MCP / Workflow AI
`/ponytail full`. Diagnóstico primero (no parchar el mensaje). `silent-failure-hunter` para confirmar que no haya otros lookups frágiles de email.

## 6. Verificación
- Manual con Chrome MCP: drawer de cliente → enviar correo → 200.
- Query a la DB para confirmar dónde estaba el email.

## 7. Bitácora (append-only)
- 2026-06-20: plan creado. Endpoint consulta `users.email` por `id+tenant_id`; el bug está aguas arriba (id que manda el front, columna del email, o scope de tenant). Investigar antes de tocar el 422.
- 2026-06-20: DIAGNOSTICADO + FIXED (hipótesis 2). El email de los clientes del dashboard vive en
  `users.extra_data['email']` (JSON) — así lo escribe `create_lead`/`update_lead` y lo lee `_user_to_dict`.
  La columna `users.email` **ni existe** en la DB (prod): el `SELECT id, email, name FROM users` original
  tiraba UndefinedColumn → siempre fallaba. Confirmado por query directa: 6 clientes con email en extra_data,
  0 en columna. El `client_id` del front (= `str(u.id)`) era correcto → fix backend-only, sin tocar Clients.jsx.
  Cambio (`admin.py` send_email_to_client): raw SQL → ORM `db.query(User)` + `_parse_extra` →
  `extra.get('email') or getattr(user,'email',None)`. `User` no mapea columna email, así que el getattr es
  fallback inocuo. 422 se mantiene solo si no hay email real. Validación id UUID (422 si inválido).
  Verificado: replay de la lógica contra cliente real `740662a8...` → resuelve `lead@x.com`. silent-failure-hunter:
  no hay otros lookups frágiles de `users.email` (grep limpio). Gates: ruff (mi línea nueva limpia tras `from None`;
  resto baseline), import OK, test_activity_log falla baseline (mock `_RecordingSession` sin `begin_nested`, no
  relacionado). No se hizo el send en vivo (mandaría correo real a un cliente de prueba); el bug era el lookup,
  ya probado. `/ponytail full`: fix mínimo, sin abstracciones. Commit+push.

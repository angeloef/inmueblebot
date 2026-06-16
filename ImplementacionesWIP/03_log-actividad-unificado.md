---
id: 03
title: "Log de actividad unificado (Visitas y actividad sólida)"
status: pending
priority: high
area: backend+frontend
files:
  - app/db/models/                    # nuevo activity_log.py
  - app/api/routes/admin.py           # emitir eventos + endpoint GET actividad
  - alembic/versions/                 # nueva migración
  - dashboard/src/api.js              # hook useActivity
  - dashboard/src/Properties.jsx      # bloque "Visitas y actividad" (279-294)
  - dashboard/src/Clients.jsx         # tab "Actividad" (241-255)
emit_points:
  - app/api/routes/admin.py:1017   # update_property        → property_edited
  - app/api/routes/admin.py:1118   # update_property_status → status_changed
  - app/api/routes/admin.py:1157   # reassign               → reassigned
  - app/api/routes/admin.py:1228   # relate-client          → relation_linked/changed/unlinked
related_existing:
  - app/db/models/appointment.py       # visitas/citas (ya alimentan el timeline)
  - app/db/models/cobranzas.py         # contracts/charges/economic_indices YA EXISTEN → unificar, no duplicar
depends_on: []
note: "01 y 02 introducen/centralizan puntos de vínculo; idealmente ejecutar 03 después para emitir desde código ya estabilizado."
skills: ["fastapi-patterns", "python-patterns", "python-testing", "react-patterns"]
agents: ["Plan", "security-reviewer", "react-reviewer"]
---

# Plan 03 — Log de actividad unificado

## 1. Objetivo
Que **"Visitas y actividad"** deje de mostrar solo citas y pase a ser un **timeline sólido y unificado** por propiedad (y por cliente) que registre: **vínculos de cliente**, **cambios de estado** y **ediciones de propiedad** — más los datos esenciales que un jefe de inmobiliaria argentina necesita ver de un vistazo. Persistido y auditable.

## 2. Contexto necesario (estado actual real)

**Hoy "Visitas y actividad"** (`Properties.jsx:279-294`) solo hace `allEvents.filter(e => e.propId === property.id)` → son **appointments** (citas de calendario). No hay registro de ninguna otra acción.

**No existe** tabla/modelo de actividad o auditoría. Modelos actuales: `appointments`, `properties`, `users`, y un módulo **`cobranzas`** ya presente con `contracts`, `charges`, `economic_indices` (`app/db/models/cobranzas.py`) — clave para "datos esenciales unificados" (ver §recomendación).

**Las acciones a registrar ya pasan por 4 endpoints** (ver `emit_points` en frontmatter):
- `update_property` (1017), `update_property_status` (1118), `reassign` (1157), `relate-client` (1228).
- Todos reciben `db: Session` y ya hacen `db.commit()`. Son el lugar natural para emitir un registro de actividad en la **misma transacción**.
- Multi-tenant: las entidades llevan `tenant_id` (ver `appointment.py`). El log debe ser tenant-scoped igual.

**Estado/auth del actor:** el dashboard opera scopeado por `X-Branch-Id`/tenant (ver `api.js:30`). Verificar si hay identidad de usuario-agente disponible en el request; si no, registrar `actor='dashboard'` + branch, y dejar `actor_user_id` nullable para evolución futura. (Investigar dependencias de auth en `admin.py` — usar subagente **Explore**.)

## 3. Plan secuencial

### Backend
- [ ] **Modelo** `app/db/models/activity_log.py` → tabla `activity_log`:
  `id (uuid)`, `tenant_id (fk, nullable)`, `entity_type ('property'|'client')`, `entity_id (str)`, `action (str)`, `actor (str)`, `actor_user_id (uuid, nullable)`, `payload (JSONB: before/after, relation, nombres legibles)`, `created_at (tz)`. Índice por `(tenant_id, entity_type, entity_id, created_at)`.
- [ ] **Migración alembic** para la tabla (seguir convención de `alembic/versions/`).
- [ ] **Helper** `log_activity(db, *, tenant_id, entity_type, entity_id, action, actor, payload)` (en `app/services/` o repo) que hace `db.add(...)` sin commitear (lo commitea el endpoint). Que **nunca** rompa la operación principal: envolver en try/except y loguear con `logging`.
- [ ] **Emitir** en los 4 endpoints, capturando antes/después:
  - `relate-client`: `relation_linked` / `relation_changed` / `relation_unlinked` (incluir nombre del cliente y relación).
  - `update_property_status`: `status_changed` con `{from, to}`.
  - `update_property`: `property_edited` con diff de campos clave (precio, moneda, datos), **no** dumpear todo el objeto.
  - `reassign`: `reassigned` con sucursal origen/destino.
- [ ] **Endpoint** `GET /admin/properties/{id}/activity` y `GET /admin/clients/{id}/activity` (o unificado `GET /admin/activity?entity_type=&entity_id=`), tenant-scoped, paginado, orden desc.
- [ ] Tests pytest: que cada endpoint escribe la fila correcta y que un fallo del log no aborta la operación.

### Frontend
- [ ] Hook `useActivity(entityType, id)` en `api.js`.
- [ ] **Merge** en el timeline: combinar `appointments` (visitas) + `activity_log` en una sola lista ordenada por fecha, con ícono/color por tipo (reusar `KIND_META` de `EventPopover.jsx` y extender con tipos nuevos). Aplica a `Properties.jsx:279-294` y al tab Actividad de `Clients.jsx:241-255`.
- [ ] Cada entrada: fecha, actor, descripción legible en español ("Vinculado como inquilino: Juan Pérez", "Estado: Disponible → Alquilada", "Precio actualizado USD 120.000 → 115.000").

## 4. Recomendación — datos esenciales para inmobiliaria AR (unificados)
Para que el log/ficha resuelva problemas reales y de forma **unificada** (no islas de datos), priorizar y **enlazar con el módulo `cobranzas` ya existente** en vez de duplicar:

- **Alquiler / contrato** (vía `contracts`/`charges`): fecha inicio–fin, monto y **moneda (ARS/USD)**, **índice de ajuste (ICL / IPC / Casa Propia)** y periodicidad, **próxima actualización**, depósito, **garante / seguro de caución**, expensas, y **estado de pago (al día / atrasado)** traído de `charges`. → el timeline debería mostrar hitos de contrato y alertas de vencimiento/ajuste.
- **Propietario**: contacto del dueño, **tipo y vencimiento de autorización** (venta/alquiler), exclusividad.
- **Venta**: precio USD, seña/reserva, estado de escrituración.
- **Operativo / gestión**: agente responsable, **origen del lead** (ZonaProp / Argenprop / MercadoLibre / WhatsApp / referido), fecha de última gestión.

Decisión de diseño sugerida: el `activity_log` registra *eventos*; los *datos estructurados* (contrato, autorización) viven en sus tablas (`cobranzas`, `extra_data`) y el timeline los **referencia/surface**. Así "Visitas y actividad" se vuelve el panel unificado del jefe sin reescribir lo que ya existe.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns` (routers finos, schemas separados, validación), `python-patterns`, `python-testing` (pytest + cobertura del helper), `react-patterns`.
- **Agentes:** **Plan** (subagente arquitecto) para decidir tabla nueva vs. extender, y el contrato del endpoint, **antes** de codear; `security-reviewer` (el log no debe filtrar PII sensible ni tokens; respetar tenant-scoping/RLS); `react-reviewer` para el merge del timeline.
- **MCP:** ninguno externo.
- **Workflow:** este es el plan transversal y de mayor riesgo → arrancar con **Plan agent** para el diseño, luego implementar backend con migración + tests, y recién después el frontend. Correr suite pytest existente para no romper.

## 6. Verificación
- `alembic upgrade head` en entorno limpio + downgrade.
- `pytest` (incluir tests nuevos del log; verificar que fallo del log no aborta la operación principal).
- Manual/Playwright: cambiar estado, vincular y editar una propiedad → las 3 acciones aparecen en el timeline con texto correcto.
- `security-reviewer` sobre el diff backend (PII / tenant-scoping).

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Pendiente. Confirmar disponibilidad de identidad de agente en requests del dashboard (afecta campo `actor`).

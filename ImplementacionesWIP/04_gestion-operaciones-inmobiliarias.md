# Gestión de operaciones inmobiliarias — Plan de mejora

**Fecha:** 2026-06-16
**Contexto:** Análisis estructural de los flujos "Vincular propiedad" (comprador/inquilino/interesado) y "Cobranzas", y plan para cubrir las funciones administrativas que necesita una inmobiliaria real (AR).

**Decisiones tomadas (2026-06-16):**
- Ejecución **backend primero** (modelo + migraciones + endpoints). El frontend del dashboard queda para una fase siguiente.
- **El contrato es la fuente de verdad** para inquilino↔propiedad: vincular un inquilino crea/abre un contrato (borrador) y el estado de la propiedad se deriva del contrato activo.
- **Promover las relaciones JSONB a tablas relacionales** con FK + backfill.
- **Atribución por agente**: cada vínculo/venta/contrato registra el agente (`tenant_members.id`); seleccionable en un dropdown cuyas opciones son los miembros de equipos.

---

## Cómo funciona hoy (estado actual)

### Vincular propiedad
`POST /admin/properties/{prop_id}/relate-client` (admin.py). Relaciones: `buyer`, `tenant`, `interested`, `none`.
- Propiedad (`extra_data` JSONB): `buyer_id`/`tenant_id`; `status` → `sold`/`rented`.
- Usuario (`extra_data` JSONB): `role` → `owner`/`tenant`; append a `property_relations[]`.
- Loguea en `activity_log`.
- **Todo en blobs JSONB, sin FK ni historial real.**

### Cobranzas
Tablas relacionales: `contracts`, `charges`, `contract_expenses`, `economic_indices`.
- Contrato con `tenant_id` (inquilino), `owner_id` (propietario), renta base, ajuste IPC/fijo, punitorio diario, comisión.
- Cuotas idempotentes hasta el mes actual; punitorio al vuelo; pago congela cifras; liquidación al propietario; recordatorio WhatsApp manual.
- **Núcleo sólido**, pero desconectado del CRM de vínculos.

---

## Problemas detectados

### 🔴 Críticos (se resuelven y ejecutan en esta fase)

| # | Problema | Solución propuesta |
|---|----------|--------------------|
| C1 | "Vincular inquilino" y el contrato son sistemas distintos; sin fuente única de verdad; la propiedad no vuelve a `available` al terminar el contrato. | El contrato manda. Vincular inquilino crea/asegura un contrato (estado `draft`). El estado de la propiedad se **deriva** del contrato activo. |
| C2 | No existe la entidad **garante/garantía** (solo un tipo de documento, donde se puede subir cualquier cosa). | Tabla `guarantors` (tipo: propietaria/recibo/caución/otro, datos de contacto, propiedad en garantía), ligada al contrato. |
| C3 | No hay **depósito en garantía**. | Campos de depósito en `contracts` (monto, moneda, estado held/returned/partial, fecha de devolución). |
| C4 | La **venta** no se modela (solo flag `status=sold`). | Tabla `sales` (precio, seña/reserva, fecha, comisión de venta, estado reserved/signed/closed/fallen, comprador, propietario, agente). |
| C5 | Sin **atribución por agente** (`actor_user_id` siempre NULL). | Columna `agent_id` (FK `tenant_members`) en `property_relations`, `contracts` y `sales`. |

### 🟡 Importantes (fase 2)

- **I1** Carga manual del IPC; sin fetch automático INDEC/BCRA; falta índice **ICL** nativo.
- **I2** Un solo inquilino/comprador por propiedad; sin co-inquilinos ni co-propietarios. *(La tabla `property_relations` ya lo habilita estructuralmente; falta UI y lógica de contrato multi-parte.)*
- **I3** Sin **recibos** de pago ni liquidación como **PDF**.
- **I4** Sin automatización del ciclo de vida: avisos de vencimiento/renovación, dunning automático, scheduler de cuotas.
- **I5** Integridad referencial débil en lo viejo (JSONB sin FK). *(Se corrige al migrar a `property_relations`.)*

### 🟢 Menores (fase 3)

- **M1** Estados de propiedad gruesos; no soporta venta+alquiler simultáneos; `reserved` no guarda quién/seña/vencimiento.
- **M2** Sin embudo comercial (lead → visita → oferta → reserva → contrato/venta).
- **M3** Punitorios sin tope legal ni distinción interés moratorio/punitorio.
- **M4** Alquileres/ventas en USD no encajan con el modelo de ajuste IPC.

---

## Diseño de datos (fase crítica)

Todas las tablas nuevas llevan `tenant_id` (RLS org-aware, como el resto) y se crean en **transacción aislada** (patrón `ensure_cobranzas_schema`) para no tocar la migración monolítica frágil de `admin.py` (ver memoria `startup-migration-single-txn-landmine`).

```
property_relations
  id UUID PK
  tenant_id UUID            -- agencia/sucursal (RLS)
  property_id INTEGER FK properties(id) ON DELETE CASCADE
  client_id   UUID FK users(id) ON DELETE CASCADE
  relation    VARCHAR(20)   -- buyer|tenant|interested|owner
  agent_id    UUID FK tenant_members(id) ON DELETE SET NULL
  status      VARCHAR(20)   -- active|ended
  created_at, ended_at
  UNIQUE (property_id, client_id, relation) parcial WHERE status='active'

guarantors
  id UUID PK
  tenant_id UUID
  contract_id UUID FK contracts(id) ON DELETE CASCADE (nullable)
  client_id   UUID FK users(id) ON DELETE SET NULL (nullable)
  name, guarantee_type VARCHAR(20)  -- propietaria|recibo|caucion|otro
  phone, email, guarantee_property_address, notes
  created_at

sales
  id UUID PK
  tenant_id UUID
  property_id INTEGER FK properties(id) ON DELETE SET NULL
  buyer_id    UUID FK users(id) ON DELETE SET NULL
  seller_id   UUID FK users(id) ON DELETE SET NULL  -- propietario
  agent_id    UUID FK tenant_members(id) ON DELETE SET NULL
  sale_price BIGINT, currency VARCHAR(3)
  reservation_amount BIGINT, reservation_date DATE   -- seña
  sale_date DATE
  commission_pct DOUBLE PRECISION, commission_amount BIGINT
  status VARCHAR(20)  -- reserved|signed|closed|fallen
  notes, created_at, updated_at

contracts  (ALTER: columnas nuevas, IF NOT EXISTS)
  agent_id UUID FK tenant_members(id) ON DELETE SET NULL
  deposit_amount BIGINT DEFAULT 0
  deposit_currency VARCHAR(3) DEFAULT 'ARS'
  deposit_status VARCHAR(20) DEFAULT 'none'   -- held|returned|partial|none
  deposit_returned_at TIMESTAMPTZ
  deposit_notes VARCHAR(500)
```

## Endpoints (fase crítica) — router `operations.py` (`/admin/*`)

- `GET/POST/PATCH/DELETE /admin/property-relations` — CRUD relacional de vínculos (reemplaza el JSONB; `relate-client` pasa a escribir acá también).
- `GET/POST/DELETE /admin/contracts/{id}/guarantors` — garantes del contrato.
- `GET/POST/PATCH/DELETE /admin/sales` — ventas.
- `POST /admin/operations/backfill` — migra `extra_data.property_relations` y `buyer_id`/`tenant_id` a `property_relations`.

## Cambios en endpoints existentes

- `relate-client` (admin.py): además del JSONB (compat), escribe una fila en `property_relations`, acepta `agent_id`, y si `relation=tenant` **asegura un contrato `draft`** (property+tenant) en vez de solo flipear estado.
- `create_contract`/`update_contract` (cobranzas.py): aceptan `agent_id` y los campos de depósito.

---

## Estado de ejecución (actualizado 2026-06-17)

### Backend — críticos C1–C5
- [x] Modelos ORM nuevos (`operations.py`): `PropertyRelation`, `Guarantor`, `Sale`.
- [x] `ensure_operations_schema()` — DDL en transacción aislada + ALTERs idempotentes
      (corren SIEMPRE y cada uno en su propia transacción).
- [x] Router `operations.py` + registro en `main.py` (app + compat `/api`).
- [x] `relate-client` escribe en `property_relations` + `agent_id` + crea contrato `draft`.
- [x] `create_contract`/`update_contract` con `agent_id` + depósito; serializer los devuelve.
- [x] Backfill ejecutado en prod: `POST /admin/operations/backfill` (migró 2 vínculos JSONB→relacional).

### Frontend — críticos C1–C5
- [x] `LinkClientProperty`: dropdown "Agente asignado" (miembros de equipos) → `agent_id`.
- [x] `Cobranzas` (ContractEditor): dropdown de agente + depósito (monto/estado); pill "Borrador".
- [x] `GuarantorsPanel`: alta/baja/listado de garantes por contrato.
- [x] `api.js`: hooks `useSales*`, `useGuarantors*`, `agent_id` en `useRelateClientToProperty`.

### Visitas — C5 extendido a `appointments`
- [x] `appointments.agent_id` (columna) + create/update/serializer.
- [x] `EventEditor`/`EventPopover`: select de agente real (antes nombres mock hardcodeados).
- [x] `api.js`: `toEvent`/`fromEvent` mapean `agent_id`.

### Fixes de raíz descubiertos y resueltos en el camino
- [x] 500 al vincular: tabla `activity_log` no existía (la migración monolítica abortaba en
      `messages.id` UUID). Ver memoria `startup-migration-single-txn-landmine`.
- [x] `log_activity`/`log_activity_async` envueltos en SAVEPOINT (`begin_nested`) para no
      envenenar el commit del endpoint.
- [x] `agent_id` como **referencia blanda**: se dropearon las FK `*_agent_id_fkey` porque el
      dropdown puede mandar el id del dueño (que no es fila de `tenant_members`) → la FK dura
      tiraba 500.

### Pendiente
- [ ] Validación en vivo de la atribución de agente en visitas (esperando deploy de `eed3537`).
- [ ] Importantes (fase 2): IPC automático/ICL, recibos/liquidación PDF, dunning, co-partes.
- [ ] Menores (fase 3): estados de propiedad finos, embudo comercial, tope punitorio, USD.

### Commits clave (rama main)
`14ee3fd` savepoint log_activity · `744cc51` fix messages.id migración · `f116b32` modelo
operaciones C1–C5 · `2ebdc8b` UI operaciones · `1d6be33` agente en visitas · `eed3537`
agent_id soft ref.
```

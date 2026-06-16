---
id: 02
title: "Propiedades — atajo 'Vincular inquilino' en el encabezado del drawer"
status: pending
priority: medium
area: frontend
files:
  - dashboard/src/Properties.jsx     # PropertyDrawer (header + bloque asignación)
  - dashboard/src/api.js             # useRelateClientToProperty
endpoints:
  - POST /admin/properties/{prop_id}/relate-client   # YA EXISTE, se reutiliza
depends_on: []
shares_with: ["01"]   # mismo flujo de vínculo → componente común LinkClientProperty
skills: ["react-patterns", "accessibility"]
agents: ["react-reviewer"]
---

# Plan 02 — Propiedades: atajo "Vincular inquilino" arriba

## 1. Objetivo
Agregar un botón **atajo** en el encabezado del drawer de propiedad (junto a Eliminar/Editar/Agendar visita) que abra el flujo de asignación existente **preseleccionado en `tenant` (Inquilino)**, sin tener que scrollear hasta el bloque inferior.

## 2. Contexto necesario (estado actual real)

**Encabezado del drawer** — `Properties.jsx` líneas **137-141**:
```jsx
<span style={{marginLeft:'auto',display:'flex',gap:6}}>
  <Button kind="danger"    size="sm" icon="trash"    onClick={...}>Eliminar</Button>
  <Button kind="secondary" size="sm" icon="edit"     onClick={...}>Editar</Button>
  <Button kind="primary"   size="sm" icon="calendar" onClick={() => onAgenda(property)}>Agendar visita</Button>
</span>
```

**Bloque de asignación existente** — `Properties.jsx` líneas **195-277** ("Asignar comprador / inquilino"):
- Estado local relevante ya presente: `assignOpen` (bool), `assignRelation` (línea **91**, default según `operation==='rent' ? 'tenant' : 'buyer'`), `assignSearch`.
- Cuando NO hay vínculo, muestra botón "Vincular cliente" → al abrir, chips `buyer/tenant/interested` (línea 241) + buscador + lista que llama `relateClient.mutate({prop_id, client_id, relation: assignRelation, update_status:true})`.
- Cuando YA hay comprador/inquilino, muestra la tarjeta con menú editar/desvincular (líneas 204-230).

## 3. Plan secuencial
- [ ] Agregar botón "Vincular inquilino" (icon `user-plus`) en el header (137-141).
- [ ] Su `onClick` debe: `setAssignRelation('tenant')` + `setAssignOpen(true)` y hacer **scroll** al bloque de asignación (usar un `ref` en el `detail-block` de línea 195 y `scrollIntoView({behavior:'smooth'})`).
- [ ] Si la propiedad **ya tiene inquilino** (`tenantClient`, línea 106), el botón debe llevar a la tarjeta existente (scroll) en lugar de abrir alta — evitar estado inconsistente de doble inquilino.
- [ ] Coordinar con Plan 01: si se extrae `LinkClientProperty.jsx`, este atajo solo setea props (`fixedRelation='tenant'`, `open=true`) del componente común.
- [ ] Accesibilidad: `aria-label` claro; foco al buscador al abrir (ya hay `autoFocus` en el input de línea 238-239).

## 4. Criterios de aceptación
- El botón aparece arriba y, al tocarlo, el flujo de asignación queda visible y con "Inquilino" preseleccionado.
- No permite crear un segundo inquilino si ya existe uno; en ese caso lleva a la tarjeta actual.
- Vincular desde el atajo cambia el estado de la propiedad a `rented` (comportamiento ya provisto por el backend cuando `update_status:true`).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns`, `accessibility`.
- **Agentes:** `react-reviewer` (revisar manejo de `ref`/scroll y que no se dupliquen estados con Plan 01).
- **MCP:** ninguno.
- **Workflow:** ejecutar idealmente **junto con Plan 01** para extraer el componente compartido en una sola pasada y revisar ambos diffs juntos.

## 6. Verificación
- `npm run lint`.
- Manual: propiedad sin inquilino (abre alta preset tenant) y con inquilino (lleva a tarjeta).
- Diff review `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Pendiente de ejecución.

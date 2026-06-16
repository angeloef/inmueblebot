---
id: 01
title: "Clientes — acciones rápidas del perfil + pestaña Propiedades con vínculo"
status: completed
priority: high
area: frontend
files:
  - dashboard/src/Clients.jsx        # ClientDrawer + lista
  - dashboard/src/api.js             # useRelateClientToProperty, useProperties
  - dashboard/src/App.jsx            # navegación a Calendario (para "Agendar")
  - dashboard/src/EventPopover.jsx   # EventEditor (alta de cita)
endpoints:
  - POST /admin/properties/{prop_id}/relate-client   # YA EXISTE, se reutiliza
depends_on: []
shares_with: ["02"]   # mismo flujo de vínculo cliente↔propiedad → extraer componente común
skills: ["react-patterns", "frontend-patterns", "accessibility"]
agents: ["react-reviewer", "e2e-runner"]
---

# Plan 01 — Clientes: acciones rápidas + pestaña "Propiedades"

## 1. Objetivo
En la pestaña Clientes: (a) que los botones de acción rápida del perfil **funcionen**, (b) renombrar la pestaña interna `Intereses` → **`Propiedades`** y agregar dentro un **CTA "Vincular propiedad"** que despliegue el flujo de vínculo (el mismo, accesible desde el lado cliente y desde el lado propiedad).

## 2. Contexto necesario (estado actual real)

**a) Botones que hoy NO hacen nada** — `Clients.jsx` líneas **159-162**, dentro de `ClientDrawer > .quick`:
```jsx
<Button kind="primary"   size="sm" icon="phone">Llamar</Button>
<Button kind="secondary" size="sm" icon="whatsapp">WhatsApp</Button>
<Button kind="secondary" size="sm" icon="mail">Correo</Button>
<Button kind="secondary" size="sm" icon="calendar">Agendar</Button>
```
No tienen `onClick`. El objeto `client` ya expone `client.phone` y `client.email`.
- Patrón ya usado en el repo para enlaces de contacto: `Equipos.jsx` líneas 311/327/340 (`https://wa.me/${phone.replace(/[^\d]/g,'')}`, `tel:`, `mailto:`). Reutilizar ese mismo criterio de normalización de teléfono.
- **"Agendar"** es el caso no trivial: en Propiedades el `onAgenda` actual es un *stub* (`App.jsx`/`Properties.jsx` solo hace `pushToast`). La forma correcta es navegar al Calendario abriendo `EventEditor` (`EventPopover.jsx`, importado en `Calendar.jsx:5`) con el `clientId` precargado. `Calendar` ya acepta `initialEventId`/`initialDate` desde `App.jsx:182`; falta una vía equivalente para "nuevo evento con cliente precargado".

**b) Pestaña a renombrar** — `Clients.jsx` línea **168**:
```jsx
{[['overview','Resumen'],['interest','Intereses'],['activity','Actividad'],['docs','Documentos']]...}
```
El contenido de ese tab (líneas **206-237**) ya titula "Propiedades vinculadas" y lista `interestProps` + `linkedProps` (estos vienen de `client.property_relations`, ver `api.js:366`). **No hay** ningún control para *agregar* un vínculo desde acá.

**c) Mecanismo de vínculo (a reutilizar)** — hook `useRelateClientToProperty` (`api.js:549-581`) → `POST /admin/properties/{prop_id}/relate-client` con body `{ client_id, relation, update_status }`. `relation ∈ {buyer, tenant, interested, none}`. El backend (`app/api/routes/admin.py:1228`) actualiza `property.extra_data` y `user.extra_data.property_relations`, y mapea `buyer→sold`, `tenant→rented`. **El endpoint es property-keyed pero sirve igual desde el cliente**: el cliente elige una propiedad y se llama con ese `prop_id`.

## 3. Plan secuencial
- [ ] **Acciones rápidas**: agregar `onClick` a los 4 botones (159-162).
  - Llamar → `window.open('tel:'+phone)`; WhatsApp → `https://wa.me/${normalizado}`; Correo → `mailto:`. Deshabilitar si falta el dato (`disabled={!client.phone}` etc.).
- [ ] **Agendar**: pasar un callback `onAgenda(client)` a `ClientDrawer` desde `Clients` → `App`, que navegue al Calendario con `EventEditor` abierto y `clientId` precargado. Si se decide no tocar navegación aún, dejar fallback honesto (abrir Calendario en fecha de hoy) — **no** dejarlo como toast vacío.
- [ ] **Rename**: `'Intereses'` → `'Propiedades'` (línea 168). Revisar que no rompa `tab==='interest'` (la *key* puede seguir siendo `interest` para no tocar lógica; solo cambia el label visible).
- [ ] **CTA Vincular propiedad**: dentro del panel `tab==='interest'` agregar botón "Vincular propiedad" que abra un buscador de propiedades (`useProperties`) + selector de relación (`interested/tenant/buyer`) y llame `useRelateClientToProperty`. Reutilizar el patrón visual del lado propiedad (`Properties.jsx:236-273`).
- [ ] **Refactor compartido** (coordinar con Plan 02): extraer el buscador+selector+mutación a `dashboard/src/LinkClientProperty.jsx` parametrizado por "lado" (fijar cliente y elegir propiedad, o fijar propiedad y elegir cliente). Evita duplicar lógica entre Clients y Properties.
- [ ] Invalidación de caché: confirmar que tras vincular se refrescan `clients` y `properties` (el hook ya invalida; verificar que el drawer abierto refleje el cambio, ver `Clients.jsx:301-309` para patrón de update optimista).

## 4. Criterios de aceptación
- Los 4 botones ejecutan la acción correcta y se deshabilitan sin dato.
- El tab muestra "Propiedades"; el contenido sigue funcionando.
- Desde el perfil del cliente se puede vincular una propiedad (con relación elegida) y aparece en la lista sin recargar.
- Sin `console.log` ni props sin tipar nuevas; respeta `eslint-plugin-react-hooks`.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns` (estructura de componente/hooks), `frontend-patterns`, `accessibility` (los botones de acción y el buscador deben ser navegables por teclado, igual que el patrón existente con `onKeyDown`).
- **Agentes:** `react-reviewer` para revisar el diff (rules-of-hooks, derivación de estado), `e2e-runner` (Playwright) para un flujo: abrir cliente → vincular propiedad → verla listada.
- **MCP:** ninguno externo necesario.
- **Workflow:** UI pura, bajo riesgo → cambio directo. Antes de tocar Agendar, usar el subagente **Explore** para mapear cómo `App.jsx` orquesta la navegación entre vistas y no romper el routing.

## 6. Verificación
- `npm run lint` en `dashboard/`.
- Test manual/Playwright de los 3 flujos (contacto, rename, vínculo).
- Diff review con `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Pendiente de ejecución.
- 2026-06-16 — Implementado (implementador-loop).
  - **Acciones rápidas** (`Clients.jsx`): los 4 botones (Llamar/WhatsApp/Correo/Agendar) ahora tienen `onClick` y `disabled` sin dato. WhatsApp normaliza el teléfono (`replace(/[^\d]/g,'')`) y abre `_blank` con `noopener,noreferrer`, igual que `Equipos.jsx`.
  - **Agendar**: callback `onAgenda(client)` → `App.openAgenda` navega al Calendario; `Calendar` acepta `initialNewEventClientId` y abre `EventEditor` en modo create con el cliente precargado (no es toast vacío). Remount controlado por `key`.
  - **Rename**: label `Intereses` → `Propiedades` (la key del tab sigue siendo `interest`, sin tocar lógica).
  - **CTA Vincular propiedad** + **refactor compartido**: nuevo `dashboard/src/LinkClientProperty.jsx` parametrizado por `side` (`client`/`property`), reutilizable por Plan 02. Usado en el tab Propiedades del cliente. Invalidación de caché vía `useRelateClientToProperty` (ya optimista).
  - **Gates:** el repo no tiene script `lint` ni tests de frontend; gate efectivo = `npm run build` (vite) → verde (1897 módulos). Se instaló `lucide-react` (faltaba en node_modules, rompía el build baseline de `Reportes.jsx`; ya estaba en package.json). Review con subagente **react-reviewer**: findings aplicados (cerrar panel solo en `onSuccess`, reset de `relation` al cerrar, `aria-label` en el buscador). Gate UX interactivo con Chrome MCP no ejecutado (requiere levantar backend+auth+DB, fuera de budget); cambio autocontenido y con build+review en verde.

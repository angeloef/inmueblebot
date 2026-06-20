---
id: 17
title: "Configuración — reconstruir la UI con el layout del handoff (rail de 8 secciones)"
status: completed
priority: high
area: frontend
files:
  - dashboard/src/Config.jsx        # REEMPLAZAR por el layout de 8 secciones con rail
  - dashboard/src/useTheme.js       # tema claro/oscuro (ya existe, reusar para el toggle)
  - dashboard/src/api.js            # hooks: me, usage, change-password, update-profile, self-settings, team, tenants, billing
  - dashboard/src/Primitives.jsx    # Button/Icon/Pill/useFocusTrap
  - dashboard/src/styles.css        # estilos del layout (tokens del design system)
design_handoff:
  - "Claude interface layout-handoff/claude-interface-layout/project/Configuración.dc.html"   # diseño primario (leer completo)
  - "Claude interface layout-handoff/claude-interface-layout/project/_ds/.../colors_and_type.css"  # tokens color/tipografía
depends_on: ["16"]
decisiones:
  alcance: "solo la superficie de Configuración; el resto del dashboard queda igual"
  tema: "2 opciones (claro/oscuro) reusando useTheme app-wide; NO el 3-way system del mock"
  whatsapp: "PLACEHOLDER (estado derivado + botón deshabilitado/'próximamente'); embedded signup = plan futuro"
skills: ["react-patterns", "frontend-patterns", "accessibility", "data-viz"]
agents: ["react-reviewer"]
---

# Plan 17 — Reconstruir Configuración con el layout del handoff

## 1. Objetivo
Recrear **fielmente** el diseño del handoff (`Configuración.dc.html`) en React, reemplazando el `Config.jsx` actual por un layout de **rail izquierdo + 8 secciones**, búsqueda, tema claro/oscuro, barra "cambios sin guardar" y estados skeleton/error — **cableado a nuestro backend** (existente + plan 16). Solo se rediseña Configuración.

## 2. Contexto necesario (estado actual real)
- **Diseño primario** (leer completo, top-to-bottom): `Claude interface layout-handoff/.../Configuración.dc.html`. Es un prototipo HTML/CSS/JS (no copiar su estructura interna; **replicar el output visual** en React). Trae tokens en su `<style>` (`.cfg{--page-bg...}` claro + `[data-theme="dark"]`) y un design-system CSS (`_ds/.../colors_and_type.css`). Reusar esos tokens/colores/tipografía (Inter/Manrope).
- **`Config.jsx` actual** ya implementa varias piezas a reaprovechar como **lógica/hooks** (no su UI): `TenantsSection` (tenants CRUD, `useTenants`), `PlanSection` (plan 09), `RouterSegmented`/`active_router` (`useUpdateTenantSettings`), `LimitBar`, `agent_whatsapp`. Reusar los hooks; rehacer la presentación según el mock.
- **Backend disponible**: `/auth/me` (full_name, email, email_verified, auth_methods, tier/limits/features, subscription, branches), `team.py` (members/roles/invite), `admin/tenants` (superadmin), `tenant_settings.active_router`, billing (08/09). **Plan 16** agrega: `change-password`, `PATCH perfil`, self-settings del dueño, `GET /usage`, `whatsapp_status`.
- **Tema**: `useTheme.js` (light/dark, `data-theme` en `documentElement`, persiste en localStorage). El mock muestra system/light/dark → **reducir a claro/oscuro** (2 opciones) que matchean el dark/light real de la app, app-wide.

## 3. Plan secuencial — mapa sección → datos

### Estructura general
- [ ] Layout: rail izquierdo (256px) con buscador + nav de secciones; main centrado (~780px) con la sección activa; **mobnav** (buscador + `<select>`) en ≤860px (el mock lo trae). Estados: **skeleton** (carga), **error** (con reintento), **búsqueda** (filtra nav + lista de resultados, del `idxRaw` del mock).
- [ ] **Tema claro/oscuro**: toggle (2 opciones) que usa `useTheme`; aplicar tokens del mock. Verificar que dark se vea bien (reusa el dark app-wide existente).
- [ ] **Barra "cambios sin guardar"** sticky: aparece con `dirty`, botones Descartar/Guardar (patrón del mock). Cada sección editable marca `dirty` y persiste al Guardar.
- [ ] **Gating por rol**: secciones "Sistema" e "Inmobiliarias" (marcadas **Admin** en el mock) visibles solo para admin/superadmin (usar `me.role`/`features`). Para no duplicar el /superadmin existente, "Inmobiliarias" puede reusar el CRUD actual (`useTenants`) o enlazar a `/superadmin` — decidir en review.

### Secciones (cableado)
- [ ] **General**: avatar (inicial + color → `PATCH perfil`, plan 16), nombre completo (`full_name` → `PATCH perfil`), apariencia (tema, `useTheme`).
- [ ] **Cuenta**: email (read-only, `me.email`), email verificado (`me.email_verified`), métodos de login (`me.auth_methods`), **cambiar contraseña** (`POST /auth/change-password`, plan 16), cerrar sesión (`/auth/logout`).
- [ ] **Mi inmobiliaria**: nombre comercial (`display_name`), horario (`business_hours`), WhatsApp del agente (`agent_whatsapp`), zona horaria (`timezone`) → **self-settings** (plan 16). **Estado de WhatsApp**: pill derivado (`me.whatsapp_status`) + botón **"Conectar WhatsApp" PLACEHOLDER** (deshabilitado/"próximamente").
- [ ] **Facturación**: reusar `PlanSection`/hooks de billing (planes 08/09): banner trial/active/past_due + grilla Básico/Pro/Enterprise (`/billing/plans`) + acciones (subscribe / gestionar / hablar con ventas). Re-skin al mock.
- [ ] **Uso**: barras de `GET /usage` (plan 16): Propiedades, Conversaciones del mes, Miembros — color por umbral (≥80% rojo, ≥50% ámbar) y nota "cerca del límite", como el mock.
- [ ] **Equipo**: tabla de `team.py` (members + rol Propietario/Administrador/Agente) + invitar (`POST /team/members`) + estado vacío (del mock). Quitar miembro (`DELETE`).
- [ ] **Sistema** (Admin): segmented V1/V2/V3 → `active_router` (`useUpdateTenantSettings`) + descripción por router (texto del mock).
- [ ] **Inmobiliarias** (Admin/superadmin): lista de tenants (`useTenants`) con WA/router/estado + editar + nueva. Reusar la lógica de `TenantsSection` con la UI del mock.

## 4. Criterios de aceptación
- Configuración se ve como el mock (rail + 8 secciones + búsqueda + save-bar + skeleton/error), en claro y oscuro.
- Cada sección lee/escribe contra el backend real: editar perfil, cambiar contraseña, editar datos de la inmobiliaria, ver uso, gestionar equipo, cambiar router, ver/gestionar facturación, y (admin) tenants.
- WhatsApp: estado real + botón placeholder (sin romper nada).
- Secciones Admin solo visibles según rol.
- Accesible (teclado, foco, `progressbar`/roles), sin `console.log`, rules-of-hooks; build verde.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns`, `frontend-patterns`, `accessibility`, `data-viz` (barras de uso).
- **Agentes:** **react-reviewer** (estado/hooks, dirty-state, gating por rol, dark mode).
- **MCP:** ninguno externo.
- **Workflow:** leer el `.dc.html` completo + el CSS del design system primero; reusar hooks existentes (no reescribir lógica); reemplazar `Config.jsx` por el nuevo layout; iterar el pixel-fit con Chrome MCP (claro y oscuro).

## 6. Verificación
- `npm run build`.
- **Chrome MCP** (gold standard): recorrer las 8 secciones en claro y oscuro; editar perfil/contraseña/inmobiliaria y ver el save-bar + persistencia; ver Uso con datos; equipo (invitar/quitar); router; facturación; búsqueda filtrando; responsive (mobnav). Screenshots por sección + consola sin errores. Confirmar que el WhatsApp connect es placeholder y no rompe.
- `react-reviewer` sobre el diff. Comparar contra el mock para fidelidad visual.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado desde el handoff. Decisiones: solo Configuración; tema claro/oscuro (2 opc.) app-wide vía useTheme; WhatsApp connect = placeholder (embedded signup futuro). Depende de 16 (change-password/perfil/self-settings/usage). Reusa hooks de Config.jsx actual y de planes 08/09.

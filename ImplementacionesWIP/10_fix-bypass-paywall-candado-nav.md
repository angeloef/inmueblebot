---
id: 10
title: "Fix bypass de paywall — gating real de vistas premium (candado en nav, sin entrar)"
status: completed
priority: critical
area: frontend
files:
  - dashboard/src/Shell.jsx     # Sidebar (items 307-318) + UpgradeModal (262)
  - dashboard/src/App.jsx       # render de vistas (216-235) + listener subscription:required (80-86)
  - dashboard/src/auth.jsx      # account/me expone features (plan 08)
depends_on: []
relacionado: ["08", "09"]   # 08 expone me.features/tier; 09 dejó el modal pero sin bloqueo de sección
skills: ["react-patterns", "accessibility"]
agents: ["react-reviewer", "security-reviewer"]
---

# Plan 10 — Fix bypass de paywall (candado en nav, sin entrar)

## 1. Objetivo
Cerrar el agujero por el que se puede **operar features premium gratis**: hoy la vista premium se renderiza siempre y el popup de upgrade es descartable (clic afuera → seguís operando). Decisión UX: **ítem de nav con candado que NO entra a la vista** — al clickearlo abre directo el modal de upgrade. Más un **guard de ruta** como defensa en profundidad.

## 2. Contexto necesario (estado actual real)
- **Bug raíz** — `App.jsx:227`: `{active === 'cobranzas' && <Cobranzas />}` (y `website`/`documents`/`reportes`) se renderizan **sin chequear el plan**. El `UpgradeModal` (`Shell.jsx:262`) cierra con backdrop `onClick={onClose}` → al cerrarlo, la sección de atrás queda operable. El backend devuelve 402 en algunos endpoints, pero la UI deja operar lo que no pega al server.
- **Nav** — `Shell.jsx` `Sidebar` (items 307-318): lista estática de `{id, icon, label}`; `onClick={() => handleNav(it.id)}` siempre navega. Recibe `account` (tiene `features`/`tier` del plan 08).
- **Catálogo de features** (plan 08, expuesto en `me.features`): `cobranzas`, `website`, `documents`, `exec_reports`, `exports`, etc. **Mapeo vista→feature** necesario:
  - `cobranzas` → feature `cobranzas` (tier profesional)
  - `website` → `website` (profesional)
  - `documents` → `documents` (enterprise)
  - `reportes`/exports en headers → `exec_reports`/`exports` (enterprise)
  Definir este mapa como **dato** (un solo lugar), no inline disperso.
- **Modal ya escucha** `subscription:required` (`App.jsx:80-86`) → reusarlo: el candado del nav dispara ese mismo evento con `{required:<tier>, feature:<f>}`.

## 3. Plan secuencial
- [ ] **Mapa vista→feature** en un módulo compartido (p. ej. `dashboard/src/featureGates.js`): `{ cobranzas:'cobranzas', website:'website', documents:'documents', reportes:'exec_reports' }`. Helper `hasFeature(account, feature)` (si no hay features → tratar como sin acceso, fail-closed).
- [ ] **Sidebar (Shell.jsx)**: cada item con `feature` definido y NO presente en `account.features` → renderizar con **ícono de candado** + `aria-disabled`/`title="Disponible en plan superior"`, y `onClick` que **dispara** `window.dispatchEvent(new CustomEvent('subscription:required', {detail:{required, feature}}))` en vez de `handleNav`. No navegar.
- [ ] **Guard de ruta (App.jsx)** — defensa en profundidad para URL directa: si `active` es una vista premium sin feature, **no** montar el componente operable; mostrar un `FeatureLock` (placeholder con candado + CTA "Ver planes") o redirigir a `dashboard`. Así, aunque entren por `/dashboard/cobranzas` a mano, no hay UI operable.
- [ ] **UpgradeModal**: mantener descartable (está bien), porque ya **no** queda nada operable detrás. Confirmar que al cerrar el modal el usuario queda en una vista no-premium (no en la sección bloqueada).
- [ ] Revisar headers con acciones premium embebidas (ExportCsv en Clientes/Cobranzas, Reportes) → ocultar/lockear el botón si falta la feature (mismo helper).

## 4. Criterios de aceptación
- Un usuario sin `cobranzas` ve el ítem con candado; al clickearlo aparece el modal de upgrade y **no** navega ni puede operar Cobranzas.
- Entrar por URL directa a una vista premium sin acceso **no** muestra UI operable (FeatureLock o redirect).
- Cerrar el modal (clic afuera/Esc) no deja ninguna sección premium operable.
- El gating visual deriva de `me.features` (un solo mapa); el backend (plan 08) sigue siendo el enforcement real (402).
- `security-reviewer` confirma que no queda camino de operación gratis en el cliente.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns`, `accessibility` (candado con `aria-disabled`, foco, label claro; no romper navegación por teclado).
- **Agentes:** **react-reviewer** (gating sin romper rules-of-hooks; estado derivado), **security-reviewer** (que el bypass quede realmente cerrado en el cliente, fail-closed sin features).
- **MCP:** ninguno.
- **Workflow:** mapa de features → lock en nav → guard de ruta → headers premium. Probar con cuenta Básico (sin cobranzas) y con Pro.

## 6. Verificación
- `npm run build`.
- **Chrome MCP** (clave): login Básico → Cobranzas con candado, clic → modal, no entra; intentar `/dashboard/cobranzas` directo → FeatureLock; cerrar modal → nada operable. Login Pro → Cobranzas funciona normal. Screenshots + consola sin errores.
- `react-reviewer` + `security-reviewer` sobre el diff.

## 7. Bitácora (append-only)
- 2026-06-17 — Plan creado. Prioridad crítica (bypass de cobro). Decisión UX: candado en nav que abre upgrade sin entrar + guard de ruta. Depende de `me.features` del plan 08 (ya desplegado).
- 2026-06-18 — Implementado. Archivos: `featureGates.js` (nuevo mapa único), `Shell.jsx` (candado + aria-label descriptivo), `App.jsx` (FeatureLock + guard de ruta), `styles.css` (sb-item--locked, feature-lock). Gates: build ✓, react-reviewer APPROVE (2 MEDIUMs a11y corregidos). SHA en el commit de este push.

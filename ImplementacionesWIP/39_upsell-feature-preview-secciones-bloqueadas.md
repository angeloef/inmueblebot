---
id: upsell-feature-preview-secciones-bloqueadas
status: completed
priority: P2
area: Frontend (gating/upsell)
files:
  - dashboard/src/Shell.jsx
  - dashboard/src/featureGates.js
endpoints: []
depends_on: []
related_areas: [10_fix-bypass-paywall-candado-nav, 22_gating-candado-enterprise-audit, 20_hablar-con-ventas-enterprise]
skills: [frontend-design-direction, make-interfaces-feel-better, accessibility]
agents: [react-reviewer, a11y-architect]
---

# 39 — Pestaña-mockup de upsell en secciones bloqueadas por plan

## 1. Objetivo
Hoy navegar a una sección no incluida en el plan solo dispara el `UpgradeModal` (un popup) y no
deja entrar. Mantener ese popup, pero además: al navegar a una sección bloqueada, mostrar una
**página real de preview** que explique claro y conciso qué problema resuelve esa sección, qué
funciones tiene, con un CTA fuerte a cambiar de plan. Componente **genérico templado** (decisión
del dueño), alimentado por feature.

## 2. Contexto necesario
- `dashboard/src/featureGates.js` — `VIEW_GATES` mapea vista → `{feature, required}`
  (cobranzas, website, documents, reportes). `hasFeature(account, feature)` y
  `dispatchUpgradeEvent`. Acá se agrega el contenido de marketing por feature
  (título, problema que resuelve, lista de funciones, screenshot/ilustración).
- `dashboard/src/Shell.jsx:337-346` — `handleNav(id)`: si la vista está gateada, hoy hace
  `dispatchUpgradeEvent(...)` y `return` (no navega). Cambiar para que **navegue a la página de
  preview** en vez de no hacer nada (o además del modal). Ver también `:360-377` donde pinta el
  item con `sb-item--locked` + `lock`.
- `Shell.jsx:278` `UpgradeModal` — reusar su CTA "Ver planes"/`onGoToPlans`. No duplicar el flujo
  de checkout; el preview enlaza a la sección de planes existente.
- Enterprise = "Hablar con ventas" (no self-serve) — ver plan 20; el CTA debe respetar eso cuando
  `required==='enterprise'`.

## 3. Plan secuencial
- [ ] Crear `<FeaturePreview feature required />` (un solo componente) que renderice: hero con título + 1 frase de problema, 3-4 bullets de funciones, screenshot/ilustración, y CTA según `required` (Ver planes / Hablar con ventas).
- [ ] Mover el contenido por feature a `featureGates.js` (o un `featurePreviews.js` adyacente): para cobranzas, website, documents, reportes.
- [ ] En `handleNav`: si la vista está bloqueada, navegar a la preview (renderizar `<FeaturePreview>` como contenido de esa ruta) en lugar del dead-end actual. Decidir si el modal sigue apareciendo o solo la página (el dueño quiere la página "bien pensada"; el modal puede quedar para clicks desde otros lados).
- [ ] Cuidar accesibilidad (headings, foco, contraste light+dark) y que no reintroduzca el bypass del plan 10 (la página es solo marketing; no monta la feature real).

## 4. Criterios de aceptación
- Navegar a cada sección bloqueada muestra una página de preview con problema + funciones + CTA, no un dead-end ni la feature real.
- El CTA lleva a planes (o a ventas si Enterprise).
- Un componente genérico cubre las 4 secciones (DRY); agregar una nueva feature = agregar datos, no UI nueva.
- No se puede usar la feature real desde la preview (sin bypass).
- Light y dark se ven intencionales.

## 5. Skills / MCP / Workflow AI
`/ponytail full`. `frontend-design-direction` + `make-interfaces-feel-better` para que no parezca template. `accessibility`/`a11y-architect` y `react-reviewer` al cerrar.

## 6. Verificación
- Chrome MCP en Docker: login con plan que no incluya cada sección; navegar y screenshot light+dark.
- Confirmar que el plan 10 (no-bypass) sigue intacto.

## 7. Bitácora (append-only)
- 2026-06-20: plan creado. Hoy `handleNav` bloquea con modal y no navega. Decisión: agregar página de preview genérica templada alimentada desde `featureGates.js`, CTA a planes/ventas, sin reabrir el bypass del plan 10.
- 2026-06-20: IMPLEMENTADO + SHIPPED. Reaprovechado el guard existente `FeatureLock` (App.jsx, ya
  renderizado en lugar de la feature real cuando `!hasFeature` → plan 10 intacto) reescribiéndolo como
  `FeaturePreview` genérico, data-driven: contenido por feature en `featureGates.js` → `FEATURE_PREVIEWS`
  (cobranzas/website/documents/exec_reports: título, problema 1 frase, 3-4 bullets). CTA según `required`:
  enterprise → "Hablar con ventas", resto → "Ver planes"; ambos van a `goToPlans()` (settings/facturación,
  donde vive el modal de ventas del plan 20). `handleNav` (Shell.jsx) ahora navega a la vista gateada (antes
  dead-end con modal) → se ve la página. Fix de paso: el botón viejo usaba `btn--primary btn--sm` (clases
  inexistentes, sin estilo) → ahora `btn btn-primary`. CSS nuevo `.feat-preview*` con tokens (light+dark
  automáticos). Verificación Playwright sobre Docker (tras `docker restart` por staleness de Vite HMR en
  Windows): /cobranzas y /documentos renderizan la preview (no la feature real), badge+bullets+CTA correctos,
  screenshots light+dark intencionales, enterprise muestra "Hablar con ventas". Errores de consola = 402/404
  preexistentes (suscripción inactiva del tenant), no del cambio. Build vite OK. `/ponytail full`: un solo
  componente genérico, sin UI nueva por feature; reusé el guard en vez de crear otra ruta. Commit+push.

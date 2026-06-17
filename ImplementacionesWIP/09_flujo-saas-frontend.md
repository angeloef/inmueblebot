---
id: 09
title: "Flujo SaaS en frontend — banner trial, manejo 402, checkout y sección de suscripción"
status: in_progress
priority: high
area: frontend
files:
  - dashboard/src/api.js            # interceptor (solo 401 hoy, línea 66) → agregar 402; hooks billing
  - dashboard/src/Shell.jsx         # planLabel (106) + banner global de trial
  - dashboard/src/Config.jsx        # sección "Plan y suscripción" (integrar acá)
  - dashboard/src/auth.jsx          # useAuth/me expone subscription (status/plan/trial_ends_at)
  - dashboard/src/Primitives.jsx    # Button/modal/Pill reutilizables
endpoints_existentes:
  - POST /billing/subscribe   # → init_point (redirect MercadoPago)
  - GET  /billing/status      # estado de suscripción
  - GET  /billing/plans       # catálogo de tiers (lo agrega el plan 08)
  - GET  /auth/me             # subscription: status/plan/trial_ends_at (+ tier/limits/features del 08)
depends_on: ["08"]
decisiones_ux:
  paywall_402: "ambos (modal de upgrade ante la acción + bloqueo visual de la sección premium)"
  trial_banner: "barra global, aparece ≤7 días del fin, descartable por sesión"
  pagina_plan: "integrar en Config.jsx (no pestaña nueva)"
skills: ["react-patterns", "frontend-patterns", "accessibility"]
agents: ["react-reviewer", "e2e-runner"]
---

# Plan 09 — Flujo SaaS (frontend)

## 1. Objetivo
Construir el flujo SaaS visible para el usuario sobre el backend de tiers (plan 08): **banner de trial con countdown**, **manejo del 402** (modal de upgrade + bloqueo de secciones premium), y una **sección "Plan y suscripción" en Config** con estado, comparativa de tiers y botón de suscribir/gestionar (checkout MercadoPago; Enterprise → "Hablar con ventas").

## 2. Contexto necesario (estado actual real)
- **`useAuth`/`/auth/me`** ya expone `subscription` (`status`, `plan`, `trial_ends_at`) y —con el plan 08— `tier`, `limits`, `features`, `self_serve`. El banner y el gating visual salen de ahí sin pedir nada nuevo.
- **Interceptor `api.js` (línea 66)**: hoy maneja **solo 401** (refresh + `auth:expired`). **No hay manejo de 402.** Hay que sumar: ante 402, emitir `window.dispatchEvent(new CustomEvent('subscription:required', {detail: <body del 402>}))` para que un listener global abra el modal de upgrade con el tier requerido (el 402 del plan 08 trae `{reason, required, feature}`).
- **`Shell.jsx`**: `planLabel(me)` (línea ~106) ya pinta el nombre del plan en el menú de cuenta. `Shell` envuelve la app → lugar natural para la **barra global de trial** y para montar el **listener** de `subscription:required`.
- **`Config.jsx`**: es la pantalla de configuración del titular; ahí va la **sección "Plan y suscripción"** (no crear pestaña nueva, por decisión).
- **Checkout**: `POST /billing/subscribe` devuelve `init_point` → redirigir (`window.location.href = init_point`). MercadoPago vuelve a una URL de retorno → manejar estado `success/pending/failure` (mostrar toast + refrescar `/billing/status`).
- **Primitivos** (`Primitives.jsx`): reusar `Button`, `Pill`, patrón de modal + `useFocusTrap` (ya usado en otros drawers/modales).

## 3. Plan secuencial

### Infraestructura de datos
- [ ] Hooks en `api.js`: `useBillingStatus`, `useBillingPlans`, `useSubscribe` (POST → init_point). Tipar el shape del 402.
- [ ] Interceptor: agregar rama `response.status === 402` → `dispatchEvent('subscription:required', detail)`. No reintentar; no romper el flujo 401 existente.

### Banner de trial (global)
- [ ] Componente `TrialBanner` montado en `Shell`. Lee `subscription`: si `status==='trial'` y faltan **≤7 días** para `trial_ends_at`, muestra barra con **countdown** ("Te quedan N días de prueba") + CTA "Ver planes" (abre la sección de Config). **Descartable por sesión** (estado en memoria/`sessionStorage`-equivalente en React state del provider; recordar: no usar localStorage si está prohibido en este entorno — usar estado de sesión del front).
- [ ] Si `status` es `past_due/paused/cancelled` → variante de barra "reactivá tu plan" (sin countdown).

### Manejo 402 (ambos)
- [ ] **Modal de upgrade** global (listener de `subscription:required` en `Shell`): explica que la función es de un tier superior, muestra el tier requerido (`detail.required`) y CTA a la sección de planes / suscribir. Accesible (foco atrapado, Esc, aria).
- [ ] **Bloqueo de sección**: en las vistas premium (Reportes, Exports, Documentos, Cobranzas según tier) mostrar overlay con candado + CTA cuando `features` del usuario no incluye la feature. Derivar de `me.features` (plan 08), sin esperar al 402 (defensa visual proactiva). El 402 sigue siendo el backstop real.

### Sección "Plan y suscripción" en Config
- [ ] Estado actual: tier, precio, estado (trial/active/past_due), `trial_ends_at`/`current_period_end`, uso vs límites (de `limits`).
- [ ] **Comparativa de tiers** (de `GET /billing/plans`): tabla Básico/Pro/Enterprise con features y precios; resaltar el plan actual.
- [ ] **Acciones**: suscribir/cambiar a Básico o Pro → `useSubscribe(plan)` → redirect a `init_point`. **Enterprise** (`self_serve:false`) → botón "Hablar con ventas" (mailto/WhatsApp/landing, sin checkout). Si ya tiene suscripción activa → "Gestionar" (link al panel MP / cancelar según disponga el backend).
- [ ] Manejo del retorno de MP: detectar query params de retorno y mostrar toast + invalidar `billing-status`/`me`.

## 4. Criterios de aceptación
- En trial con ≤7 días, aparece la barra con countdown correcto, descartable por sesión.
- Un usuario sin el tier requerido: ve la sección premium bloqueada con candado y, si fuerza la acción, recibe el modal de upgrade (gatillado por el 402) con el tier correcto.
- Desde Config puede ver su plan, comparar tiers y lanzar el checkout (redirige a MercadoPago); Enterprise muestra "Hablar con ventas".
- Al volver de MP, la UI refleja el nuevo estado sin recargar manualmente.
- Sin `console.log`; respeta rules-of-hooks; sin `localStorage` (usar estado de sesión).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns`, `frontend-patterns`, `accessibility` (banner/modal/overlay navegables por teclado, foco atrapado, `aria-live` para el countdown).
- **Agentes:** **react-reviewer** (interceptor sin romper 401, hooks, foco/aria), **e2e-runner** (flujo: trial banner → intentar feature premium → modal → ir a Config → checkout redirect).
- **MCP:** ninguno externo (el redirect a MercadoPago se valida hasta el `init_point`).
- **Workflow:** datos+interceptor → banner → 402 (modal+lock) → Config. Probar el 402 forzando una cuenta Básico contra una ruta Pro (depende de 08 desplegado en el entorno de test).

## 6. Verificación
- `npm run build` (no hay script lint/test de frontend; build es el gate efectivo, ver bitácora de planes 01/02).
- **Chrome MCP** (gold standard de este plan): login con cuenta en trial → ver banner+countdown; login Básico → sección premium bloqueada + modal al forzar acción; Config → comparativa de tiers + click suscribir llega al `init_point` de MP; screenshots y consola sin errores.
- Coherencia: el tier mostrado en Config == el de `/auth/me`.
- `react-reviewer` sobre el diff (interceptor + Shell + Config).

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Depende de 08 (catálogo/tier/402 estructurado). Recordatorio: este entorno prohíbe localStorage en artefactos; el "descartar por sesión" del banner usa estado de sesión del front, no localStorage.

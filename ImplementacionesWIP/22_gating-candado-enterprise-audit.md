---
id: 22
title: "Gating — audit & fix: pestañas bloqueadas con candado incluso en cuentas Enterprise"
status: completed
priority: high
area: frontend+backend
files:
  - dashboard/src/featureGates.js   # mapa vista→feature (plan 10)
  - dashboard/src/Shell.jsx         # candado en nav (plan 10)
  - dashboard/src/App.jsx           # guard de ruta (plan 10)
  - app/services/plans.py           # catálogo: features por tier (plan 08)
  - app/api/routes/auth.py          # /me expone features/tier
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker con cuenta Enterprise y otra Básico."
skills: ["react-patterns", "python-testing", "accessibility"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 22 — Audit del gating (Enterprise no debería ver candados)

## 1. Objetivo
Corregir que **pestañas premium aparecen bloqueadas con candado incluso dentro de una cuenta Enterprise** (que debería tener acceso a todo). Auditar la cadena features→tier→UI y arreglar el origen.

## 2. Contexto necesario (estado actual real)
- Plan 10 introdujo `featureGates.js` (mapa vista→feature) + candado en `Shell.jsx` + guard en `App.jsx`, derivando de `me.features`.
- Plan 08 definió el catálogo `plans.py` (features por tier). **Enterprise debe incluir todas las features.**
- **Hipótesis del bug** (a confirmar): (a) el catálogo no marca todas las features para Enterprise, o (b) `/auth/me` no devuelve `features` completas para el tier del usuario, o (c) `featureGates`/`hasFeature` no contempla un caso (p. ej. org/branch o tier alias). Auditar de punta a punta.

## 3. Plan secuencial
- [ ] **Audit**: con una cuenta Enterprise real, inspeccionar `/auth/me` → `tier`/`features`. Confirmar qué features faltan vs el catálogo.
- [ ] **Fix backend** (si aplica): en `plans.py`, Enterprise debe tener el set completo de features (cobranzas, website, documents, exec_reports, exports, multi_branch, api, etc.). Tests que verifiquen "enterprise incluye todas".
- [ ] **Fix frontend** (si aplica): `hasFeature`/`featureGates` no debe lockear cuando el tier es Enterprise (o cuando la feature está presente). Revisar el caso org/branch (un gerente de sucursal hereda features del plan de la org).
- [ ] Verificar que Básico/Pro sigan correctamente gateados (no romper plan 10).

## 4. Criterios de aceptación
- Una cuenta Enterprise ve **todas** las secciones desbloqueadas (sin candados).
- Básico/Pro mantienen el gating correcto.
- `security-reviewer` confirma que el fix no abre acceso indebido a tiers inferiores.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **security-reviewer** (no romper el gating real), **react-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** con **dos cuentas** (Enterprise = sin candados; Básico = candados correctos).

## 6. Verificación
- `pytest` (enterprise tiene todas las features; básico no); `npm run build`.
- Chrome MCP/Playwright: login Enterprise → todo desbloqueado; login Básico → candados esperados.
- `security-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Audit de la cadena features→tier→UI (planes 08/10). Enterprise debe desbloquear todo.
- 2026-06-20 — Bug root cause: hasFeature() leía account.features (siempre undefined); las features viven en account.subscription.features. Fix en featureGates.js (1 línea). Backend catalog ya era correcto. 4 tests de regresión agregados. 28 tests pass. Build OK. security-reviewer + react-reviewer: APPROVE. SHA: a55309d. Deploy en Render automático.

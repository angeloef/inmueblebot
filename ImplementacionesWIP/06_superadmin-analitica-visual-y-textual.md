---
id: 06
title: "Super-admin — pestaña de análisis de datos (visual + textual)"
status: completed
priority: high
area: backend+frontend
files:
  - app/api/routes/admin.py         # endpoints de analítica de plataforma
  - app/api/routes/reports.py       # reportes existentes (reusar lógica)
  - app/db/models/metric_snapshot.py# KPIs mensuales por tenant
  - app/db/models/subscription.py   # SaaS/MRR
  - dashboard/src/Reportes.jsx      # patrón de charts SVG/CSS + ReportesBento.css
  - dashboard/src/superadmin/       # nueva pestaña Analítica
  - dashboard/src/api.js            # hooks de analítica
depends_on: ["04"]
metricas:
  saas:    ["tenants activos/trial/churn", "MRR", "altas/bajas por mes"]
  uso:     ["mensajes/bot", "propiedades", "citas", "conversión"]
  ops:     ["latencia", "errores", "uso de routers/modelos IA", "costos"]
  drilldown: ["comparativa y detalle por tenant"]
skills: ["fastapi-patterns", "python-patterns", "react-patterns", "data-viz", "accessibility"]
agents: ["Plan", "react-reviewer", "security-reviewer"]
---

# Plan 06 — Analítica de plataforma (visual + textual)

## 1. Objetivo
Pestaña **"Analítica"** en `/superadmin` con vista **visual** (charts) y **textual** (resumen + tablas) de los datos de **todas** las inmobiliarias, con el detalle relevante para los 2 devs: **negocio/SaaS, uso de producto, salud técnica/ops y drilldown por tenant**.

## 2. Contexto necesario (estado actual real)
- **Fuentes de datos ya disponibles:**
  - `metric_snapshots` (`app/db/models/metric_snapshot.py`): foto mensual de KPIs por tenant (funnel/cobranzas/cartera/demanda), JSONB, con índice único `(tenant_id, period)`. Ideal para tendencias mes-a-mes baratas.
  - `subscriptions` (`subscription.py`): `status` (trial/active/paused/cancelled/past_due), `plan`, `amount`, `currency`, `current_period_end` → base de **MRR/churn**.
  - `app/api/routes/reports.py`: ya hay lógica de reportes por tenant a reusar/agregar.
  - Uso/ops: derivar de `messages`/`conversations`, `appointments`, `properties`, y de los logs de router (ver `router-v2-architecture-review.md`, `eval_v3_*.log`). Para costos/modelos IA, verificar si hay métrica persistida; si no, dejar el panel marcado como "fase 2" en vez de inventar datos.
- **Charting:** `Reportes.jsx` **no usa librería** (no hay recharts/chart.js en `package.json`); usa **SVG/CSS a mano** con `ReportesBento.css`. Decisión: reusar ese estilo para consistencia visual; si se necesita algo más rico (series temporales multi-tenant), evaluar agregar **Recharts** (está permitido en el stack) y documentarlo.
- **Vista textual:** combinar (a) tablas de números crudos y (b) un **resumen narrativo** corto. Para el narrativo se puede usar un endpoint que arme el texto con plantillas determinísticas (sin LLM) o, opcionalmente, una llamada al modelo ya integrado en el backend. Recomendación: empezar **determinístico** (rápido, sin costo/latencia) y dejar el narrativo-IA como toggle fase 2.

## 3. Plan secuencial

### Backend
- [ ] Endpoint `GET /admin/analytics/overview` (superadmin): agrega a nivel plataforma — nº tenants por estado, MRR (suma de `amount` de subs activas, normalizada por `currency`), altas/bajas por mes, totales de uso (propiedades, citas, mensajes), y señales de ops disponibles.
- [ ] Endpoint `GET /admin/analytics/tenants` para el **drilldown**: una fila por tenant con sus KPIs (desde `metric_snapshots` + live), para comparativa.
- [ ] Reusar `reports.py`/`metric_snapshots`; no recalcular lo que ya existe. Cachear si es caro.
- [ ] Resumen textual determinístico (plantillas) en el payload (`narrative: {...}`).
- [ ] Tests: agregaciones correctas con datos de ≥2 tenants; 403 para no-superadmin.

### Frontend
- [ ] Pestaña "Analítica" con secciones: **SaaS/Negocio**, **Uso de producto**, **Salud técnica/Ops**, **Drilldown por tenant**.
- [ ] Charts reusando el patrón de `Reportes.jsx`/`ReportesBento.css` (o Recharts si se aprueba). KPIs grandes + series temporales + comparativa por tenant (tabla ordenable).
- [ ] **Vista textual**: panel de resumen ("X tenants activos, MRR ARS …, +N altas este mes, tenant Y lidera en conversión") + tablas exportables (reusar `ExportCsv.jsx`).
- [ ] Estados vacío/cargando/error en cada panel.

## 4. Criterios de aceptación
- Los 4 grupos de métricas se muestran con datos reales agregados de todas las inmobiliarias.
- Hay vista visual (charts) **y** textual (resumen + tablas) coherentes entre sí.
- Drilldown permite comparar y abrir el detalle por tenant.
- 403 para no-superadmin.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `fastapi-patterns`, `python-patterns`, `react-patterns`, `data-viz` (diseño de charts/legibilidad), `accessibility` (charts con alternativa textual = buena a11y por diseño).
- **Agentes:** **Plan** (definir el catálogo de métricas y de dónde sale cada una ANTES de codear, para no inventar datos), **react-reviewer**, **security-reviewer** (agregados no deben permitir des-anonimizar/leak entre tenants si alguna vista fuera compartida).
- **MCP:** ninguno externo.
- **Workflow:** primero fijar el catálogo de métricas y sus fuentes (Plan agent), luego endpoints + tests, luego visualización. Marcar como "fase 2" toda métrica sin fuente real (costos IA) en vez de fabricarla.

## 6. Verificación
- `pytest` de las agregaciones (números cuadran vs queries directas).
- `npm run build`; Chrome MCP: cargar la pestaña con datos de ≥2 tenants, screenshot de cada sección, consola sin errores.
- Revisar que la vista textual coincida con la visual (mismos números).

## 7. Bitácora (append-only)
- 2026-06-16 — Plan creado. Decisión: charts reusan el patrón SVG/CSS de Reportes salvo que se apruebe Recharts; narrativo determinístico en v1, narrativo-IA fase 2; métricas sin fuente real → "fase 2", no inventar.
- 2026-06-17 — Implementado. Backend: `app/api/routes/admin_analytics.py` (NEW) con `GET /admin/analytics/overview` (SaaS/negocio: tenants por estado, MRR por moneda, altas/bajas por mes acotadas a ventana, uso: propiedades/citas/mensajes/conversaciones/conversión, ops=fase2, narrativa determinística) y `GET /admin/analytics/tenants` (drilldown por tenant), ambos cross-tenant vía GUC superadmin (RLS), gateados por `require_superadmin` (401 sin auth). Registrado en `main.py` (app + compat). Frontend: pestaña "Analítica" (`PlatformAnalytics.jsx` NEW) con charts SVG a mano (patrón Reportes), KPIs, banner fase 2 y tabla drilldown ordenable + export CSV client-side; hooks `useAnalyticsOverview`/`useAnalyticsTenants` en `api.js`; wired en `SuperadminShell.jsx`. Decisión confirmada: sin Recharts (SVG a mano alcanza); narrativo determinístico (sin LLM). Gates: ruff OK, 7 tests nuevos + 8 de admin_global verdes en Docker, `vite build` OK, Chrome MCP sin errores de consola (visual=textual: 302 inmobiliarias/221 props/16 citas), review security+react sin CRITICAL/HIGH (MEDIUM aplicados: queries de tendencia acotadas por fecha, name-map proyectado, headers de orden accesibles por teclado, aria-hidden en barras SVG, revoke de objectURL diferido).

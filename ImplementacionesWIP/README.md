# ImplementacionesWIP — Índice maestro

Carpeta de planes de implementación (WIP) para `inmueblebot`. Cada `.md` es **autocontenido**: trae el contexto mínimo verdadero para resolver un problema y deja al modelo autonomía para investigar y llegar a la solución. Sirven como memoria de trabajo entre sesiones separadas de Claude Code.

> Generado el 2026-06-16. Rol: lead engineer. Stack: dashboard React/Vite (`dashboard/src/*.jsx`) + backend FastAPI/SQLAlchemy (`app/`).

## Planes activos

| # | Archivo | Área | Estado | Depende de |
|---|---------|------|--------|------------|
| 01 | [`01_clientes-acciones-y-pestana-propiedades.md`](./01_clientes-acciones-y-pestana-propiedades.md) | Frontend (Clients.jsx) | `completed` | — |
| 02 | [`02_propiedades-atajo-vincular-inquilino.md`](./02_propiedades-atajo-vincular-inquilino.md) | Frontend (Properties.jsx) | `completed` | comparte flujo de vínculo con 01 |
| 03 | [`03_log-actividad-unificado.md`](./03_log-actividad-unificado.md) | Backend + Frontend | `completed` | 01/02 emiten eventos que 03 persiste |
| 04 | [`04_superadmin-base-y-acceso-cross-tenant.md`](./04_superadmin-base-y-acceso-cross-tenant.md) | Backend + Frontend | `completed` | — (base de 05/06/07) |
| 05 | [`05_superadmin-explorador-global-cross-tenant.md`](./05_superadmin-explorador-global-cross-tenant.md) | Backend + Frontend | `completed` | 04 (reusa activity_log de 03) |
| 06 | [`06_superadmin-analitica-visual-y-textual.md`](./06_superadmin-analitica-visual-y-textual.md) | Backend + Frontend | `completed` | 04 |
| 07 | [`07_error-reporting-in-app-y-pestana-superadmin.md`](./07_error-reporting-in-app-y-pestana-superadmin.md) | Backend + Frontend | `completed` | 04 |
| 08 | [`08_tiers-planes-backend.md`](./08_tiers-planes-backend.md) | Backend | `completed` | — (base de 09) |
| 09 | [`09_flujo-saas-frontend.md`](./09_flujo-saas-frontend.md) | Frontend | `completed` | 08 |
| 10 | [`10_fix-bypass-paywall-candado-nav.md`](./10_fix-bypass-paywall-candado-nav.md) | Frontend | `completed` | — (relac. 08/09) |
| 11 | [`11_formato-numerico-modal-contrato.md`](./11_formato-numerico-modal-contrato.md) | Frontend | `completed` | — |
| 12 | [`12_enviar-correo-desde-app.md`](./12_enviar-correo-desde-app.md) | Backend + Frontend | `completed` | — (reusa activity_log de 03) |
| 13 | [`13_faq-ux-wizard-guiado.md`](./13_faq-ux-wizard-guiado.md) | Frontend | `completed` | — |
| 14 | [`14_propiedades-ux-wizard-y-tutorial.md`](./14_propiedades-ux-wizard-y-tutorial.md) | Frontend | `completed` | — (reusa patrón del 13) |
| 15 | [`15_importacion-asistida-propiedades.md`](./15_importacion-asistida-propiedades.md) | Backend + Frontend | `completed` | 14 (CTA en estado vacío) |
| 16 | [`16_config-backend-gaps.md`](./16_config-backend-gaps.md) | Backend | `completed` | — (base de 17) |
| 17 | [`17_config-ui-rebuild-handoff.md`](./17_config-ui-rebuild-handoff.md) | Frontend | `completed` | 16 |
| 18 | [`18_facturacion-seguridad-checkout.md`](./18_facturacion-seguridad-checkout.md) | Backend+Frontend | `completed` | — **(CRÍTICO)** |
| 19 | [`19_facturacion-historial-y-uso.md`](./19_facturacion-historial-y-uso.md) | Backend+Frontend | `completed` | 18 |
| 20 | [`20_hablar-con-ventas-enterprise.md`](./20_hablar-con-ventas-enterprise.md) | Backend+Frontend | `completed` | — |
| 21 | [`21_fixes-visuales-darkmode-y-modal.md`](./21_fixes-visuales-darkmode-y-modal.md) | Frontend | `completed` | — |
| 22 | [`22_gating-candado-enterprise-audit.md`](./22_gating-candado-enterprise-audit.md) | Frontend+Backend | `completed` | — |
| 23 | [`23_config-cleanup-sistema-y-equipo.md`](./23_config-cleanup-sistema-y-equipo.md) | Frontend+Backend | `completed` | — |
| 24 | [`24_inmobiliarias-sucursales-unificadas.md`](./24_inmobiliarias-sucursales-unificadas.md) | Frontend+Backend | `completed` | — |
| 25 | [`25_branding-logo-viviendapp.md`](./25_branding-logo-viviendapp.md) | Frontend | `completed` | — |
| 26 | [`26_perfil-avatar-foto-crop.md`](./26_perfil-avatar-foto-crop.md) | Backend+Frontend | `completed` | 16 |
| 27 | [`27_borrar-cuenta-2fa-email.md`](./27_borrar-cuenta-2fa-email.md) | Backend+Frontend | `completed` | — |
| 28 | [`28_ambientes-vs-habitaciones-monoambiente.md`](./28_ambientes-vs-habitaciones-monoambiente.md) | Backend+Frontend+Bot | `completed` | — |
| 29 | [`29_propiedades-agente-asignado-cleanup.md`](./29_propiedades-agente-asignado-cleanup.md) | Frontend+Backend | `completed` | — |
| 30 | [`30_faq-ejemplos-overlay-bloqueante.md`](./30_faq-ejemplos-overlay-bloqueante.md) | Frontend | `completed` | — |
| 31 | [`31_avatar-propagacion-y-crop-ui.md`](./31_avatar-propagacion-y-crop-ui.md) | Backend+Frontend | `completed` | — |
| 32 | [`32_propiedades-sort-by.md`](./32_propiedades-sort-by.md) | Frontend | `completed` | — |
| 33 | [`33_inicio-enterprise-rehacer-ui.md`](./33_inicio-enterprise-rehacer-ui.md) | Frontend | `completed` | — |
| 34 | [`34_propiedades-exportar-e-importar-modal.md`](./34_propiedades-exportar-e-importar-modal.md) | Frontend (Properties.jsx) | `completed` | — |
| 35 | [`35_faq-dedup-ejemplos.md`](./35_faq-dedup-ejemplos.md) | Frontend + Backend | `completed` | — |
| 36 | [`36_config-avatar-reactivo.md`](./36_config-avatar-reactivo.md) | Frontend (Config.jsx + auth.jsx) | `completed` | — |
| 37 | [`37_clientes-boton-editar-claro.md`](./37_clientes-boton-editar-claro.md) | Frontend (Clients.jsx) | `completed` | — |
| 38 | [`38_fix-envio-correo-cliente-con-email.md`](./38_fix-envio-correo-cliente-con-email.md) | Backend + Frontend | `completed` | relac. 12 |
| 39 | [`39_upsell-feature-preview-secciones-bloqueadas.md`](./39_upsell-feature-preview-secciones-bloqueadas.md) | Frontend (gating) | `completed` | relac. 10/22 |
| 40 | [`40_propiedades-miniaturas-webp-optimizadas.md`](./40_propiedades-miniaturas-webp-optimizadas.md) | Backend + Frontend | `completed` | — |
| 41 | [`41_enforcement-limites-plan-backend.md`](./41_enforcement-limites-plan-backend.md) | Backend | `completed` | **P0** — relac. 08/09 |
| 42 | [`42_busqueda-multi-tipo-search-properties.md`](./42_busqueda-multi-tipo-search-properties.md) | Backend (bot / search tool) | `completed` | **P1** — no toca engine.py |
| 43 | [`43_respuestas-conversacionales-envoltorio-verbatim.md`](./43_respuestas-conversacionales-envoltorio-verbatim.md) | Backend (bot / engine.py) | `completed` | **P2** — reversible con flag (off por default) |

### Bot chatbot — UX conversacional sin perder grounding (43)
**43 (P2)** las respuestas de búsqueda suenan a template (bloque Python verbatim, sin LLM).
Dirección "envolver, no reescribir": LLM agrega intro/outro alrededor del bloque de datos duros
(precio/specs/ID), que sigue siendo Python puro e intocable — test no-negociable: bloque
verbatim byte-idéntico. Reusa `LLMRole.SYNTH` (gpt-5.4-mini) ya existente. Reversible con flag;
medir costo/latencia en tests/eval/ antes de habilitar en prod (WhatsApp activo).

### Bot chatbot — bug real detectado en WhatsApp (42)
**42 (P1)** `search_properties` trata `tipo` como string singular — "depto o casa" solo busca uno.
Fix: `tipo` acepta CSV (`"departamento,casa"`) + `.in_()` en el filtro, combinable con todos los
demás criterios (zona/reference_points, presupuesto, dormitorios, ambientes). Explícitamente NO
toca `app/routers/v3/engine.py` (ahí vive un bug relacionado de `_assemble_response` que descarta
la segunda llamada a un mismo tool en un turno — documentado, fuera de alcance).

### Lote testing manual #3 (37–41)
Bugs/gaps detectados en testing manual sobre features ya marcadas `completed`:
**41 (P0)** los límites cuantitativos de plan no se aplican (`plans.py` los define, nadie los
enforce → Básico carga >50 propiedades e invita equipo sin tope) — bloqueo duro + 402/UpgradeModal;
**38 (P1)** enviar correo a un cliente con email da 422 "no tiene email" (bug aguas arriba del
endpoint, no en el 422); **40 (P1)** miniaturas de propiedades se sirven en nativa — generar WebP
escalado al subir y servir nativa solo al editar; **39 (P2)** secciones bloqueadas solo muestran
popup — agregar página de preview genérica con problema/funciones/CTA upgrade; **37 (P2)** botón
"editar cliente" es icon-only poco claro. Orden sugerido: **41 → 38 → 40 → 39 → 37**.
Todos corren `/ponytail full` + verificación Chrome MCP/Playwright en Docker (light+dark).

### Lote fixes UI/UX (34–36)
Bugs detectados en testing: exportar/importar en Propiedades (34), FAQs duplicadas al cargar ejemplos dos veces (35), avatar de perfil requería reload para verse (36). Todos independientes entre sí.

### Lote de bugs del testing manual #2 (30–33)
FAQ overlay bloqueante (30), avatar propagado al equipo + mejor crop (31), sort por columna en
Propiedades (32), e Inicio Enterprise rehecho con design system + contraste dark (33).
Todos corren **`/ponytail full`** + verificación **Chrome MCP/Playwright en Docker** (light+dark).

### Lote de bugs del testing manual (18–29)
Agrupados por área para distintas sesiones del loop. **Prioridad:** 18 (seguridad de cobro) primero.
**Nuevo estándar (SKILL actualizado):** todo plan corre **`/ponytail full`** tras implementar y verifica
los cambios visuales con **Chrome MCP/Playwright en Docker local** (light+dark) antes de marcar done.

### Configuración / nuevo layout (16–17)
Reconstrucción de la pantalla **Configuración** según el handoff de diseño (`Claude interface layout-handoff/`):
rail de 8 secciones (General, Cuenta, Mi inmobiliaria, Facturación, Uso, Equipo, Sistema·Admin, Inmobiliarias·Admin),
búsqueda, tema claro/oscuro, save-bar y estados skeleton/error. **16** construye los huecos de backend que el diseño
necesita (cambio de contraseña logueado, update de perfil, self-settings del dueño, `GET /usage`, `whatsapp_status`);
**17** recrea la UI y la cablea. WhatsApp "Conectar" queda como **placeholder** (embedded signup = plan futuro).
Solo se rediseña Configuración. Orden: **16 → 17**.

### Propiedades (14–15)
**14** rediseña el alta de propiedades como **wizard por pasos** con tips permanentes y barra de
progreso; el tutorial/CTA de onboarding solo aparece con **0 propiedades** (reusa el patrón del 13).
**15** suma **importación asistida**: el cliente manda su listado (archivos + nota) desde Propiedades,
ve el estado (Recibido → En proceso → Cargadas) y recibe email al completar; los devs lo reciben/parsean
en una pestaña nueva **"Importaciones"** del `/superadmin` (espeja `error_reports` + `ErrorTriage`). Orden: **14 → 15**.

### Arreglos dashboard (10–12)
Fixes independientes pedidos sobre el dashboard: **10** cierra el **bypass del paywall**
(candado en nav que abre upgrade sin entrar + guard de ruta) — *prioridad crítica*; **11**
formatea los montos del modal de contrato en Cobranzas (es-AR: $, miles con punto, decimales
con coma, % ); **12** envía correo al cliente **desde la app** vía Resend (from plataforma,
reply-to inmobiliaria) y lo registra en `activity_log`. Orden sugerido: **10 → 12 → 11**.

### Épica SaaS / planes (08–09)
Completar el flujo de suscripciones: **08** lleva el backend de mono-plan a **3 tiers**
(Básico/Pro/Enterprise) con catálogo central, gating por tier, montos MP y exposición de
tier/límites; **09** construye el frontend (banner de trial, manejo de 402 con modal+lock,
sección "Plan y suscripción" en Config con checkout MercadoPago). Orden: **08 → 09**.
Catálogo/precios en `recommended_pricing_plans_v3.md`. Enterprise = "Hablar con ventas" (no self-serve).

### Épica Super-admin (04–07)
Dashboard dedicado a los 2 devs en ruta aislada `/superadmin` (login por `role=superadmin`).
**04** es la base (auth + acceso cross-tenant sobre RLS); luego **05** (explorador global con
edición full), **06** (analítica visual+textual) y **07** (reporte de errores) corren en paralelo
sobre esa base. Orden de ejecución: **04 → (05, 06, 07)**.

### Ejecución automatizada
Estos planes los procesa el skill **`loop-skill/`** (implementador-loop, patrón Ralph):
selecciona el próximo `pending` con dependencias cumplidas, implementa, verifica con
gates y pushea. Instalación y uso en [`loop-skill/README.md`](./loop-skill/README.md).

### Orden sugerido de ejecución
1. **01** y **02** en paralelo (UI pura, bajo riesgo, mismo flujo de vínculo → conviene extraer un componente compartido `LinkClientProperty`).
2. **03** al final: es transversal (modelo + migración + endpoint) y se nutre de los puntos de vínculo/estado que tocan 01 y 02. Hacerlo después evita re-trabajar los emisores de eventos.

---

## AUDIT — Formato óptimo de estos `.md` para loops en Claude Code

**Pregunta auditada:** ¿cuál es la forma más optimizada de formatear estos `.md` para optimizar trabajo futuro con loops/custom commands de Claude Code, dando contexto verdadero pero autonomía al modelo?

**Resultado del audit (recomendación aplicada):**

1. **Frontmatter YAML máquina-parseable al inicio.** Un loop puede leer `status`, `files`, `endpoints`, `depends_on`, `skills`, `agents` sin parsear prosa. Permite filtrar "dame el próximo plan `pending` sin dependencias abiertas".
2. **Contexto verdadero, no exhaustivo.** Se listan archivos + rangos de línea + *comportamiento actual observado* (no el código entero). Esto ancla al modelo en la realidad del repo sin sobre-restringir la solución. Regla: si el dato evita que el modelo se equivoque o re-descubra algo costoso, va; si el modelo lo puede deducir leyendo el archivo señalado, se omite y se cita el archivo.
3. **Plan secuencial como checklist accionable** (`- [ ]`) → un loop puede marcar progreso y reanudar.
4. **Criterios de aceptación explícitos y verificables** → habilitan un paso de verificación automatizable (lint, Playwright, diff).
5. **Sección fija de Skills/MCP/Workflow** → el orquestador sabe qué subagente/skill disparar sin adivinar.
6. **Bitácora append-only al final** → memoria entre sesiones; cada corrida anota qué hizo y qué quedó.
7. **Una unidad de trabajo por archivo**, agrupando solo cuando tocan el mismo código. Mantiene cada loop corto y el contexto enfocado (alineado con la directiva "leer solo las partes relevantes del codebase").

**Estructura canónica de cada plan:**

```
--- (frontmatter YAML: id, status, priority, area, files, endpoints, depends_on, skills, agents)
# Título
## 1. Objetivo            (1-3 frases)
## 2. Contexto necesario  (archivos + líneas + estado actual real)
## 3. Plan secuencial     (checklist [ ])
## 4. Criterios de aceptación
## 5. Skills / MCP / Workflow AI
## 6. Verificación
## 7. Bitácora (append-only)
```

Este formato es el que usan los tres planes de esta carpeta.

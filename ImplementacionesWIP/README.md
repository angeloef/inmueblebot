# ImplementacionesWIP — Índice maestro

Carpeta de planes de implementación (WIP) para `inmueblebot`. Cada `.md` es **autocontenido**: trae el contexto mínimo verdadero para resolver un problema y deja al modelo autonomía para investigar y llegar a la solución. Sirven como memoria de trabajo entre sesiones separadas de Claude Code.

> Generado el 2026-06-16. Rol: lead engineer. Stack: dashboard React/Vite (`dashboard/src/*.jsx`) + backend FastAPI/SQLAlchemy (`app/`).

## Planes activos

| # | Archivo | Área | Estado | Depende de |
|---|---------|------|--------|------------|
| 01 | [`01_clientes-acciones-y-pestana-propiedades.md`](./01_clientes-acciones-y-pestana-propiedades.md) | Frontend (Clients.jsx) | `completed` | — |
| 02 | [`02_propiedades-atajo-vincular-inquilino.md`](./02_propiedades-atajo-vincular-inquilino.md) | Frontend (Properties.jsx) | `completed` | comparte flujo de vínculo con 01 |
| 03 | [`03_log-actividad-unificado.md`](./03_log-actividad-unificado.md) | Backend + Frontend | `completed` | 01/02 emiten eventos que 03 persiste |

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

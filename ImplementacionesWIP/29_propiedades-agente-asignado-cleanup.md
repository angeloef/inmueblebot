---
id: 29
title: "Propiedades — limpiar 'Agente asignado' hardcodeado (wire a equipo real o descartar)"
status: completed
priority: low
area: frontend+backend
files:
  - dashboard/src/Properties.jsx    # agent: 'M. Pereyra' (739/750), select 'Agente asignado' (1028-1029), col (1466/1498), ficha (203)
  - app/api/routes/team.py          # miembros reales del tenant (si se rehace el vínculo)
  - app/db/models/property.py       # cómo se persiste el agente hoy
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decision_pendiente: "rehacer el vínculo (agente = miembro real del equipo) vs descartar el campo — definir con el usuario en preflight"
skills: ["react-patterns", "fastapi-patterns", "python-testing"]
agents: ["react-reviewer", "security-reviewer"]
---

# Plan 29 — Agente asignado: limpiar hardcodeo

## 1. Objetivo
Hoy "Agente asignado" en propiedades tiene **4 agentes hardcodeados** (código muerto, p. ej. `agent: 'M. Pereyra'`). Limpiarlo y **o bien descartar** la vinculación **o rehacerla bien** (agente = miembro real del equipo del tenant).

## 2. Contexto necesario (estado actual real)
- `Properties.jsx`: defaults hardcodeados `agent: 'M. Pereyra'` (739/750), `<select id="pw-agent">` con opciones fijas (1028-1029), columna de tabla (1466/1498) y ficha (`property.agent`, 203). Es texto libre/hardcode, no referencia a un usuario real.
- **Equipo real** existe en `team.py` (miembros del tenant con rol). Lo correcto sería que el agente asignado salga de ahí.
- Confirmar cómo persiste hoy `agent` en el modelo (texto en `extra_data`?) para migrar/limpiar.

## 3. Plan secuencial
> **Preflight**: confirmar con el usuario la decisión (rehacer vs descartar). Default recomendado: **rehacer** vinculando a miembros reales del equipo.
- [ ] **Si rehacer**: el selector de "Agente asignado" lista los **miembros del equipo** (`team.py`); persistir el **id** del miembro (no texto libre). Mostrar el nombre real en ficha/tabla. Backfill/limpieza de los valores hardcodeados existentes.
- [ ] **Si descartar**: quitar el campo "Agente asignado" de alta/edición/ficha/tabla y limpiar el código muerto y los defaults.
- [ ] En ambos casos: eliminar los nombres hardcodeados y defaults (`'M. Pereyra'`, etc.). Sin código muerto.
- [ ] Tests (si backend): el agente asignado referencia un miembro válido del tenant; no acepta agentes de otro tenant.

## 4. Criterios de aceptación
- No quedan agentes hardcodeados ni defaults inventados.
- Según la decisión: el agente sale del equipo real (con id válido del tenant) o el campo se quitó limpio.
- Build verde; sin código muerto.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer** (limpieza sin romper), **security-reviewer** (si se vincula a equipo: scoping del tenant).
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar (ideal para detectar el código muerto); **Chrome MCP/Playwright en Docker** (light+dark).

## 6. Verificación
- `npm run build`; `pytest` si toca backend.
- Chrome MCP/Playwright: alta/edición de propiedad con el agente real (o sin el campo).
- `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Decisión rehacer-vs-descartar a confirmar en preflight; default recomendado: vincular a miembros reales del equipo (team.py).
- 2026-06-20 — Decisión: descartar el campo. Eliminados 7 puntos de referencia a `agent` en Properties.jsx: ficha (dt/dd), defaults en form init (×2), payload de submit, select con 4 opciones hardcodeadas, th de tabla y td de fila. Build verde ✓.

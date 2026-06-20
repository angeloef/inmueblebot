---
id: 28
title: "Propiedades — diferenciar ambientes vs habitaciones (+ monoambiente) en UI, backend y bot"
status: completed
priority: medium
area: backend+frontend+chatbot
files:
  - app/db/models/property.py       # hoy solo 'bedrooms' (dormitorios); falta 'ambientes'
  - app/tools/v2/registry.py        # schema de búsqueda (dormitorios, bedrooms_match)
  - app/tools/v2/search_properties.py  # filtros del bot
  - app/tools/v2/get_property_details.py  # render (monoambiente = bedrooms==0)
  - dashboard/src/Properties.jsx    # campo 'Ambientes' (829) y 'Baños'
  - alembic/versions/               # migración (nuevo campo + backfill)
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
skills: ["fastapi-patterns", "python-patterns", "python-testing", "react-patterns"]
agents: ["Plan", "security-reviewer", "react-reviewer"]
---

# Plan 28 — Ambientes vs habitaciones + monoambiente

## 1. Objetivo
Diferenciar correctamente **ambientes** (concepto AR: total de espacios; 1 ambiente = **monoambiente**) de **habitaciones/dormitorios**, en la **UI**, el **backend/modelo** y la **lógica del chatbot** (búsqueda y fichas). Hoy se confunden.

## 2. Contexto necesario (estado actual real)
- **Modelo** (`property.py`): solo existe `bedrooms` ("dormitorios"). No hay campo `ambientes`.
- **Bot**: `get_property_details.py:46-47` usa `bedrooms` y marca "(monoambiente)" cuando `bedrooms==0`. El schema de búsqueda (`registry.py`) filtra por `dormitorios`/`bedrooms_match`. → todo está modelado como dormitorios, no como ambientes.
- **UI** (`Properties.jsx:829`): el campo se llama "Ambientes" pero probablemente persiste sobre `bedrooms`/`rooms` → mezcla los conceptos.
- **Convención AR a fijar (con Plan)**: `ambientes` = total de espacios habitables; `dormitorios` = subconjunto; **monoambiente = 1 ambiente / 0 dormitorios**. Definir la relación y qué usa el bot para filtrar (los clientes suelen decir "2 ambientes" o "1 dormitorio").

## 3. Plan secuencial
> Arrancar con **Plan** para fijar el modelo de datos y la semántica (ambientes vs dormitorios, monoambiente) y cómo migrar lo existente.
- [ ] **Modelo + migración**: agregar `ambientes` (int) a `properties` (mantener `bedrooms`). Backfill razonable (p. ej. ambientes = bedrooms+1 salvo monoambiente) — definir en preflight. Downgrade.
- [ ] **Backend/bot**: actualizar `search_properties`/`registry` para entender **ambientes** y **dormitorios** (mapear lo que pide el cliente). Render de fichas (`get_property_details`) muestra ambientes y dormitorios; **monoambiente** correcto (1 ambiente). Mantener compat de los filtros existentes.
- [ ] **UI** (`Properties.jsx` / wizard del plan 14): separar campos **Ambientes** y **Dormitorios** (y caso monoambiente: al elegir 1 ambiente, dormitorios=0/oculto). Etiquetas claras + tip. Persistir ambos.
- [ ] Tests: bot filtra por ambientes y por dormitorios; monoambiente se muestra/filtra bien; UI guarda ambos campos.

## 4. Criterios de aceptación
- UI, backend y bot distinguen ambientes de dormitorios; monoambiente se maneja correctamente en los 3.
- Búsquedas del bot ("2 ambientes", "1 dormitorio", "monoambiente") devuelven lo correcto.
- Migración aplica y revierte; datos existentes con valor coherente.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **Plan** (semántica/modelo antes de codear), **security-reviewer** (migración/datos), **react-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (alta/edición con ambientes/dormitorios, light+dark). Probar el bot con `pytest`/simulador.

## 6. Verificación
- `alembic upgrade/downgrade`; `pytest` (búsqueda + render + monoambiente) en Docker; `npm run build`.
- Chrome MCP/Playwright: alta de propiedad con ambientes y monoambiente.
- `security-reviewer` (migración/datos).

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Toca modelo + bot + UI. Fijar semántica ambientes/dormitorios/monoambiente con el subagente Plan antes de migrar.
- 2026-06-20 — Implementado. Migración 0024: columna `ambientes` + backfill. Modelo, API (admin + admin_global), bot (registry + search + details), dashboard (api.js + Properties.jsx). Build verde.

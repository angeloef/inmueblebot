---
id: search-properties-redaccion-sensible-al-count
area: Backend (bot / search tool)
priority: P1
status: pending
depends_on: []
related_areas: [v3-prompts, v4-prompts-inherit, tests-v3]
---

## Problema

La redacción que arma `search_properties` no mira **cuántos resultados
devolvió** — produce dos bugs observables en conversación real (WhatsApp,
tenant `default`):

1. **Plural incorrecto con 1 resultado:** "Encontré 1 propiedad casas, en
   alquiler, en UNAM:" — "1 propiedad" (singular, correcto) + "casas"
   (siempre plural, incorrecto). Empeora con multi-tipo: "1 propiedad
   departamentos y casas" cuando en realidad solo matcheó 1 casa (ningún
   departamento).
2. **Tip de "seguí filtrando" sin sentido con pocos resultados:** con 1 sola
   propiedad en la lista, el bot igual ofrece "Si queres, puedo filtrar por
   presupuesto o dormitorios" — filtrar más no ayuda cuando ya hay 1 resultado;
   el paso lógico es ver detalles/fotos/agendar.

Caso real observado (conversación de test, 2026-07-02): usuario busca "casa
con patio" → alquiler → UNAM (1 resultado) → pregunta "¿algún departamento?"
→ el bot re-busca y devuelve el mismo bloque, ahora con la etiqueta "casas y
departamentos" (implica mezcla, pero en realidad no hay ningún departamento
— la respuesta nunca lo aclara explícitamente).

## Contexto

**Anclas reales, `app/tools/v2/search_properties.py`:**

- `_tipo_plural_label(tipos: list[str])` (líneas 87-92): pluraliza cada
  término de tipo **incondicionalmente** (`t + "s"`), sin recibir el count de
  resultados. Contrastar con `_plural(word, count)` (líneas 527-530), que sí
  es sensible al count y ya se usa correctamente para "propiedad"/"propiedades"
  en la línea 451 (`f"Encontré {len(properties)} {_plural('propiedad',
  len(properties))}{filters_desc}:\n"`).
- `_describe_filters(...)` (líneas 556-577): construye `filters_desc`
  (incluye la llamada a `_tipo_plural_label` en la línea 565) sin recibir
  `count` como parámetro. Se llama en la línea 451 (armado de la lista final)
  y probablemente en otros puntos de la cascada de fallback — revisar todos
  los call-sites antes de cambiar la firma.
- `_build_missing_criteria_tip(operation, tipo, zona, presupuesto_max,
  dormitorios)` (líneas 533-553): decide qué tip ofrecer mirando solo qué
  criterios faltan, nunca cuántos resultados quedan. Se llama en la línea 454,
  inmediatamente después de armar `lines` con la lista ya formateada — el
  `count` (`len(properties)`) está disponible ahí mismo, no hay que
  recalcularlo.
- **Multi-tipo sin match parcial:** cuando `tipo` trae ≥2 valores (plan #42,
  `_parse_tipos` línea ~70-84) y la búsqueda real solo matchea uno de ellos,
  hoy no hay ninguna lógica que compute matches por tipo individual y lo
  mencione ("no hay departamentos, pero sí esta casa"). Sería una consulta
  adicional agrupando por `Property.category` sobre el mismo `stmt` filtrado,
  o contar en Python sobre `properties` ya traído (más barato, sin roundtrip
  extra) — decidir cuál en la ejecución, no asumir.

## Criterios de aceptación

- `search_properties(tipo="casa", ...)` con exactamente 1 resultado devuelve
  "Encontré 1 casa en alquiler en UNAM" (singular correcto), no "1 propiedad
  casas".
- Con `tipo="departamento,casa"` y 1 solo match (una casa, cero
  departamentos), la respuesta declara explícitamente que no hay
  departamentos disponibles y muestra la casa — no una etiqueta ambigua tipo
  "1 propiedad departamentos y casas" que sugiere mezcla.
- Con 2+ resultados del mismo tipo, el plural sigue funcionando igual que hoy
  ("Encontré 3 casas...") — retrocompatibilidad total, sin tocar tests
  existentes que ejercitan ese camino.
- Con un número bajo de resultados (definir el umbral en la ejecución, ej.
  ≤3), el tip de "filtrar por X" se reemplaza por una invitación a avanzar
  (ver detalles/fotos/agendar) en vez de seguir acotando una lista que ya es
  corta. Con muchos resultados, el tip de "filtrar por X" sigue apareciendo
  igual que hoy.
- Suite `pytest tests/v3/ -q` en verde, incluyendo los tests existentes de
  multi-tipo del plan #42 (`tests/v3/test_multi_tipo_search.py`) sin
  modificarlos salvo para que sigan pasando con el cambio de firma.

## Fuera de alcance

- No tocar `app/routers/v3/engine.py` ni `_assemble_response` — mismo límite
  que el plan #42 (bug de `break` en múltiples tool_calls del mismo tool
  documentado ahí, sigue fuera de alcance acá también).
- No tocar el sistema de `framing` (intro/outro condicional, plan #44) — ese
  vive en `engine.py`/`prompts.py` y se atiende en un plan separado
  (`46_prompts-engine-fluidez-conversacional.md`) para no mezclar el riesgo
  de dos áreas de código distintas en un mismo diff.
- No expandir el cálculo de match-por-tipo a otros parámetros multi-valor
  (zonas múltiples, operaciones múltiples) — alcance acotado a `tipo`, que es
  el único parámetro multi-valor que existe hoy (plan #42).

## Skills / MCP / Workflow recomendados

- TDD: extender `tests/v3/test_multi_tipo_search.py` (o crear un archivo
  hermano) con casos parametrizados: 1 resultado singular, 2+ resultados
  plural, multi-tipo con match parcial, multi-tipo con 0 matches del tipo
  agregado.
- `code-review` sobre el diff antes de commitear — toca una tool en
  producción activa (WhatsApp, tenant `default`, ~54 propiedades).
- Verificar con `pytest tests/v3/ -q` offline (sin Docker ni DB real) antes
  de cualquier push, igual que el plan #42.

## Bitácora

- 2026-07-02: plan creado. Diagnóstico hecho en sesión previa sobre una
  conversación de test real: identificado que `_tipo_plural_label` ignora el
  count (causa el bug de plural), que `_build_missing_criteria_tip` ignora
  el count (ofrece filtrar con 1 solo resultado), y que no hay lógica de
  match-parcial-por-tipo en búsquedas multi-tipo (la respuesta no aclara
  cuándo un tipo agregado no matcheó nada). Separado de
  `46_prompts-engine-fluidez-conversacional.md` (framing/prompt) por área de
  código, mismo criterio que separó los planes #42 y #43.

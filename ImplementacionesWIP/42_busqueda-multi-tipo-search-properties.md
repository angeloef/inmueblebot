---
id: busqueda-multi-tipo
area: Backend (bot / search tool)
priority: P1
status: completed
depends_on: []
related_areas: [v3-prompts, v4-prompts-inherit, tests-v3]
---

## Problema

Cuando un usuario le pide al bot algo como *"busco departamento o casa cerca de
la municipalidad"* o *"depto o casa en alquiler hasta $300000"*, el bot solo
busca **un** tipo de propiedad (el LLM elige uno arbitrariamente), en vez de
devolver ambos tipos que cumplan el resto de los filtros. Caso real observado
en WhatsApp con la inmobiliaria en producción (tenant `default`, ~54
propiedades, `active_router=v4`):

> Usuario: "hola buenas tardes estoy buscando un departamento o casa cerca de
> la municipalidad"
> Bot: buscó solo `tipo=departamento`, ignorando "casa".

Root cause confirmado (no re-diagnosticar): `search_properties` en
[`app/tools/v2/search_properties.py`](../app/tools/v2/search_properties.py)
trata `tipo` como **string singular**. En la función `search_properties`
(actualmente ~línea 228-279): `mapped_tipo = tipo_map.get(tipo.lower(),
tipo.lower())` seguido de `stmt.where(Property.category == mapped_tipo)`. No
hay soporte de lista, y el prompt (`app/routers/v3/prompts.py`) tampoco le dice
al LLM cómo pasar múltiples tipos, así que en la práctica el modelo elige uno.

## Contexto

**Opción evaluada y descartada:** emitir múltiples `tool_calls` de
`search_properties` (uno por tipo) y fusionar resultados en
`app/routers/v3/engine.py` `_assemble_response` (~líneas 812-849). Se descarta
porque esa función ya tiene un bug real de by-design: hace `break` en el
primer match de `search_properties` en `tools_used`/`tool_results` y descarta
cualquier segunda llamada al mismo tool en el mismo turno (el resultado
sencillamente se pierde, sin error visible). Arreglar eso es un cambio aparte,
de mayor riesgo (toca el renderizado verbatim que ya tuvo varios bugs de
formato documentados en los comentarios del propio archivo). **No tocar
`app/routers/v3/engine.py` en este plan.**

**Opción elegida:** que `tipo` acepte **múltiples valores en una sola
llamada**, vía string separado por comas (ej. `"departamento,casa"`). Se elige
CSV y no array porque la tool se invoca con argumentos JSON-string-encoded
(ver nota en `app/routers/v3/schema.py:8`: `tool_calls[].arguments is a
JSON-encoded string`) — mantener `tipo` como `string` en el schema OpenAI-style
es el cambio más chico y menos invasivo; parsear el CSV dentro de
`search_properties` mismo.

**Archivos con anclas reales a tocar:**

1. `app/tools/v2/search_properties.py`
   - Firma de `search_properties(...)`: `tipo: str = ""` sigue como está en la
     firma (sigue siendo un string, ahora con semántica CSV: `"departamento"`
     o `"departamento,casa"`).
   - Reemplazar el mapeo singular `mapped_tipo = tipo_map.get(...)` por un
     parseo a lista: split por coma, strip, aplicar `tipo_map` a cada término,
     descartar vacíos y duplicados preservando orden.
   - Filtro WHERE: `Property.category == mapped_tipo` → `Property.category.in_(mapped_tipos)` (cuando hay >1; con exactamente 1 elemento el `.in_()` funciona igual, no hace falta ramificar).
   - Revisar TODOS los usos de `mapped_tipo`/`tipo` en cascada de fallback
     (fallback1/2/3 dentro de la misma función, aprox. líneas 296-380) y en
     `_describe_filters`, `_format_properties_list`, `_build_missing_criteria_tip`,
     y el bloque de telemetría (`_record_search_telemetry`) — todos asumen hoy
     un tipo singular para pluralizar palabras ("departamentos") o filtrar
     listas (`p.category == mapped_tipo`). Deben generalizarse a listas: p.ej.
     "No encontré departamentos ni casas..." cuando hay 2+ tipos, singular
     cuando hay 1, para no romper la redacción actual.
   - Confirmar que sigue funcionando igual con un solo tipo (retrocompatibilidad
     total — no debe cambiar ningún test existente ni el comportamiento con las
     54 propiedades reales del tenant `default`).
   - Este cambio debe **combinarse libremente** con todos los demás filtros ya
     soportados en la misma llamada: `operation`, `zona` (incluye matching
     contra `reference_points`, integrado recientemente — ver `_build_zone_filters`
     y `_strip_proximity`), `presupuesto_max`, `dormitorios`/`dormitorios_max`/
     `bedrooms_match`, `ambientes`/`ambientes_max`/`ambientes_match`. Ejemplo de
     caso a soportar con una sola llamada: *"depto o casa en alquiler cerca del
     hospital hasta $300000"*.

2. `app/tools/v2/registry.py`
   - Definición de la tool `search_properties` (~línea 58-128, campo `"tipo"`
     dentro de `parameters.properties`, ~línea 78-84): actualizar la
     `description` para indicar el formato CSV multi-tipo, con ejemplo.
   - `validate_tool_args` (línea 384) **no necesita cambios** — ya se
     verificó que solo chequea `required` (vacío para `search_properties`), no
     valida el valor de `tipo` contra un enum. Confirmarlo en la ejecución, no
     asumir sin revisar si el código cambió.
   - Hay una segunda definición de `tipo` (~línea 339 y ~366, probablemente
     definiciones de otras tools como `capture_lead`/`qualify_lead` en
     `app/routers/v4/prompts.py` que también mencionan `zona`/`tipo` como
     parámetro simple) — decidir si esas también deben aceptar CSV o si quedan
     fuera de alcance (probablemente fuera de alcance: son para *un* lead, no
     una búsqueda multi-tipo). Confirmar antes de tocarlas.

3. `app/routers/v3/prompts.py`
   - Descripción de la tool `search_properties` dentro del prompt estático
     (línea ~34, la misma línea que ya se tocó recientemente para el fix de
     `reference_points`): agregar que `tipo` acepta múltiples valores
     separados por coma cuando el usuario menciona más de un tipo ("depto o
     casa" → `tipo:"departamento,casa"`).
   - Agregar UN ejemplo few-shot nuevo en la sección de ejemplos existente
     (busca el bloque de ejemplos alrededor de las líneas 111-151) que combine
     multi-tipo con otro criterio, ej.: "busco depto o casa en alquiler cerca
     del hospital hasta $300000" → `tool_calls:[{name:search_properties,
     arguments:{"operation":"alquiler","tipo":"departamento,casa","zona":"hospital","presupuesto_max":300000}}]`.

4. `app/routers/v4/prompts.py`
   - **No requiere cambios propios.** V4 embebe el prompt de V3 vía
     `_V3_PROMPT = _v3_build()` (línea 16) y despacha tools vía
     `_execute_tools` de `app/routers/v3/engine.py` (confirmado en sesión
     previa). Este punto es una **verificación a incluir en el plan**, no una
     tarea de código: correr o inspeccionar el prompt final de V4 y confirmar
     que el texto nuevo de `search_properties` efectivamente aparece ahí
     (import-time constant, se recalcula solo si se reinicia el proceso).

5. Tests de regresión — extender/crear en `tests/v3/` (estilo
   `tests/v3/test_bedrooms_range.py` o `tests/v3/test_city_variants_matrix.py`
   para el patrón de casos parametrizados). Casos mínimos a cubrir:
   - Un solo tipo (retrocompatibilidad — comportamiento idéntico al actual).
   - Dos tipos CSV (`"departamento,casa"`) → resultado incluye ambos.
   - Tipo múltiple + `zona` (incluye el caso de reference_points, ej. "cerca
     del hospital").
   - Tipo múltiple + `presupuesto_max` + `dormitorios`.
   - Un tipo inválido mezclado con uno válido (ej. `"departamento,invencionrara"`)
     → debe ignorar el inválido sin crashear ni devolver 0 resultados por su culpa.
   - Mensajes de "no encontré" con 2+ tipos: verificar que la redacción sea
     coherente en plural (no repetir literalmente "departamentos" cuando el
     usuario pidió depto+casa).

## Criterios de aceptación

- `search_properties(tipo="departamento,casa", ...)` devuelve propiedades de
  AMBOS tipos que cumplan el resto de los filtros, en una sola llamada/query.
- `search_properties(tipo="departamento", ...)` (un solo valor) se comporta
  exactamente igual que hoy — todos los tests existentes que la ejercitan
  siguen en verde sin modificarlos.
- Combinable sin restricciones con `operation`, `zona` (incluye matching de
  `reference_points`), `presupuesto_max`, `dormitorios*`, `ambientes*` en la
  misma llamada.
- Mensajes de fallback ("no encontré...", `_describe_filters`,
  `_format_properties_list`, tip de "podés filtrar por...") leen naturalmente
  en español tanto con 1 tipo como con 2+ tipos.
- El prompt de V3 (heredado por V4) refleja el nuevo formato CSV con al menos
  un ejemplo few-shot combinando multi-tipo + otro criterio.
- Suite de tests offline (`pytest tests/v3/ -q` o el subconjunto relevante) en
  verde antes de cualquier despliegue. No requiere tocar la DB de prod — es un
  cambio de código puro, los datos reales (54 propiedades del tenant
  `default`) ya sirven para probarlo manualmente en V4 vía WhatsApp una vez
  deployado.

## Fuera de alcance

- No tocar `app/routers/v3/engine.py` ni `_assemble_response` (esa es la
  Opción A descartada; el bug de `break`/pérdida de la segunda llamada a
  `search_properties` en el mismo turno queda documentado pero sin arreglar
  acá).
- No tocar `app/routers/v4/prompts.py` salvo para verificar (no para editar) —
  hereda el prompt de V3 automáticamente.
- No modificar `capture_lead`/`qualify_lead` (tools V4) a menos que la
  investigación en registry.py confirme que comparten el mismo parámetro
  `tipo` de forma que rompa algo — de ser así, es una decisión a confirmar con
  el usuario antes de tocarlas, no asumir.
- No escribir datos ni migrar la DB de prod — este plan es 100% cambio de
  código.
- No expandir a otros parámetros multi-valor (ej. múltiples zonas, múltiples
  operaciones) — el pedido explícito es solo `tipo`.

## Skills / MCP / Workflow recomendados

- TDD: escribir primero los casos de test parametrizados (retrocompat + CSV +
  combinaciones), luego implementar el parseo CSV y el `.in_()`.
- `python-reviewer` / `security-reviewer` no aplica de forma crítica acá (no
  hay input de usuario final sin sanitizar más allá de lo que ya sanitiza
  `_norm_accents`/`_zone_like`), pero correr `code-review` sobre el diff antes
  de commitear es razonable dado que toca una tool en producción activa.
- Verificar con `pytest tests/v3/ -q` (o el archivo nuevo específico) offline,
  sin Docker ni DB real, antes de cualquier push. Si existe infraestructura de
  eval (`tests/eval/`), un caso adicional en `tests/eval/cases/dev.jsonl` con
  un turno multi-tipo es un buen agregado opcional, no obligatorio.

## Bitácora
- 2026-07-01: plan creado. Diagnóstico previo ya hecho en sesión: causa raíz
  confirmada en `search_properties.py` (tipo singular) y en `engine.py`
  `_assemble_response` (bug de `break` en múltiples tool_calls del mismo tool,
  documentado pero fuera de alcance de este plan por decisión explícita del
  usuario). Confirmado que `validate_tool_args` no restringe `tipo` por enum.
  Confirmado que V4 hereda el prompt de V3 sin cambios propios necesarios.
- 2026-07-01: implementado por implementador-loop. `status` del frontmatter
  venía en español (`pendiente`) — no lo reconocía el picker (`pick-next.sh`
  solo matchea `pending|in_progress|completed`); corregido a `pending` para
  que el loop lo levante.
  Cambios: `_parse_tipos()` + `_TIPO_MAP` a nivel de módulo en
  `search_properties.py` (CSV → lista deduplicada, cap de 10 términos —
  `ponytail:` insurance contra CSV degenerado); `Property.category == mapped_tipo`
  → `.in_(mapped_tipos)` en la query principal y las 3 fallbacks +
  `_count_same_type_elsewhere`; `_tipo_plural_label()` reemplaza la
  pluralización singular en mensajes ("departamentos y casas"); `_describe_filters`
  actualizado para multi-tipo sin romper su firma (test de regresión existente
  en `tests/test_chat5_fixes_regression.py` sigue en verde sin tocarlo).
  Prompt (`app/routers/v3/prompts.py`): descripción de `search_properties`
  actualizada + 1 ejemplo few-shot nuevo (multi-tipo + zona + presupuesto).
  Tuve que reformular 2 frases para no violar el cap de "negativos duros"
  (`test_negative_rule_ratio_under_cap` en `test_prompt_cache.py`) — quité
  "NUNCA" y lo reescribí en positivo.
  `registry.py`: descripción de `tipo` actualizada con el formato CSV.
  V4 verificado (no modificado): `_SYSTEM_PROMPT_V4` hereda el texto nuevo vía
  `_V3_PROMPT = _v3_build()` — confirmado con un check directo en runtime
  dentro de Docker.
  Tests nuevos: `tests/v3/test_multi_tipo_search.py` (parseo CSV, pluralización,
  `_describe_filters` multi-tipo — todo offline, sin DB).
  Gates: lint (ruff, sin errores nuevos — 12 E501 preexistentes en el archivo
  no tocados por este diff), `pytest tests/v3/ -q` → 325 passed/2 skipped/
  3 xfailed, `pytest tests/ -q` full suite → mismas ~103 fallas preexistentes
  no relacionadas (auth/billing/jobs_engine/DB de test sin migrar — documentado
  en memoria `docker-test-baseline`), ninguna toca los 3 archivos de este plan.
  `security-reviewer`: sin hallazgos (confirmó `.in_()` parametrizado, RLS/
  tenant scoping intacto en las 4 rutas de query, sin riesgo de inyección);
  sugirió cap defensivo de longitud → aplicado.
  Fuera de alcance respetado: no se tocó `engine.py`/`_assemble_response` ni
  `capture_lead`/`qualify_lead`.

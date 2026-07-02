---
id: prompts-engine-fluidez-conversacional
area: Backend (bot / prompts.py + engine.py — reglas de conversación)
priority: P1
status: completed
depends_on: []
related_areas: [v3-prompts, v3-engine, v4-prompts-inherit, v4-engine-inherit, tests-v3, framing-plan-44]
---

## Problema

Sobre una conversación de test real (2026-07-02, ver bitácora) se identificaron
tres fallas de fluidez que **no son del tool de búsqueda** (eso va en el plan
`45_search-properties-redaccion-sensible-al-count.md`) sino de las reglas y
ejemplos del prompt del engine, más una falta de guard de código:

1. **Doble pregunta en un mismo mensaje.** Cuando `search_properties` ya
   devuelve un bloque que termina en pregunta (narrowing progresivo — "muchos
   resultados, ¿en qué zona?"), el engine a veces agrega un `framing.outro`
   con OTRA pregunta encima ("¿Querés que te muestre fotos o coordinamos una
   visita?"), violando la propia regla de "una sola pregunta por mensaje".
   El propio ejemplo del prompt enseña este patrón sin la salvedad necesaria.
2. **El bot repite el bloque de resultados idéntico ante preguntas de
   confirmación.** Ante "¿solo esa tienen?" (sin ningún criterio nuevo), el
   engine vuelve a ejecutar `search_properties` y devuelve el mismo texto por
   tercera vez en la conversación, en vez de responder desde el estado ya
   mostrado. El prompt tiene un ejemplo para preguntas comparativas ("¿cuál
   tiene más ambientes?") pero ninguno para preguntas de confirmación de
   disponibilidad, y la regla de "buscá ya, no demores" dominaba sin
   contrapeso.
3. **El acknowledge-first no reconoce atributos que no son filtro.** Cuando
   el usuario pide "una casa con patio", el bot ignora "patio" por completo
   (no es un parámetro de `search_properties`) y no lo menciona ni siquiera
   en el reconocimiento inicial — sale un clarify seco: "¿Buscás alquilar o
   comprar?".

## Contexto

**1. Doble pregunta — `app/routers/v3/prompts.py` + `app/routers/v3/engine.py`:**

- El ejemplo problemático está en `prompts.py:105`: `BUENO (primera
  búsqueda) → framing:{intro:"...", outro:"¿Querés que te muestre fotos o
  coordinamos una visita?"}`. No aclara que esto solo aplica cuando el bloque
  de datos NO termina ya en una pregunta propia. La sección completa "CAMPO
  framing" está en `prompts.py:80-109` (introducida por el plan #44).
- El caso que dispara el bug: `_next_filter_question` en
  `app/tools/v2/search_properties.py:101-118` devuelve texto que ya termina
  en `?` cuando hay demasiados resultados sin zona/dormitorios/presupuesto
  definidos.
- `_apply_framing(turn, verbatim_text)` en `engine.py:704-724` (plan #44):
  concatena `intro + verbatim_text + outro` sin ningún chequeo de si
  `verbatim_text` ya es una pregunta. Es el único punto de "framing" en este
  codebase que no tiene un guard de código — contrasta con `_safe_framing_part`
  (`engine.py:696-701`), que sí valida longitud/seguridad antes de usar el
  texto del LLM. `_apply_framing_intro_only` (`engine.py:727+`) es la
  variante usada para booking — no le aplica este bug porque nunca agrega
  outro.

**2. Repetición ante preguntas de confirmación — `app/routers/v3/prompts.py`:**

- Regla 46 (taxonomía intent→action, línea 46): "TAMBIÉN cuando el usuario
  refina una búsqueda anterior con un criterio nuevo... RE-ejecutá
  search_properties... no demores" — está redactada de forma amplia y no
  distingue "criterio nuevo real" de "pregunta retórica/de confirmación
  sobre lo ya mostrado".
- Regla 3b (línea 125): "PROHIBIDO... Nunca demores una búsqueda al
  siguiente turno" — refuerza el sesgo hacia re-buscar.
- El ejemplo existente que SÍ cubre "responder desde el estado sin
  herramientas" está en `prompts.py:172-175` ("¿cuál tiene más ambientes?" →
  `action:clarify`, sin tools) — pero es una pregunta comparativa, no una de
  confirmación de disponibilidad ("¿es la única?", "¿solo esa tienen?").
  Falta ese caso en los ejemplos.
- El estado ya trae `ultima_busqueda` (ver `engine.py:195` y el comentario en
  `engine.py:553`) con el texto exacto ya mostrado — la información para
  responder sin re-buscar ya está disponible, es puramente un problema de
  qué ejemplo/regla sigue el modelo.

**3. Acknowledge-first sin cobertura de atributos no filtrables —
`app/routers/v3/prompts.py`:**

- La sección "ACKNOWLEDGE-FIRST en clarify y saludo" (`prompts.py:111-119`,
  plan #44) tiene un solo ejemplo, sobre zona ("busco algo en el centro").
  No hay ejemplo para un atributo que `search_properties` no soporta como
  parámetro (patio, cochera, pileta — no están en el catálogo de la línea 34).

## Criterios de aceptación

- Un turno donde el bloque de datos (verbatim) ya termina en `?` (narrowing
  progresivo, sin resultados, etc.) nunca llega al usuario con una segunda
  pregunta agregada por `framing.outro` — verificable con un test que arme
  un `verbatim_text` terminado en `?` y confirme que `_apply_framing` lo
  devuelve sin outro sin importar qué mande `turn.framing`.
- Una pregunta de confirmación sobre resultados ya mostrados ("¿solo esa
  tienen?", "¿es la única?") no dispara una nueva llamada a
  `search_properties` — se responde desde `ultima_busqueda` del estado. Un
  criterio de búsqueda genuinamente nuevo (zona, tipo, presupuesto,
  dormitorios) sigue disparando una búsqueda nueva igual que hoy — no
  romper la regla 46 para el caso legítimo.
- Un mensaje que incluye un atributo no soportado como filtro ("con patio",
  "con cochera") lo reconoce en el texto de acknowledge-first, sin
  inventar que se usó como filtro de búsqueda.
- El guard de doble pregunta vive en **código** (`_apply_framing`), no solo
  en el prompt — que sobreviva aunque el LLM no siga la instrucción al pie
  de la letra (mismo principio que `_wrap_text_is_safe`/`_safe_framing_part`
  en `engine.py`).
- Suite `pytest tests/v3/ -q` en verde, incluyendo los tests existentes del
  plan #44 (`tests/v3/test_response_framing.py` o el nombre que haya
  quedado) sin romperlos.
- V4 hereda los cambios de prompt automáticamente (mismo mecanismo
  verificado en los planes #42/#43/#44 — `_V3_PROMPT = _v3_build()` en
  `app/routers/v4/prompts.py:16`); confirmar con una inspección del prompt
  final de V4, no asumir.

## Fuera de alcance

- No tocar `app/tools/v2/search_properties.py` — eso es
  `45_search-properties-redaccion-sensible-al-count.md`, un plan separado
  para no mezclar el riesgo de dos áreas de código en un mismo diff.
- No rediseñar el mecanismo de `framing` en sí (campo, schema, call-sites) —
  eso ya está construido y en producción (plan #44); este plan solo cierra
  un gap puntual (doble pregunta) con un guard adicional.
- No agregar `patio`/`cochera`/`pileta` como parámetros reales de
  `search_properties` (eso implicaría tocar el tool y la DB/`extra_data`) —
  el alcance acá es solo que el bot los **reconozca en el texto**, no que
  los use como filtro duro. Si se decide filtrar por esos atributos más
  adelante, es un plan aparte.
- No relajar la regla de "buscá ya, no demores" para criterios de búsqueda
  genuinamente nuevos — el ajuste es acotar cuándo aplica, no debilitarla.

## Skills / MCP / Workflow recomendados

- TDD: el test del guard de doble pregunta (`_apply_framing` con
  `verbatim_text` terminado en `?`) se escribe antes del cambio de código —
  es el criterio más objetivo y barato de verificar.
- Prueba conversacional manual vía `/simulate/multi` (o WhatsApp test)
  reproduciendo el guion exacto de la conversación de test que originó este
  plan, para confirmar que las 3 fallas específicas ya no ocurren.
- `code-review` de subagente sobre el diff — toca reglas de conversación en
  producción activa (WhatsApp, tenant `default`) con historial de bugs reales
  documentado en los comentarios de `engine.py` y en los planes #42/#43/#44.
- Verificar en Docker (`docker cp` + `docker exec`, patrón de
  `docker-test-baseline`): `pytest tests/v3/ -q` completo.

## Bitácora

- 2026-07-02: plan creado. Diagnóstico hecho en sesión previa sobre una
  conversación de test real (WhatsApp, tenant `default`): 4 problemas de
  fondo identificados, 2 de ellos (pluralización y tips sensibles al count)
  van en `45_search-properties-redaccion-sensible-al-count.md`; los otros 2
  (doble pregunta por falta de guard + falta de few-shot para preguntas de
  confirmación) más el gap de acknowledge-first para atributos no filtrables
  quedan acá, agrupados porque tocan `prompts.py`/`engine.py` — la misma
  área que el plan #44 (framing), del que este plan es un refinamiento
  puntual, no un reemplazo.
- 2026-07-02: implementado. Guard de doble pregunta en código:
  `_apply_framing` (`engine.py:704-729`) ahora descarta `outro` cuando
  `verbatim_text` ya termina en `?` — con test (`test_response_framing.py`,
  2 tests nuevos). Prompt: regla 46/3b acotadas para distinguir criterio
  nuevo de pregunta de confirmación + nuevo few-shot ("¿solo esa tienen?");
  nuevo ejemplo de acknowledge-first para atributos no filtrables ("con
  patio"). `pytest tests/v3/ -q` → 339 passed, 2 skipped, 3 xfailed.
  V4 confirmado heredando los 3 cambios (`_SYSTEM_PROMPT_V4` contiene las
  frases nuevas, verificado por inspección directa del prompt final).
  security-reviewer sobre el diff: sin hallazgos. Gate de Chrome MCP UX no
  aplica (sin cambios de UI, solo backend/prompt).

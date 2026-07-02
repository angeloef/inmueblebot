---
id: framing-nativo-engine-respuestas
area: Backend (bot / schema + prompts + engine.py — response assembly)
priority: P1
status: completed
depends_on: []
related_areas: [v3-engine, v3-schema, v3-prompts, v4-engine-inherit, v4-prompts, tests-v3, eval-harness]
---

## Problema

Las respuestas del bot v4 se sienten robóticas, sobre todo al arranque de la
conversación: cuando el usuario pide una propiedad, el bot responde
directamente con la lista o con una pregunta seca, sin una sola frase de
atención al cliente antes. Reportado explícitamente por el usuario en sesión.

Dos causas confirmadas (no re-diagnosticar):

1. **Búsquedas/detalles salen verbatim, sin envoltorio.** El plan #43 ya
   construyó un mecanismo de intro/outro (`_wrap_verbatim_with_intro_outro`,
   `app/routers/v3/engine.py:696-760`), pero: (a) está detrás de
   `CONVERSATIONAL_WRAP_ENABLED` (`app/core/config.py:242`, default **False**,
   no seteado en Render → en prod hoy sale la lista pelada); (b) es una
   **segunda llamada LLM** que solo ve `user_message`, sin historia/estado →
   intros genéricas; (c) es incondicional cuando el flag está on (envuelve
   siempre, aporte o no — el usuario pidió explícitamente que esto NO sea así).
2. **Clarify y saludos salen secos por diseño del prompt.** Las reglas de
   estilo de `_SYSTEM_PROMPT` (`app/routers/v3/prompts.py:81` "saludos en ≤15
   palabras", `:96-98` "una sola pregunta, no repitas datos") producen
   respuestas tipo "¿Buscás alquilar o comprar?" sin reconocer antes lo que la
   persona pidió.

Además, en cada turno con tools el engine ya redacta un placeholder de
`response_plan` que **se descarta por diseño** ("AHORRO DE TOKENS",
`prompts.py:70-78`) — es decir, el modelo con todo el contexto (historia,
estado, memoria) ya "habla" en cada turno, pero ese texto se tira. Ese es el
canal que este plan reutiliza en vez de agregar una llamada nueva.

## Contexto

**Dirección acordada con el usuario (sesión de diseño previa, no rediseñar):**
el engine emite el envoltorio conversacional **en su única llamada
estructurada existente** — cero llamadas LLM extra — y **lo emite como
`null` cuando no aporta**, con reglas explícitas en el prompt de cuándo sí y
cuándo no. El bloque de datos duros (precio/specs/ID) sigue siendo Python
puro e intocable, igual que en el #43; este plan cambia *dónde* se genera el
envoltorio (dentro de la llamada 1, no en una llamada 2) y lo hace
condicional en vez de incondicional. **Supersede y reemplaza el mecanismo del
plan #43**, que queda eliminado (el flag nunca se prendió en prod).

**1. `app/routers/v3/schema.py`** — campo nuevo top-level `framing`:
- `TURN_JSON_SCHEMA` (líneas 38-182, strict mode: todo key en `required`,
  nullable vía `["type","null"]`): agregar `"framing": {intro: string|null,
  outro: string|null}`, ambos required-pero-nullable (patrón ya usado por
  `missing_slot`).
- Pydantic (`schema.py:223-232`): `class Framing(BaseModel): intro:
  str|None=None; outro: str|None=None` y `TurnOutput.framing: Framing =
  Framing()`. El default es obligatorio — `_apply_fallback` en engine.py
  construye `TurnOutput` a mano y no debe romper.
- **V4 hereda solo, verificar no asumir:** `app/routers/v4/schema.py:98-113`
  hace `{**_v3_inner["properties"], ...}` y copia `_v3_inner["required"]` a
  import-time; `TurnOutputV4` extiende `TurnOutput`. Un campo nuevo en V3
  debería aparecer en V4 sin tocar `v4/schema.py` — confirmar con un check de
  import, no solo asumirlo. Lo único V4-propio a tocar es la lista de campos
  en "DISCIPLINA DE OUTPUT V4" (`app/routers/v4/prompts.py:60-64`).

**2. `app/routers/v3/prompts.py`** — la condicionalidad vive acá, es la parte
más importante del plan:
- Sección nueva "CAMPO framing" en `_SYSTEM_PROMPT`: cuándo `intro`/`outro`
  aportan (primera búsqueda de la conversación, criterios nuevos, resultado
  vacío, booking confirmado) vs. cuándo van `null` (refinamiento de una
  búsqueda ya mostrada, ficha de detalle pedida por ID/posición, flujo de
  fotos, dos búsquedas seguidas en el mismo hilo). Prohibiciones explícitas
  (mismas del #43): nunca precios/IDs/specs en el envoltorio, nunca afirmar
  un filtro no aplicado, máx. 1 frase por campo, no repetir una intro ya
  usada en la conversación (está en el historial que el engine ya ve).
  3-4 ejemplos BUENO/MALO.
- Reglas **acknowledge-first** para clarify y el saludo del primer turno
  (estos NO usan `framing`, su texto ya sale de `response_plan`): en clarify,
  espejar lo que el usuario pidió antes de la pregunta única ("¡Buenísimo! Te
  ayudo a encontrar un depto en el centro 🙂 ¿Buscás alquilar o comprar?" en
  vez de solo "¿Buscás alquilar o comprar?"); en el primer turno (estado/
  historial vacíos), una bienvenida real con el nombre de la inmobiliaria —
  la regla "≤15 palabras" queda solo para saludos con conversación en curso.
- Actualizar "DISCIPLINA DE OUTPUT" (líneas 104-107) agregando `framing` a la
  lista de campos requeridos. La regla del placeholder descartable en
  `response_plan` no cambia.

**3. `app/routers/v3/engine.py`** — dónde se aplica (`_assemble_response`,
líneas 765-968):
- Helper nuevo `_apply_framing(turn, verbatim_text) -> str`: lee
  `turn.framing`, pasa cada miembro por `_wrap_text_is_safe`
  (`engine.py:686-693`, guard existente anti-leak de `$`/`id:` — reutilizar,
  no reescribir) + un cap de longitud; miembro inválido → tratado como null;
  concatena solo las partes presentes; con `intro`/`outro` ambos null
  devuelve el bloque **byte-idéntico**. Sin intro fija de fallback (a
  diferencia del #43): si no hay framing válido, silencio, no plantilla.
- Reemplaza `_wrap_verbatim_with_intro_outro` en el call-site de Path 0b2
  (search/details verbatim, líneas 894-937).
- Aplicar también en Path 0a-appt (gestión de citas verbatim, líneas
  825-835) y, **solo `framing.intro`**, en Path 0b-booked (booking exitoso,
  líneas 861-864 — la confirmación real ya trae fecha/dirección/cierre,
  decisión LOCKED de scheduling-bulletproof, no tocar el outro ahí) y en el
  tail multi-intent (líneas 917-933, mismo criterio que el #43: el tail
  sintetizado ya cierra solo).
- **No tocar:** flujo de fotos (CTA determinista LOCKED), gates de seguridad
  (emergencia/abuso/cap/out-of-scope), abstención KA3, mensajes FSM,
  clarify/smalltalk (se mejoran vía prompt, no vía framing).
- Borrar `_wrap_verbatim_with_intro_outro`, `_WRAP_DEFAULT_INTRO` y el flag
  `CONVERSATIONAL_WRAP_ENABLED` (`app/core/config.py:242` + toda referencia).

**4. `app/core/config.py`** — flag nuevo `RESPONSE_FRAMING_ENABLED`, default
**True** (a diferencia del #43: acá es kill-switch de prod, no experimento —
no hay llamada extra que justifique arrancar apagado).

**5. Tests** — `tests/v3/test_conversational_wrap.py` (el del #43) se
reemplaza por `tests/v3/test_response_framing.py`, mismo espíritu (bloque
verbatim byte-idéntico como criterio no-negociable, con precios reales tipo
`$35.976`/`$85.000.000` sin drift) más los casos nuevos de condicionalidad y
del guard reutilizado. `tests/v3/test_multi_tool_concat.py` y
`tests/v3/test_compact_search_summary.py` son referencia de estilo y deben
seguir en verde sin tocarlos.

**Costo/latencia esperado:** -1 llamada LLM por búsqueda respecto al #43 con
el flag prendido (el framing viaja en la llamada 1 que ya existe, no en una
llamada 2). +~40-80 tokens de output en turnos con framing, ~0 en turnos con
`null/null`. El schema+prompt nuevos rompen el prompt cache una vez por
deploy (esperado, no recurrente).

## Criterios de aceptación

- **No negociable:** el bloque de datos duros llega byte-a-byte idéntico al
  que genera `_format_properties_list`/las tools, con framing presente,
  ausente, inválido o con el flag apagado. Test de igualdad/substring exacto,
  no "similar".
- La condicionalidad es real y observable, no decorativa: un refinamiento de
  búsqueda ("¿y en el centro?") NO trae intro; una primera búsqueda SÍ; una
  ficha de detalle trae a lo sumo outro. Verificable con prueba manual +
  casos de test dedicados.
- Intro/outro nunca contienen precios, IDs, ni afirman un filtro no aplicado
  — garantizado por guard de código (`_wrap_text_is_safe` reutilizado), no
  solo por instrucción de prompt.
- Cero llamadas LLM adicionales por turno respecto a hoy (verificable:
  `rich_content["llm_calls"]` en V4 sigue en 1 para una búsqueda simple).
- Clarify reconoce el pedido del usuario antes de preguntar; el saludo del
  primer turno presenta al bot/inmobiliaria; ninguno de los dos inventa datos
  no confirmados por el estado.
- El mecanismo del plan #43 (`_wrap_verbatim_with_intro_outro`,
  `_WRAP_DEFAULT_INTRO`, `CONVERSATIONAL_WRAP_ENABLED`) queda eliminado —
  un solo mecanismo vivo en el repo.
- V3 y V4 se comportan igual (comparten `_assemble_response`); si difieren en
  algo, queda documentado como intencional en la bitácora.
- `RESPONSE_FRAMING_ENABLED=false` vuelve al verbatim 100% puro sin requerir
  otro deploy de código.
- Suite `pytest tests/v3/ -q` en verde (incluye los tests existentes citados
  arriba, sin modificarlos salvo para hacerlos pasar por el nuevo call-site).

## Fuera de alcance

- Modos de personalidad, plantillas de tono por tenant, A/B de estilos de
  respuesta — over-engineering explícitamente vetado (misma decisión del
  #43, reconfirmada acá).
- Tocar el flujo de fotos, su CTA, el texto de confirmación de booking o los
  gates de seguridad — son decisiones LOCKED de planes previos
  (scheduling-bulletproof, photo-delivery).
- Regenerar/resumir el bloque de resultados con LLM en cualquier escenario —
  patrón que ya causó bugs reales (truncamiento, drift `$35,976` vs
  `$35.976`, filtros fantasma) y que el #43 y este plan evitan estructuralmente.
- Tocar `_format_properties_list` o `app/tools/v2/search_properties.py`.
- Arrancar el flag apagado "para después": si la verificación/eval mostrara
  una regresión de calidad, el plan no se shippea (no se shippea con
  `RESPONSE_FRAMING_ENABLED=False` a la espera de una decisión futura — eso
  es exactamente lo que dejó al #43 sin efecto en prod).

## Skills / MCP / Workflow recomendados

- TDD: escribir primero `tests/v3/test_response_framing.py` (el caso
  byte-idéntico no-negociable, antes que el helper `_apply_framing`).
- `/ponytail full` para el helper de assembly: es reutilizar un guard
  existente + ~20-30 líneas de concatenación condicional, no un sistema de
  templating.
- Verificar en Docker (`docker cp` + `docker exec`, patrón de
  `docker-test-baseline`): `pytest tests/v3/ -q` completo, no solo el archivo
  nuevo.
- `tests/eval/` (runner + graders + baselines existentes) para medir
  score/latencia antes vs. después en V3 y V4 — con llamadas LLM iguales (no
  hay llamada extra), no debería haber regresión de latencia; confirmar con
  el dato, no asumir.
- `code-review` de subagente sobre el diff final antes de commitear — toca un
  camino de respuesta en producción activa (WhatsApp, tenant `default`) con
  historial de bugs reales documentados en los propios comentarios de
  `engine.py`.

## Bitácora

- 2026-07-02: plan creado. Contexto: usuario reportó que las respuestas de
  v4 se sienten robóticas al arranque de la conversación (lista/pregunta
  seca sin atención al cliente). Diagnóstico hecho en sesión previa: el wrap
  del #43 sigue apagado en prod (flag default False, nunca seteado en
  Render), y aunque se prendiera sería incondicional y sin contexto real
  (segunda llamada que solo ve el mensaje del usuario). Usuario pidió
  explícitamente que el envoltorio sea condicional — no aplicarlo siempre —
  y que la mejora sea comprensiva a todas las respuestas del bot, no solo
  búsquedas. Diseño acordado: mover el envoltorio a la llamada 1 del engine
  (campo `framing`, nullable) con la condicionalidad definida en el prompt;
  reusar el guard anti-leak del #43; cubrir search/details, gestión de
  citas, booking (solo intro) y el tail multi-intent (solo intro); mejorar
  clarify/saludo por una vía distinta (acknowledge-first en el prompt, sin
  campo nuevo) porque su texto ya sale del LLM sin pasar por verbatim. Fotos,
  gates de seguridad y FSM quedan fuera por decisiones LOCKED previas. Flag
  nuevo arranca en True (a diferencia del #43) porque no hay llamada extra
  que justifique un default apagado.
- 2026-07-02: implementado y verificado en Docker local. `schema.py`: campo
  `Framing{intro,outro}` (nullable, strict-mode) agregado a `TURN_JSON_SCHEMA`/
  `TurnOutput`; V4 lo hereda por spread (confirmado con check de import, no
  asumido: `framing` aparece en `TURN_JSON_SCHEMA_V4.properties`/`.required`).
  `prompts.py` (V3): sección "CAMPO framing" con reglas de cuándo aporta/cuándo
  null + 5 ejemplos BUENO/MALO, más reglas ACKNOWLEDGE-FIRST para clarify y
  saludo de primer turno; `DISCIPLINA DE OUTPUT` actualizada. Tuve que reescribir
  algunas frases de "Nunca X" a positivo para no romper el test de ratio de
  negativos (`test_negative_rule_ratio_under_cap`, máx. 1:10 líneas). `prompts.py`
  (V4): agregado `framing` a la lista de "DISCIPLINA DE OUTPUT V4". `engine.py`:
  borrado `_wrap_verbatim_with_intro_outro`/`_WRAP_DEFAULT_INTRO`; nuevos
  `_apply_framing`/`_apply_framing_intro_only` (reutilizan `_wrap_text_is_safe`
  + cap de 220 chars), aplicados en Path 0a-appt (intro+outro), Path 0b-booked
  (solo intro) y Path 0b2 search/details (intro+outro); tail multi-intent sigue
  sin framing (mismo criterio que #43). `config.py`: `CONVERSATIONAL_WRAP_ENABLED`
  reemplazado por `RESPONSE_FRAMING_ENABLED` (default True, kill-switch).
  Tests: `test_conversational_wrap.py` borrado, `test_response_framing.py` nuevo
  (11 casos: byte-identidad, wrap, leak de precio/ID, flag off, atributo faltante).
  **Hardening post-review:** un subagente security-reviewer marcó MEDIUM que
  `_wrap_text_is_safe` (chequeo literal de "$"/"id:") no atrapaba leaks en
  lenguaje natural ("propiedad 7", "35.976 pesos"); endurecido a "cualquier
  dígito en el texto = inseguro" (framing es prosa pura, nunca necesita un
  dígito legítimamente) + 2 tests de regresión nuevos. `pytest tests/v3/ -q`:
  337 passed, 2 skipped, 3 xfailed (era 335 antes del hardening). Suite completa
  (`pytest -q` fuera de tests/v3/) tiene ~103 fallos preexistentes por estado de
  DB/migraciones del contenedor local (no relacionados a este plan — ver memoria
  docker-test-baseline); fuera de alcance, el criterio de aceptación del plan es
  `tests/v3/ -q` en verde, que se cumple. No se requirió verificación Chrome MCP/
  Playwright (gate 4 del loop): este plan no toca UI/dashboard, es lógica de
  backend del engine V3/V4 (WhatsApp).

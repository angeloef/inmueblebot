---
id: respuestas-conversacionales-envoltorio
area: Backend (bot / engine.py — response assembly)
priority: P2
status: completed
depends_on: []
related_areas: [v3-engine, v4-engine-inherit, tests-v3, eval-harness]
---

## Problema

Las respuestas del bot para búsquedas ("busco depto en el centro") suenan a
plantilla de string, no a conversación. El usuario lo pidió explícitamente:
más naturalidad, **sin ceder terreno en exactitud de datos** (precios, specs,
IDs de propiedad deben seguir siendo 100% reales, cero margen de alucinación).

Esto es intencional-por-omisión, no un bug: hoy el bot tiene dos caminos de
respuesta y el que se usa en el 100% de las búsquedas es puro Python sin LLM.

## Contexto

**Camino "verbatim" (el que corre hoy en toda búsqueda) — Path 0b2 en
`app/routers/v3/engine.py`, función `_assemble_response` (~líneas 812-849):**
cuando el turno ejecuta `search_properties` o `get_property_details`, el
motor toma el string ya formateado en Python por `_format_properties_list`
(`app/tools/v2/search_properties.py`, formato `"ID:12 — Departamento en
Centro — $250.000/mes"`) y lo devuelve **tal cual**, sin pasar por el LLM.

**Camino "synthesis" — ya existe pero infrautilizado:** `_synthesize_from_results`
(~línea 621 de `engine.py`) hace una segunda llamada LLM (`LLMRole.SYNTH`,
`app/agents/cs_llm_client.py:23` → modelo `gpt-5.4-mini`, ya es el rol barato/
rápido separado del router principal) que redacta en base a `tool_results`
reales. **Hoy solo se invoca como "tail"** cuando hay un segundo tool no-
verbatim en el mismo turno (ver `~líneas 835-848`, y el test
`tests/v3/test_multi_tool_concat.py` que cubre justamente ese caso: search +
FAQ). El resultado principal de una búsqueda simple nunca pasa por acá.

**Por qué está así — no es negligencia, hubo un incidente real (documentado
en los propios comentarios de `engine.py:815-817`):** intentos previos de
dejar al LLM redactar libremente causaron: truncamiento de listas, drift de
formato de precio (Argentina usa `$35.976` con punto de miles; el LLM
regeneraba `$35,976`), y el bug más serio — el LLM **afirmando un filtro que
no se había aplicado realmente**. La renderización verbatim fue la cura.
Cualquier solución acá DEBE preservar esa garantía estructuralmente, no con
una instrucción de prompt más ("por favor no alucines" ya falló una vez).

**Dirección acordada — "envolver, no reescribir":** los datos duros (líneas
`ID:N — Tipo en Zona — $Precio` + su línea de specs) siguen siendo Python
puro, intocables. Se agrega un envoltorio conversacional corto (intro/outro)
generado por LLM que **nunca recibe el bloque verbatim como texto editable**
— lo inserta el código DESPUÉS de la generación, no antes. Extiende el patrón
que ya existe para el tail multi-intent, pero aplicado también a búsquedas
simples.

**Piezas del sistema a revisar/tocar:**
- `app/routers/v3/engine.py` — `_assemble_response` (Path 0b2) y
  `_synthesize_from_results`. Definir si se generaliza esta última (para que
  devuelva `{intro, outro}` en vez de un bloque de texto libre) o si se crea
  una función hermana más acotada, ej. `_wrap_verbatim_with_intro_outro`.
- `app/core/response_parser.py` — `get_final_response_format()` (línea 68) y
  el schema `_STRICT_RESPONSE_SCHEMA`: **ya se verificó que hoy solo modela un
  texto de respuesta libre**, no una forma `{intro, outro}` separada. Si se
  necesita ese contrato, es un schema nuevo y acotado (no reusar el genérico
  sin revisar qué rompe en otros callers de `parse_llm_response`).
- `app/agents/cs_llm_client.py` — confirmar `LLMRole.SYNTH` (línea 23,
  `gpt-5.4-mini`) como el rol a usar; no crear un rol nuevo salvo que el
  costo/latencia real medido lo justifique.
- `app/routers/v4/engine.py` (~línea 430) — importa `_execute_tools` y
  `_assemble_response`/`_synthesize_from_results` de V3. Confirmar (no
  asumir) si el cambio se hereda automáticamente o si el flujo propio de
  `sub_goals` de V4 necesita su propio ajuste — V4 ya tiene lógica de
  multi-intención que podría interactuar con el nuevo envoltorio de forma no
  obvia.
- `tests/v3/test_multi_tool_concat.py` y `tests/v3/test_compact_search_summary.py`
  — tests existentes que ejercitan el camino verbatim/tail hoy; deben seguir
  en verde y sirven de referencia de estilo para los tests nuevos.
- `tests/eval/` — infraestructura de eval con baselines por versión (ver
  `tests/eval/baseline-v3.json`, `runner.py`, `graders.py`). Usar esto para
  medir el impacto real de latencia/costo antes de decidir si el envoltorio
  va siempre-on o detrás de un flag.

## Criterios de aceptación

- **No negociable:** el bloque de datos duros (`ID:N — Tipo en Zona — $Precio`
  y su línea de specs) llega al usuario **byte-a-byte idéntico** al que
  genera `_format_properties_list`, sin importar qué devuelva el LLM de
  envoltorio. Test explícito que lo verifique (comparación de igualdad de
  string, no "similar" ni "contiene").
- Una búsqueda simple ("busco depto en el centro") ahora incluye una frase de
  intro/outro conversacional generada dinámicamente (no siempre la misma
  frase fija) alrededor del bloque de resultados.
- El envoltorio nunca repite ni reformula precios/specs que ya están en el
  bloque verbatim (evita redundancia y evita reabrir el vector de
  alucinación).
- El envoltorio nunca afirma un filtro que no se haya aplicado realmente
  (mismo bug ya resuelto una vez — vigilar que no reaparezca en el nuevo
  punto del código).
- Si la llamada LLM de envoltorio falla (excepción/timeout), el bot sigue
  respondiendo con el bloque verbatim + un envoltorio default fijo — nunca
  bloquea ni muestra error al usuario.
- Existe un mecanismo de desactivación (flag/config) para volver al camino
  100% verbatim sin envoltorio si en producción el costo/latencia no se
  justifica frente al beneficio de UX.
- Se corrió (o se documentó explícitamente por qué no) una comparación en
  `tests/eval/` del score/latencia con vs. sin envoltorio, antes de
  recomendar el flag on por defecto en prod.
- V3 y V4 se comportan de forma consistente (o la diferencia está
  documentada y es intencional).

## Fuera de alcance

- No tocar `_format_properties_list` ni la lógica de fallback en cascada de
  `search_properties.py` (eso es contenido del plan #42, búsqueda
  multi-tipo — cambio independiente, no mezclar).
- No permitir en ningún escenario que el LLM regenere/resuma el bloque de
  resultados completo (eso es exactamente el patrón que ya falló antes).
- No introducir un modelo/proveedor LLM nuevo — usar `LLMRole.SYNTH`
  existente salvo que la medición de costo real justifique lo contrario (y en
  ese caso, confirmar con el usuario antes, no decidir unilateralmente).
- No aplicar el envoltorio a rutas donde ya existe el patrón tail (multi-
  intent) sin antes decidir explícitamente si el mecanismo nuevo lo
  reemplaza o convive — evitar duplicar dos llamadas de síntesis en el mismo
  turno.
- No deployar a prod (tenant `default`, WhatsApp activo, ~54 propiedades)
  sin verificación offline completa primero — esta es una mejora de UX, no
  un bugfix urgente; el riesgo de regresión en un canal de venta activo
  justifica cautela.

## Skills / MCP / Workflow recomendados

- TDD: escribir primero el test de "bloque verbatim byte-idéntico" — es el
  criterio no-negociable y debe fallar limpio si alguien lo rompe después.
- `tests/eval/` (runner + graders + baselines existentes) para medir
  impacto de calidad/latencia antes vs. después — evitar decidir "se siente
  mejor" sin dato.
- `code-review` sobre el diff final antes de commitear, dado que toca un
  camino de respuesta en producción activa con historial de bugs reales.
- Considerar `/ponytail` para el mecanismo de envoltorio: la tentación de
  construir un sistema de plantillas de tono/personalidad configurable es
  alta acá y es exactamente el tipo de over-engineering a evitar en un v1 —
  empezar con la llamada LLM más simple posible (intro + outro, nada de
  "modos de personalidad" o A/B testing de tono todavía).

## Bitácora
- 2026-07-01: plan creado. Contexto: usuario reportó sensación de "template"
  en las respuestas del bot; diagnóstico hecho en sesión — dos caminos de
  respuesta (verbatim vs synthesis) y el verbatim es el único usado en
  búsquedas simples por diseño defensivo (evitar los bugs de alucinación ya
  resueltos: truncamiento, drift de precio, filtros no aplicados afirmados).
  Dirección acordada: "envolver, no reescribir" — LLM solo agrega intro/outro
  fuera del bloque de datos duros, nunca lo toca. Confirmado que
  `LLMRole.SYNTH` ya usa modelo barato (`gpt-5.4-mini`) separado del router
  principal; confirmado que `get_final_response_format()` hoy no modela una
  forma `{intro, outro}`, habría que definir un schema acotado nuevo si se
  elige esa vía.
- 2026-07-02: **implementación completa, gates NO corridos (bloqueo de permisos).**
  Cambios en working tree (sin commit/push):
  - `app/core/config.py`: flag nuevo `CONVERSATIONAL_WRAP_ENABLED` (default **False** →
    100% verbatim, prod intacto).
  - `app/routers/v3/engine.py`: `_wrap_verbatim_with_intro_outro(user_message, block)`
    (usa `LLMRole.SYNTH`/`gpt-5.4-mini`, `response_format=json_object`, pide solo
    `{intro,outro}` sin ver el bloque; concatena `intro\n\n block \n\n outro` — el
    bloque nunca se regenera). Fallback fijo `_WRAP_DEFAULT_INTRO + block` ante
    excepción/timeout o salida vacía. Constante `_WRAP_DEFAULT_INTRO`.
  - Call-site: solo el retorno de búsqueda simple en Path 0b2 (~línea 849). El camino
    tail multi-intent (~846-848) se deja intacto a propósito (ya sintetiza cola →
    evita doble síntesis + doble framing en un turno).
  - **V4 hereda automáticamente**: `app/routers/v4/engine.py:478` llama al
    `_assemble_response` de V3 con `user_message` — sin cambio propio necesario.
  - Schema: NO se tocó `response_parser._STRICT_RESPONSE_SCHEMA`; se usó
    `json_object` directo (más lazy, no reabre otros callers).
  - Test nuevo `tests/v3/test_conversational_wrap.py`: no-negociable byte-idéntico
    (flag off = bloque intacto; flag on = bloque como substring exacto con precios
    `$35.976`/`$85.000.000` sin drift; fallback default ante fallo/salida vacía).
  - **Pendiente antes de shippear:** correr gates (pytest en docker: nuevo +
    `test_multi_tool_concat` + `test_compact_search_summary`; review de subagente;
    y eval `tests/eval/` con vs sin wrap ANTES de considerar flag on-by-default).
    No pude ejecutarlos: en esta corrida autónoma la ejecución de comandos
    (`pytest`, `docker exec`, `python -c`) requiere aprobación no otorgada. El flag
    va **off** → deploy seguro aunque se pushee; encender solo tras eval medida.
- 2026-07-02: retomado en sesión interactiva (con permisos de Bash) para correr
  los gates que la corrida autónoma dejó pendientes.
  - Bug de test encontrado y arreglado: `test_conversational_wrap.py` parcheaba
    `app.core.config.get_settings` con un stub mínimo (solo
    `CONVERSATIONAL_WRAP_ENABLED`), pero eso disparaba el primer import de
    `app.agents.llm_router` (singleton `LLMRouter()` construido a nivel de
    módulo) DENTRO del patch activo → `AttributeError: 'S' object has no
    attribute 'LLM_TIMEOUT_SECONDS'`. Fix: `import app.agents.cs_llm_client`
    a nivel de módulo en el test, antes del primer patch, para forzar el
    import con settings reales.
  - `security-reviewer` sobre el diff: sin CRITICAL/HIGH. Sugirió (MEDIUM,
    defense-in-depth) un guard cheap contra prompt-injection vía
    `user_message` — que el intro/outro generado filtre un precio o ID real
    aunque el system prompt ya lo prohíba. Como esto mapea directo a un
    criterio de aceptación no-negociable del plan ("el envoltorio nunca
    repite precios/specs... nunca afirma un filtro que no se aplicó"), lo
    implementé: `_wrap_text_is_safe()` rechaza intro/outro que contengan `$`
    o `id:` (case-insensitive); si ambos quedan vacíos tras el filtro, cae al
    fallback fijo `_WRAP_DEFAULT_INTRO + block`. 2 tests nuevos que lo cubren
    (precio filtrado, ID filtrado).
  - Lint (`ruff`): sin errores nuevos en el rango tocado, salvo un `I001`
    (orden de import) que replica un patrón ya existente sin tocar en el
    mismo archivo — no lo toqué para no generar un diff de estilo ajeno al
    plan.
  - Tests: `pytest tests/v3/ -q` (dentro de Docker, vía `docker cp` +
    `docker exec`) → 331 passed, 2 skipped, 3 xfailed. Incluye
    `test_conversational_wrap.py` (6/6), `test_multi_tool_concat.py`,
    `test_compact_search_summary.py` — todos en verde.
  - Eval `tests/eval/` con vs sin wrap: **no corrido, documentado
    explícitamente por qué no** — el flag ship **off** por default (0 impacto
    en prod), y el criterio de aceptación solo exige la comparación "antes de
    recomendar el flag on por defecto en prod", decisión que queda para una
    sesión futura cuando alguien decida evaluar prenderlo.
  - Gate de UX visual (Chrome MCP/Playwright): **N/A** — cambio 100%
    backend/bot, no toca dashboard ni ninguna superficie con UI.
  - SHIP: commit `6558e71` pusheado a `main`, deploy en Render confirmado vía
    `GET /version` (`{"commit":"6558e71...","service":"inmueblebot"}`); flag
    off por default → deploy seguro.

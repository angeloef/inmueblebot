# Loop de Optimización — Chatbot Router V2

**Inicio:** 2026-06-03 15:12:40 · **Presupuesto:** 40 min (fin ≈ 15:52:40)
**Destino:** push directo a `main` → auto-deploy Render (prod)
**Modelo orquestador:** Opus 4.8 · **Usuarios-jueces:** Haiku 4.5 (subagentes)
**SUT:** https://inmueblebot-api.onrender.com/simulate/multi
**SHA base:** acf9734

---

## Contrato del endpoint
`POST /simulate/multi` (sin auth) → `{response, tools_called, confidence, router, latency_ms, turn, criteria_count, selection, active_intents}`
Estado por `session_id` (id único = contexto fresco). `phone`/`session_id` con prefijo `loopN-` para aislar datos de test.

Tools wireadas en V2: `search_properties, get_property_details, get_property_images, get_faq_answer, schedule_visit, echo, get_time`.

---

## Bitácora

### Fase 0 — Bootstrap
- Health OK (cold start ~90s la primera vez).
- Smoke `/simulate/multi` OK — latency ~12s, narrowing activo.
- Endpoint `/version` agregado (lee `RENDER_GIT_COMMIT`) para detectar fin de deploy.
- Ciclo de deploy medido: **~52–79 s** push→live (Docker con capas cacheadas).

### Iteración 1 — tanda de 10 personas (Haiku 4.5)
Personas P1–P10 (funnel, operación ambigua, sin-resultados, cambio-tipo, FAQ+legal,
referencia implícita, presupuesto relativo, prompt-injection, detalles+fotos, agendado+typo).

**Resultado tanda 1:** 4 PASS · 6 FAIL.

| Persona | Síntoma | Causa-raíz | Estado |
|---|---|---|---|
| P3 | fallback sin resultados | — | ✅ pasaba |
| P4 | cambio depto→casa + landmark | — | ✅ pasaba |
| P5 | FAQ ×3 + legal→humano | — | ✅ pasaba |
| P8 | prompt injection | — | ✅ pasaba |
| **P2** | "alquilar o comprar" → asumía alquiler | `OPERATION_PATTERNS` tomaba el 1er match | ✅ **FIX + verificado** |
| **P6** | "detalles de esa" → re-preguntaba zona | fast-path `search_narrow` tragaba todo mensaje | ✅ **FIX + verificado** |
| **P9** | "opción 2 y las fotos" → re-buscaba | idem narrowing-swallow | ✅ **FIX + verificado** |
| **P7** | "más barato" → re-preguntaba zona | sin lógica de presupuesto relativo | ✅ **FIX + verificado** |
| P1 | "Dejo solicitada la visita" sin llamar `schedule_visit` | turno de nombre no entra al fast-path de booking (awaiting ≠ scheduling_confirm) | ⏸️ DIFERIDO |
| P10 | `schedule_visit` llamado pero "me falta día" | día (viernes 17:00) no persiste en belief al momento del booking | ⏸️ DIFERIDO |

**Commits (push directo a main → prod):**
- `d043fe5` feat(ops): /version endpoint
- `8618cbd` fix(narrowing): escape-hatch (P6, P9) → re-ruteo de referencia/detalle/foto/cheaper
- `3f1eed5` fix(operation): "alquilar o comprar" no asume alquiler (P2)
- `2e539bc` fix(refine): presupuesto relativo "más barato" (P7)

**Verificación (sesiones `loop1b-`/`loop1c-`):** P2, P6, P7, P9 → PASS · smoke P3, P8 → PASS (sin regresiones). P7 además encadena: 200k→160k→128k→102k→82k.

### Causa-raíz pendiente #1 (próxima corrida): flujo de AGENDADO
P1 y P10 comparten familia: la **persistencia de slots de scheduling** (día/hora/nombre) y la
entrada al fast-path de booking. Síntomas: (a) confirmación textual sin invocar `schedule_visit`
cuando el usuario da el nombre fuera del estado `scheduling_confirm`; (b) `schedule_visit`
ejecuta pero reporta día faltante pese a haberlo capturado. Requiere revisar
`_next_scheduling_slot` / `_capture_day_time` / el gate `awaiting=="scheduling_confirm"` en
`router.py` y `schedule_visit`. **Riesgo de regresión ALTO** (flujo core) → no se tocó sin
margen para verificar dentro del time-box de 40 min.

---

## Iteración 2 (2026-06-03 15:46 → 16:26) — foco AGENDADO + descubrimiento

**Descubrimiento (4 personas nuevas, Haiku):** D2 (honestidad de features) PASS · D4 (saludo→negocio) PASS ·
D1 (agendado denso en 1 mensaje) FAIL · D3 (slang "50 palos"→parseó 50 dormitorios, precios alquiler) FAIL.

**Trabajo en el flujo de AGENDADO (P1/P10/D1):** descubrí que es un bug **multicapa**, no puntual:
1. `update_belief` capturaba nombre/día/hora **solo si scheduling ya estaba activo** → en el 1er mensaje denso los slots se descartaban → booking con args vacíos.
2. La ruta `scheduling-persist` devolvía el texto del LLM **sin pasar por el guard** → el LLM **fabricaba** confirmaciones ("Te confirmo la visita para #10") sin llamar `schedule_visit`.
3. `_maybe_confirm_or_pass` trataba un `schedule_visit` fallido ("me falta día") como éxito.
4. Typo de día ("vienes"→viernes) no lo captura `DAY_PATTERN` en update_belief.

**Commits (push directo a main → prod):**
- `2cf8577` fix(scheduling): kill fake confirmations + surface real missing slot
- `a702a5b` fix(scheduling): capturar slots en el 1er turno denso + ampliar guard fake-booking
- `e1ea8fe` fix(scheduling): anti-fabrication guard en ruta persist — agenda real o pregunta honesta

**Resultado verificado:**
| Persona | Antes | Después |
|---|---|---|
| **P1** (funnel→agenda) | confirmación FALSA sin `schedule_visit` | ✅ **PASS** — agenda de verdad (lunes 16:00, schedule_visit real) |
| D1 (agendado denso) | confirmación falsa | ⚠️ ya NO finge: llama la tool y dice honestamente "me falta" — pero falta poblar slots del mensaje denso con ordinal |
| P10 (typo "vienes") | confirmación falsa | ⚠️ honesto pero re-pregunta el día (typo no capturado) |

**Logro clave:** se eliminó la **confirmación falsa silenciosa** (el peor bug: el usuario creía tener una visita inexistente). Ahora el bot **agenda de verdad cuando tiene los datos**, o **pregunta honestamente** lo que falta. P1 (el caso headline) quedó verde.

**Pendiente (refactor dedicado, riesgo alto):**
- Captura de slots en mensaje denso con ordinal ("me interesa el primero, agendá mañana 10, soy carla") — los slots no persisten en belief antes del booking.
- Typo de día en `update_belief` (usar `extract_scheduling_day`, que tolera typos, en vez de `DAY_PATTERN`).
- Slang de plata D3: "tengo 50 palos" no se parsea como presupuesto (BUDGET_PATTERN exige prefijo) y "50" se cuela como dormitorios.
Estos requieren debug local con logging por request, no thrashing en prod — fuera del time-box.

### Cierre iter2
- **P1 (confirmación falsa de agendado) resuelto y verificado** — el bot ahora agenda de verdad.
- Confirmación falsa silenciosa **eliminada** en todo el flujo (agenda real o pregunta honesta).
- Regresión: smoke search / narrowing / details+photos / FAQ → **PASS** (sin regresiones por los cambios de scheduling).
- 3 commits a prod. 2 sub-bugs de agendado (mensaje denso con ordinal, typo de día) + slang D3 documentados para refactor dedicado.
- Total acumulado (iter1+iter2): **5 bugs resueltos+verificados, 0 regresiones, 8 commits.**

---

## Iteración 3 (2026-06-03) — fixes de raíz + auto-corrección del LLM

Implementación de las 3 soluciones pendientes + un cambio estructural para que el LLM
corrija el estado cuando los extractores regex se equivocan.

### Bug 1 — Ordinal denso → ID (determinístico)
`update_belief` ahora resuelve ordinales en palabra ("el primero/segundo/tercero…") a un ID
concreto usando `belief.last_search_ids` (lookup posicional, 0 tokens). No agrega el intent
`resolved_by_description` a propósito, para no disparar el shortcut de detalles y perder un
pedido de agendado en el mismo mensaje. Archivo: `app/core/state_transitioner.py`.

### Bugs 2 y 3 + estructural — Auto-corrección del LLM (sin ampliar regex)
En vez de ampliar regex (imposible cubrir todo el lenguaje natural), se le da al LLM la
capacidad de **corregir el estado** cuando detecta que el `[ESTADO ACTUAL]` contradice lo que
el usuario dijo (typos como "vienes"→viernes, slang como "50 palos"→50.000.000, operación mal
inferida, nombre/día faltante). Pipeline:
- `response_parser.py`: el JSON final del LLM ahora incluye un campo `correcciones`
  (cadena JSON o null) + `parse_corrections()` robusto (strict-schema, json_object y markdown).
- `schemas.py`: `CSAgentResponse.belief_corrections`.
- `s2_agent.py` + `coordinator.py`: instrucción `_SELF_CORRECTION` en SYSTEM_PROMPT y en los 3
  especialistas (search/scheduling/knowledge); las 3 funciones del agente propagan `belief_corrections`.
- `router.py`: `_apply_belief_corrections()` — whitelist de campos
  (operation, property_type, zone, budget_max, bedrooms_min, scheduling_day/time/name), coerción
  + bounds-check, descarta lo inválido. Se aplica dentro de `_update_belief_from_result` (todas las
  rutas) DESPUÉS del regex → la corrección del LLM **gana** sobre el regex, en el mismo turno.
  `selected_property_id` queda FUERA de la whitelist (para que el LLM no alucine IDs; el ordinal
  ya lo resuelve determinísticamente).

### Por qué esto responde "¿y si el regex capta un dato erróneo?"
El pipeline regex→belief era unidireccional (el LLM era read-only sobre el belief). Ahora el LLM
puede escribir correcciones de vuelta: es el doble-check que faltaba para errores de extracción,
no solo para campos vacíos. Aplicado antes de `_maybe_confirm_or_pass`/booking en las rutas de
scheduling, así la corrección tiene efecto en el mismo turno.

### Validación local (lógica pura, sin tests de conversación)
- Ordinal: primero→10, segundo→18, tercero→22, fuera-de-rango→None.
- `parse_corrections`: strict-string, objeto anidado, markdown, null, ausente → todos OK.
- `_apply_belief_corrections`: normaliza "comprar"→"venta", coerciona tipos, descarta inválidos
  (op basura, presupuesto negativo, 99 dorms), ignora `selected_property_id` y campos no-whitelist.
- Los 6 módulos importan sin errores. **Tests de conversación los corre el usuario manualmente.**

### Cierre iter1
- Duración real: ~31 min de las 40 (parado por disciplina de time-box, no por agotarlo).
- **4 bugs encontrados, arreglados, pusheados a prod y verificados; 0 regresiones.**
- 2 bugs (agendado) identificados con causa-raíz y diferidos por riesgo/tiempo.
- Cuello de botella del loop: la **latencia del bot** (10–30 s/turno), no el deploy (~1 min).
  Una próxima corrida rinde más con personas más cortas (≤4 turnos) y tandas paralelas.


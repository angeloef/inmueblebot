# Plan de Fixes — Stress Test InmuebleBot

> Generado a partir del stress test de 10 escenarios (39/59 turnos OK, 1/10 escenarios limpios).
> Decisiones de diseño confirmadas con el equipo:
> - **Agendamiento**: mantener el diseño `recolectar → confirmar → reservar automáticamente`. Arreglar las assertions mal escritas del test **y** los bugs reales que traban el flujo.
> - **Out-of-scope**: reforzar con un **guard a nivel LLM** en los prompts de los especialistas (no solo blocklist de keywords).
> - **Interrupción de agenda**: **atender y mantener pendiente** — responder el tema nuevo, recordar el agendamiento y ofrecer retomarlo. Abandonar solo si el usuario lo descarta explícitamente.
> - **compare_properties**: **eliminar** por completo.

---

## Contexto arquitectónico (lo que descubrimos)

El path de producción real es `app/routers/router.py` (vía `/simulate`). Aclaraciones clave que invalidan varias assertions del test:

1. El agendamiento **no usa** `schedule_visit` como tool call del LLM. El router recolecta `nombre → día → hora` y reserva **directamente** en el paso de confirmación ([router.py:737](app/routers/router.py:737), [router.py:881](app/routers/router.py:881)). Por eso varias "fallas" de S2/S4/S10 que esperaban `schedule_visit` son **falsos negativos del test**.
2. Los tools reales de citas son `cancel_appointment` y `reschedule_appointment` (sin sufijo `_tool`). Las assertions usaban `cancel_appointment_tool` / `reschedule_appointment_tool` → **falsos negativos**.
3. El out-of-scope es un blocklist de keywords ([router.py:90](app/routers/router.py:90)) que no atrapa casos nuevos (cálculos, redacción de mails).
4. Ya existe un escape parcial de agenda (`_HARD_TOPIC_SWITCH` [router.py:123](app/routers/router.py:123)) y un handler de interrupción ([router.py:776](app/routers/router.py:776)), pero son incompletos.
5. La persistencia de especialista (`saved.active_specialist == "scheduling"`, [router.py:865](app/routers/router.py:865)) re-enruta a agenda **cualquier** mensaje sin keyword de topic-switch → causa entradas espurias a scheduling.

---

## FASE 1 — Bugs críticos

### FIX 1 — Prioridad de escalación a humano (C3)
**Síntoma:** S7-T4. "todo caro, no sirve nada, quiero hablar con una persona real ya" → enrutado a `negotiator` (ganó el keyword "caro"), que no tiene `request_human_assistance`. El handoff quedó solo en texto, sin tool call → el CRM nunca se entera.

**Causa:** No hay prioridad para el pedido de humano. El routing por keywords deja que "caro" gane sobre "persona real".

**Cambios:**
- Agregar un regex `_HUMAN_REQUEST` en `router.py` (junto a `_EMERGENCY` [router.py:114](app/routers/router.py:114)): `hablar con (una )?persona|agente|asesor|humano|persona real|alguien real|operador|representante`.
- Insertar un check **antes** del routing por especialista (y antes de la persistencia de scheduling): si matchea → llamar `request_human_assistance` directamente y devolver el handoff, limpiando `awaiting`.
- Reusar el patrón ya existente de handoff determinístico ([router.py:607-616](app/routers/router.py:607)).

**Validación:** S7-T4 debe devolver `tools_called: ["request_human_assistance"]`.

---

### FIX 2 — Guard de out-of-scope a nivel LLM (C2)
**Síntoma:** S3-T4 (calculó "15% de 2 millones = $300.000") y S3-T6 (redactó un mail completo al dueño). El blocklist no los atrapó y cayeron al LLM, que los resolvió.

**Causa:** Los prompts de los especialistas (`knowledge`, `negotiator`, `search`) no tienen una sección de scope que instruya rechazar tareas fuera de dominio.

**Cambios:**
- En `app/agents/coordinator.py`, agregar a los `system_prompt` de `knowledge`, `negotiator` y `search` una sección **ALCANCE** con instrucción explícita + ejemplos negativos:
  - Cálculos matemáticos generales (porcentajes, sumas que no sean precios de propiedades listadas).
  - Redacción de mails, cartas, mensajes a terceros.
  - Traducciones, tareas escolares, consejos legales/fiscales/de salud, código.
  - Respuesta estándar de redirección (reusar el texto de `_OUT_OF_SCOPE_RESPONSE`).
- Mantener el blocklist de keywords como primera barrera barata (no se toca).
- **Sin costo de latencia extra**: la instrucción viaja en el mismo call del especialista.

**Validación:** S3-T4 y S3-T6 no deben calcular ni redactar; deben redirigir al negocio.

---

### FIX 3 — Interrupción de agenda: atender y mantener pendiente (C1)
**Síntoma:** Una vez en `awaiting=scheduling_*`, el bot ignora topic jumps y pedidos alternativos:
- S2-T4 "¿tiene garaje?" → "¿a nombre de quién?"
- S1-T3 "¿tienen terrenos en venta?" → "Dale, lo vemos después. ¿Qué día?"
- S1-T6 "la primera, ¿tiene fotos?" → "¿Qué día querés verla?"

**Causa:** El handler B3 ([router.py:776](app/routers/router.py:776)) manda **todas** las preguntas al especialista `knowledge` y siempre agrega "¿Querés continuar con el agendamiento?". No distingue si el usuario quiere fotos, detalles o una nueva búsqueda.

**Cambios (comportamiento "atender y mantener pendiente"):**
- En el handler de interrupción de agenda, **clasificar la intención** del mensaje en vez de hardcodear `knowledge`:
  - Pedido de **fotos** → `get_property_images` (reusar shortcut de fotos).
  - Pedido de **detalles** → `get_property_details`.
  - **Pregunta de FAQ/conocimiento** → `knowledge` (comportamiento actual).
  - **Nueva búsqueda** ("terrenos", "casas", criterios nuevos) → especialista `search`.
- Tras atender, **mantener `belief.awaiting` intacto** y agregar el recordatorio de retomar ("…¿seguimos con la visita?") — solo cuando el agendamiento sigue siendo relevante.
- Ampliar `_HARD_TOPIC_SWITCH` para incluir `terrenos|lotes|ph` y formas de pregunta de nueva búsqueda, de modo que un cambio fuerte abandone la agenda (ya cubierto por el flujo de descarte explícito).

**Validación:** S2-T4 responde sobre garaje y ofrece retomar; S1-T3 busca terrenos; S1-T6 muestra fotos.

---

### FIX 4 — Entrada espuria a scheduling tras una búsqueda (raíz de S1-T2, S6-T2)
**Síntoma:** Tras una búsqueda, agregar criterios de refinamiento dispara "¿Qué día querés coordinar la visita?":
- S1-T2 "2 ambientes, zona centro, no sé el presupuesto" → pregunta de agenda.
- S6-T2 "en oberá, 2 ambientes, hasta 70 mil" → pregunta de agenda.

**Causa (a confirmar con instrumentación):** Sospechosos:
1. Persistencia `saved.active_specialist == "scheduling"` ([router.py:865](app/routers/router.py:865)) con `topic_switch_kw` demasiado débil.
2. `_detect_awaiting` ([router.py:178](app/routers/router.py:178)) marcando `scheduling_*` desde el texto del bot por falso positivo.
3. Misclasificación del coordinator LLM ante mensajes de solo-criterios.

**Cambios:**
- **Paso 0 (diagnóstico):** agregar logging temporal del `router_label` + `awaiting` + `active_specialist` por turno para reproducir y confirmar cuál de los 3 dispara.
- **Detección de refinamiento (fix principal):** si existe `belief.last_search_ids` y el mensaje entrante contiene criterios de búsqueda (presupuesto / ambientes / zona / tipo) **sin** señales de scheduling (día/hora/nombre/"agendar/visita") → tratar como **refinamiento** y re-ejecutar `search_properties` con criterios combinados. Nunca scheduling.
- Endurecer `_detect_awaiting` para que no infiera `scheduling_*` salvo que el scheduling esté realmente activo (`active_intents` o `awaiting` ya en scheduling).

**Validación:** S1-T2 y S6-T2 deben llamar `search_properties` (o responder desde contexto), nunca preguntar por la visita.

---

## FASE 2 — Bugs moderados y limpieza

### FIX 5 — Refinamiento de búsqueda con criterios cambiantes (M1)
**Síntoma:** S5-T2 "tengo 20 millones, zona sur" tras ver 7 casas → "¿Alquilar o comprar?" (perdió contexto, `conf:0.00` = fallback de error).

**Causa:** Mismo mecanismo que FIX 4 — criterios de refinamiento no reconocidos como continuación de la búsqueda activa.

**Cambios:** Cubierto en gran parte por la "detección de refinamiento" de FIX 4. Adicional:
- Investigar el `conf:0.00` (path de error/fallback) — probablemente excepción silenciada en el coordinator. Loguear y corregir.
- Asegurar que el belief combine criterios previos + nuevos antes de re-buscar.

**Validación:** S5-T2 re-busca con presupuesto 20M en zona flexible.

---

### FIX 6 — Multi-intent: fotos + agenda en un mensaje (M3)
**Síntoma:** S4-T2 "quiero ver las fotos y también agendarme una visita" → fue directo a agenda, nunca llamó `get_property_images`.

**Causa:** No hay manejo de doble intent; gana scheduling.

**Cambios:**
- En el shortcut pre-LLM (o al inicio del routing), detectar co-ocurrencia de intent de fotos + intent de agenda sobre una propiedad activa.
- Ejecutar `get_property_images` **primero**, luego entrar al flujo de agenda (preguntar día) en el mismo turno o en una respuesta secuencial.

**Validación:** S4-T2 debe incluir `get_property_images` y avanzar a agenda.

---

### FIX 7 — Eliminar `compare_properties`
**Alcance:** ~20 archivos. El tool **no** está en los especialistas activos de `coordinator.py`, así que es limpieza del path legacy + docs.

**Cambios (código):**
- `app/agents/tools.py` — eliminar la función `compare_properties` ([tools.py:1755](app/agents/tools.py:1755)) y su registro en `execute_tool`.
- `app/agents/real_estate_agent.py`, `app/agents/prompts.py`, `app/agents/planner.py` — quitar referencias y definiciones de tool.
- `app/core/state_machine.py`, `app/core/belief_state.py` — quitar estado/intents de comparación (`comparing`).
- `app/skills/mcp_server.py`, `app/skills/composer.py` — quitar el skill/registro.
- `app/core/state_transitioner.py` — quitar el patrón `comparing` de `INTENT_PATTERNS` ([state_transitioner.py:155](app/core/state_transitioner.py:155)).

**Cambios (tests):**
- `tests/stress_test.py` — eliminar la assertion de `compare_properties` en S5-T6 y rediseñar S10 sin el turno de comparación (reemplazar por detalles/fotos secuenciales).

**Cambios (docs, baja prioridad):** actualizar menciones en `BOT_DOCUMENTATION.md`, `AGENTS.md`, etc.

---

## FASE 3 — Bugs menores y corrección de tests

### FIX 8 — Formato telegráfico (m1)
**Síntoma:** S7-T3 "depto, alquiler, 2 ambientes, oberá, no me preguntes más" → no reconocido como criterios.
**Nota:** Los extractores de `state_transitioner.py` ya capturan tipo/operación/ambientes/zona. El problema es de routing/clasificación. **Debería resolverse con FIX 4** (criterios → search). Verificar tras FIX 4; si persiste, agregar few-shot de formato telegráfico al clasificador.

### FIX 9 — "quiero esa" → fotos vs detalles (m2)
**Síntoma:** S9-T6 "quiero esa" (tras "la más barata") → `get_property_details` en vez de `get_property_images`.
**Cambios:** Baja prioridad. Sesgar la resolución anafórica de "quiero esa" hacia la última acción en contexto. Evaluar si vale la pena vs. ambigüedad inherente.

### FIX 10 — Corrección de assertions del stress test
**Síntoma:** Falsos negativos por nombres de tools y labels de router que no existen.
**Cambios en `tests/stress_test.py`:**
- `cancel_appointment_tool` → `cancel_appointment`; `reschedule_appointment_tool` → `reschedule_appointment`.
- Reemplazar la expectativa de `schedule_visit` por validación del flujo real: estados `awaiting::*`, paso de confirmación y `tools_called: ["schedule_visit"]` **solo** en el turno de confirmación final.
- Eliminar assertions de `expect_router="s1"` (no es un label real; los reales son `rapport`, `search`, `knowledge`, `scheduling`, `negotiator`, `out-of-scope`, `awaiting::*`, `pre-llm::*`).
- Agregar turnos de regresión específicos: escape de agenda (FIX 3), refinamiento (FIX 4/5), prioridad de handoff (FIX 1), out-of-scope nuevo (FIX 2).

---

## Orden de ejecución sugerido

1. **FIX 10** primero (corregir tests) — para tener un baseline honesto y medir progreso real.
2. **FIX 1** (handoff) — bajo riesgo, alto impacto, aislado.
3. **FIX 2** (out-of-scope LLM) — solo cambios de prompt, aislado.
4. **FIX 4 + FIX 5** (entrada espuria + refinamiento) — comparten causa raíz; requieren instrumentación previa.
5. **FIX 3** (interrupción de agenda) — el más delicado; tocar después de estabilizar el routing.
6. **FIX 6** (multi-intent) — feature incremental.
7. **FIX 7** (eliminar compare_properties) — limpieza, sin dependencias.
8. **FIX 8 / FIX 9** — verificar/pulir al final.

## Estrategia de verificación

Tras cada fase, re-correr el stress test concurrente con Haiku (5 grupos en paralelo) y sintetizar con Sonnet, igual que en esta corrida. Meta incremental:
- Tras Fase 1: escenarios críticos (S1, S2, S3, S7) en verde.
- Tras Fase 2: ≥ 8/10 escenarios limpios.
- Tras Fase 3: 10/10 con assertions corregidas.

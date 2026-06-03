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

### Cierre
- Duración real: ~31 min de las 40 (parado por disciplina de time-box, no por agotarlo).
- **4 bugs encontrados, arreglados, pusheados a prod y verificados; 0 regresiones.**
- 2 bugs (agendado) identificados con causa-raíz y diferidos por riesgo/tiempo.
- Cuello de botella del loop: la **latencia del bot** (10–30 s/turno), no el deploy (~1 min).
  Una próxima corrida rinde más con personas más cortas (≤4 turnos) y tandas paralelas.


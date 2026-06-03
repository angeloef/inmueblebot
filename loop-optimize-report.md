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


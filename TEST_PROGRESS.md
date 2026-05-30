# TEST_PROGRESS — Goal autónomo: dejar el bot pasando los hard-test conversations

Ancla de resumibilidad. Si la sesión se corta (límite de uso), la próxima sesión **lee este
archivo y sigue desde acá** sin perder contexto.

## Goal
Ejecutar `angelo-hard-test-conversations-150.md` contra el bot deployado, encontrar bugs,
tweakear, pushear a Render y re-testear hasta que pasen. Verificar con: `/simulate/multi`
(comportamiento) + logs Render API + `/admin/*` (DB).

## Capacidades verificadas (toolkit)
- `POST https://inmueblebot-api.onrender.com/simulate/multi` — bot (tools_called, response, belief). Sin auth.
- Render API key (logs + deploy status): service `srv-d7sj5vd0lvsc73co5p6g`, owner `tea-d7shqjegkk3c73e528p0`.
- Admin API: `x-api-key: your-secure-admin-key-here` (⚠️ es el placeholder por defecto — ROTAR al terminar).
- Push directo a `main` → Render auto-deploya. Poll deploy: `GET /v1/services/{srv}/deploys?limit=1`.

## Alcance
- **A (en curso):** dejar perfectos C1, C5, C6, C8, C10 (search/details/fotos/faq/agendar + traps).
- **B (pendiente):** wirear 8 tools faltantes en V2 (reschedule/cancel/get_my_appointments/compare/recommend/refine/preferences/save_lead/handoff) para C2/C3/C4/C7/C9.

## Reglas de aceptación clave
- "lunes a las 11" → guarda **próximo lunes 11:00 ART** (= 14:00 UTC). (hoy 2026-05-30 sáb → lunes = 2026-06-01)
- Agendar crea **una sola** cita + un solo lead (sin duplicados), ligado a la identidad de sesión.
- Domingo / fuera de 9-18 → rechazo + repregunta (no agenda).
- Nunca "confirmación" de cita sin que `tools_called` incluya `schedule_visit`.

## Scoreboard (V1, escenarios ejecutables)
| Escenario | Estado | Nota |
|-----------|--------|------|
| C1 agendar (núcleo) | 🟢 | `e907773` → schedule_visit se llama; "lunes 11" → 2026-06-01 11:00 ART verificado en DB (cita user 3397c49f) |
| C1 rechazo horario | ⬜ pend | falta probar domingo / fuera-de-hora |
| C5 fallbacks      | ⬜ pend | |
| C6 cambio tipo    | ⬜ pend | |
| C8 trampas agendado | ⬜ pend | |
| C10 reprog+agendar | ⬜ pend | |

## Bugs encontrados / fixes
1. **bsuid column missing** (migración con backfill `extra_data ? 'bsuid'` rollbackeaba la tx) → removido backfill. ✅ commit previo.
2. **context_aggregator exigía teléfono** → blockers = día+horario. ✅ commit previo.
3. **scheduling specialist (coordinator.py) exigía teléfono** (reglas 8/9) → `schedule_visit` nunca se llamaba. ✅ `e907773` (deploying).
   - Pendiente verificar: re-test con flujo confirm.
   - Sospecha latente: **name loop** — el especialista NO recibe el historial de conversación; depende del belief (regex) que no extrae nombres "pelados" ("leandro gomez") → puede re-pedir el nombre. Si el re-test lo muestra, fix = pasar historial al especialista o mejorar extracción.

## Próximo paso
Esperar deploy `e907773` live → re-test scheduling con confirm → verificar cita en `/admin/appointments` (fecha correcta, 1 sola). Luego barrer C1/C5/C6/C8/C10 de V1.

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

## Scoreboard (V1, escenarios ejecutables) — TODOS VERDES (deploy ea3ab6d)
| Escenario | Estado | Nota |
|-----------|--------|------|
| C1 agendar + rechazo | 🟢 | domingo/21:00 rechaza; "lunes"+"a las 3 de la tarde" → DB 2026-06-01 15:00 ART ✅ |
| C5 fallbacks      | 🟢 | degrada con gracia |
| C6 cambio tipo    | 🟢 | type-switch arreglado (busca casas); menor: "primera casa" no filtra por tipo |
| C8 trampas        | 🟢 | ordinal "segunda" ✅; "dentro de 3 dias a las 5" → DB 2026-06-02 17:00 ART ✅ |
| C10 ordinal+sábado | 🟢 | "el ultimo"→prop 5 ✅; "el sabado a las 11" → DB 2026-06-06 11:00 ART (roll-forward) ✅ |

## Bugs encontrados / fixes (todos pusheados)
1. **bsuid column missing** (backfill rollbackeaba la tx) → removido. ✅
2. **context_aggregator exigía teléfono** → blockers día+horario. ✅
3. **scheduling specialist (coordinator.py) exigía teléfono** (reglas 8/9) → tool nunca se llamaba. ✅ `e907773`
4. **scheduling multi-turno** (día y hora en turnos distintos no se combinaban) → **booking determinístico** en persist block usando belief (router.py) + **TIME_PATTERN** rico ("a las 3 de la tarde") + DAY_PATTERN "dentro de N dias". ✅ `a813b9f`
5. **ordinal "el ultimo"** no resuelto + **faq_zonas** capturaba búsquedas → ✅ `5afe41d` (verificando)

## Pendiente / próximos pasos
- Confirmar C6/C10 verde (deploy `5afe41d`).
- Barrer V2–V15 de los escenarios ejecutables (variation-specific bugs).
- **Scope B (grande):** wirear 8 tools faltantes en V2 para C2/C3/C4/C7/C9 (reschedule/cancel/get_my_appointments/compare/recommend/refine/preferences/save_lead/handoff). Hoy degradan (no crashean) pero no completan.
- Limpieza: borrar citas/leads de test; **rotar ADMIN_API_KEY** (es el placeholder) y los secrets pegados en chat.

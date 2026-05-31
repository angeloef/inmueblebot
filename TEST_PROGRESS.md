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

## 🔴 BLOQUEADOR ACTUAL: OpenAI quota exhausted
El bot usa `openai.RateLimitError: insufficient_quota`. Todas las llamadas LLM fallan con 500.
**Para continuar**: el usuario necesita recargar créditos OpenAI o agregar una nueva API key en Render env vars.
Deploy actual: `672107e` (listo en Render, pero inutilizable hasta que se restablezca el quota).

## Alcance
- **A (completado):** C1, C5, C6, C8, C10 — todos verdes en deploy ea3ab6d.
- **B (completado):** wirear get_my_appointments, cancel_appointment, reschedule_appointment, request_human_assistance → C2 y C7 funcionan.
- **C (pendiente):** compare_properties, recommend_properties, refine_search, get_user_preferences, update_user_preferences, save_lead_info (para C3/C4/C9).

## Reglas de aceptación clave
- "lunes a las 11" → guarda **próximo lunes 11:00 ART** (= 14:00 UTC). (hoy 2026-05-30 sáb → lunes = 2026-06-01)
- Agendar crea **una sola** cita + un solo lead (sin duplicados), ligado a la identidad de sesión.
- Domingo / fuera de 9-18 → rechazo + repregunta (no agenda).
- Nunca "confirmación" de cita sin que `tools_called` incluya `schedule_visit`.

## Scoreboard

### V1 (deploy ea3ab6d) — TODOS VERDES
| Escenario | Estado | Nota |
|-----------|--------|------|
| C1 agendar + rechazo | 🟢 | domingo/21:00 rechaza; "lunes"+"a las 3 de la tarde" → DB 2026-06-01 15:00 ART ✅ |
| C5 fallbacks      | 🟢 | degrada con gracia |
| C6 cambio tipo    | 🟢 | type-switch arreglado (busca casas); menor: "primera casa" no filtra por tipo |
| C8 trampas        | 🟢 | ordinal "segunda" ✅; "dentro de 3 dias a las 5" → DB 2026-06-02 17:00 ART ✅ |
| C10 ordinal+sábado | 🟢 | "el ultimo"→prop 5 ✅; "el sabado a las 11" → DB 2026-06-06 11:00 ART (roll-forward) ✅ |

### Scope B (deploy 10944fc/672107e) — Verificado antes de que se agotara quota
| Escenario | Estado | Nota |
|-----------|--------|------|
| C2 ciclo cita     | 🟢 | T2 agenda✅ T3 get_my_appointments✅ T4 reschedule✅ T5 cancel✅ |
| C7 handoff        | 🟡 | T1 request_human_assistance✅; T2 regresa a s1 FAQ (aceptable) |

### Pendiente (necesita quota OpenAI)
| Escenario | Estado | Nota |
|-----------|--------|------|
| C1 (re-verificar) | ⏸ | Necesita quota. Última vez verde en ea3ab6d. |
| C5/C6/C8/C10 (re-verificar) | ⏸ | Idem. |
| C3/C4/C9 | ⏸ | Scope C tools no implementados. |

## Bugs encontrados y fixes (todos pusheados a main)
1. **bsuid column missing** (backfill rollbackeaba la tx) → removido. ✅
2. **context_aggregator exigía teléfono** → blockers día+horario. ✅
3. **scheduling specialist requería teléfono** (reglas 8/9) → tool nunca se llamaba. ✅
4. **scheduling multi-turno** → booking determinístico en persist block + TIME_PATTERN rico. ✅
5. **ordinal "el ultimo" + faq_zonas** → resuelto. ✅
6. **get_my_appointments / cancel / reschedule** → wired + coordinator rules 11-13. ✅ `3328003`
7. **miercoles (sin acento) no matcheaba scheduling** → INTENT_PATTERNS fix `mi[eé]rcoles`. ✅
8. **T3 "me confirmas" → llamaba schedule_visit** → clear scheduling state after success + `agendad[ao]` pattern. ✅
9. **T4 "pasala para el jueves" → schedule_visit en vez de reschedule** → scheduling specialist prompt con ejemplos argentinos. ✅
10. **S1→search con "lo quiero ver el sábado"** → secondary check visit+day → scheduling specialist. ✅
11. **"11 de la mañana" (sin "a las") → hora None** → `_parse_time`/`_parse_time_advanced`/`_extract_time_from_text` fix. ✅
12. **date_parser LLM devolvía domingo en vez de sábado** → hybrid/date.py default_strategy="code". ✅
13. **fmt_appt mostraba hora UTC (13:00) en vez de ART (10:00)** → _common.py _to_arg() timezone conversion. ✅
14. **request_human_assistance** → tool + registry + coordinator rapport specialist. ✅

## Próximos pasos (cuando se restablezca el quota OpenAI)
1. Re-correr suite completa: C2, C1, C5, C6, C8, C10, C7
2. Si hay regresiones, fixear
3. Implementar Scope C tools: compare_properties, recommend_properties, refine_search, get_user_preferences, save_lead_info
4. Añadir escenarios C3/C4/C9 a convtest.py
5. Limpieza: **rotar ADMIN_API_KEY** (es el placeholder) y los secrets pegados en chat.

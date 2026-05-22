# PLAN: Modular Prompt Architecture — MASS LLM Separated from System Prompt

**Problema actual:** El `SYSTEM_PROMPT` en `prompts.py` es un monolito de ~148 líneas que mezcla personalidad, reglas de búsqueda, flujo de agendamiento, reprogamación, manejo de errores, ejemplos de conversación, y restricciones de tipos de propiedad. Todo en un solo string. El LLM ve TODO cada turno, sin importar si el usuario está buscando propiedades, agendando una visita, o preguntando por FAQ.

Además, `_build_messages()` agrega MÁS bloques de sistema por encima (stage tag, sentiment, returning user, active property, pending scheduling) — el prompt final es una sopa de instrucciones donde lo relevante se diluye.

**Visión:** Cada capacidad (search, detail, schedule, faq, appointment, contact, greeting) tiene su propio prompt especializado. El router ya detecta la capacidad. Solo se inyecta el prompt de la capacidad detectada + los bloques dinámicos necesarios (user context, active property, scheduling info).

---

## FASE 0 — Auditoría y Extracción (1h)

### Objetivo
Extraer del SYSTEM_PROMPT monolítico los fragmentos correspondientes a cada capacidad, identificando qué es compartido vs qué es específico.

### Tareas

1. **Analizar SYSTEM_PROMPT actual y etiquetar cada sección:**

```
# Personalidad → SHARED (va siempre)
# Colaboración → SHARED (va siempre)
# Saludo Inicial → CAP greeting
# Formato de Respuestas → CAP search + detail + schedule + faq
# Contexto de Propiedad Activa → SHARED dinámico (ya en _build_messages)
# Criterios de Éxito → SHARED (va siempre)
# Condiciones de Parada → SHARED (va siempre)
# Alcance — Qué hago y qué no hago → SHARED (va siempre)
# Flujo de Agendamiento → CAP schedule
# Reprogramación y Cancelación → CAP appointment
# Rangos y Alternativas → CAP search
# property_type en search_properties → CAP search
# Ambigüedad de operación → CAP search
# Resultados vacíos → CAP search
# FAQ y Handoff → CAP faq + handoff
# Ejemplos de Conversación → cada ejemplo va con su CAP
```

2. **Identificar qué se inyecta dinámicamente (ya separado):**
   - `{company_name}` → `get_system_prompt()` resuelve
   - `### User Context` → sección dinámica con nombre/ubicación/presupuesto
   - `### ETAPA: X` → ya inyectado por router
   - `### TONO: NEGATIVO/URGENTE` → ya inyectado por SENTIMENT_KEYWORDS
   - `### ACTIVE PROPERTY CONTEXT` → ya inyectado en _build_messages
   - `### PENDING SCHEDULING INFO` → ya inyectado en _build_messages
   - `### USUARIO RECURRENTE` → ya inyectado en _build_messages

3. **Documentar el inventory actual** — crear un archivo `app/agents/prompts/INVENTORY.md` con el mapeo completo.

---

## FASE 1 — Estructura de Archivos (30min)

### Objetivo
Crear los directorios y archivos skeleton para los prompts modulares.

### Estructura propuesta

```
app/agents/prompts/
├── __init__.py
├── loader.py              ← nuevo: carga prompts de disco
├── shared/
│   ├── persona.md         ← Personalidad + Colaboración + Criterios de Éxito
│   ├── alcance.md         ← Qué hago y qué no hago
│   └── condiciones.md     ← Condiciones de Parada
├── capabilities/
│   ├── search.md          ← Búsqueda (reglas, property_type, operación, rangos)
│   ├── detail.md          ← Detalle de propiedad (formato, fotos)
│   ├── schedule.md        ← Agendamiento (flujo paso a paso, domingos)
│   ├── appointment.md     ← Reprogramación y cancelación
│   ├── faq.md             ← FAQ y handoff
│   ├── greeting.md        ← Saludo inicial
│   └── general.md         ← Conversación general fallback
└── examples/
    ├── search.md           ← Ejemplo 1: Búsqueda
    ├── schedule.md         ← Ejemplo 2: Detalles y visita + Ejemplo 4: Domingo
    ├── no-results.md       ← Ejemplo 5: Sin resultados
    └── faq.md              ← Ejemplo 3: FAQ
```

### Tareas

1. Crear `app/agents/prompts/` directorio completo
2. Crear `app/agents/prompts/__init__.py` (vacío o re-export)
3. Escribir `app/agents/prompts/loader.py` — carga archivos .md, parsea frontmatter YAML (simple, sin PyYAML), cachea en dict por capability
4. Escribir cada archivo de prompt con frontmatter YAML:

```yaml
---
capability: search
version: 1.0.0
depends_on: [shared/persona, shared/alcance]
inject_after: [user_context, active_property]
---
```

---

## FASE 2 — Fragmentar SYSTEM_PROMPT (2h)

### Objetivo
Extraer cada sección del SYSTEM_PROMPT actual a su archivo correspondiente. **No cambiar comportamiento todavía** — solo mover texto.

### Tareas

1. **shared/persona.md** — Copiar secciones #Personalidad, #Colaboración, #Criterios de Éxito
2. **shared/alcance.md** — Copiar sección #Alcance
3. **shared/condiciones.md** — Copiar sección #Condiciones de Parada
4. **capabilities/greeting.md** — Copiar sección #Saludo Inicial + ejemplo de saludo del SYSTEM_PROMPT
5. **capabilities/search.md** — Copiar reglas de búsqueda: #Formato (parte search), #Rangos, #property_type, #Ambigüedad, #Resultados vacíos
6. **capabilities/detail.md** — Copiar reglas de detalle: #Formato (parte detail), #Contexto de Propiedad Activa
7. **capabilities/schedule.md** — Copiar #Flujo de Agendamiento completo (pasos 1-5, domingo)
8. **capabilities/appointment.md** — Copiar #Reprogramación y Cancelación
9. **capabilities/faq.md** — Copiar #FAQ y Handoff + #Formato (parte FAQ)
10. **examples/search.md** — Copiar Ejemplo 1
11. **examples/schedule.md** — Copiar Ejemplo 2 y Ejemplo 4
12. **examples/no-results.md** — Copiar Ejemplo 5
13. **examples/faq.md** — Copiar Ejemplo 3

**Regla:** Cada archivo debe ser autocontenido — si necesita información de otro módulo, declararlo en `depends_on` del frontmatter.

---

## FASE 3 — Loader + Assembly Engine (2h)

### Objetivo
Implementar el motor que, dado un capability detectado por el router, arma el prompt final combinando:
- Shared base (persona + alcance + condiciones)
- Capability prompt específico
- Ejemplos relevantes (si aplica)
- Bloques dinámicos (user context, active property, etc.)

### Tareas

1. **Implementar `app/agents/prompts/loader.py`:**

```python
class PromptLibrary:
    """
    Carga y cachea prompts desde app/agents/prompts/.
    
    - load_all(): escanea directorios, parsea frontmatter, indexa por capability
    - get_capability_prompt(capability): devuelve el texto completo armado
      (shared base + capability + examples)
    - get_shared_prompt(): devuelve shared/persona + alcance + condiciones
    """
```

2. **Implementar el ensamblador:**

```python
def assemble_system_prompt(
    capability: str,      # del router.detect_capability()
    stage: str,           # del router.detect_stage()
    user_context: dict,   # nombre, presupuesto, etc.
    active_property: dict = None,
    pending_scheduling: dict = None,
    sentiment: str = None,
    is_returning: bool = False,
) -> str:
    """
    Arma el system prompt para este turno:
    
    1. SHARED BASE (persona + alcance + condiciones)
    2. CAPABILITY PROMPT (search | detail | schedule | ...)
    3. EXAMPLES relevantes a la capability
    4. User Context dinámico (nombre, preferencias)
    5. Active Property (si aplica)
    6. Pending Scheduling (si aplica)
    7. Stage tag (### ETAPA: X)
    8. Sentiment (### TONO: Y)
    9. Returning user (### USUARIO RECURRENTE)
    """
```

3. **Resolver el orden exacto de inyección:**

```
1. SHARED persona + alcance + condiciones     ← siempre
2. CAPABILITY-specific instructions            ← según detect_capability()
3. CAPABILITY-specific examples                ← según detect_capability()
4. ### User Context (nombre, presupuesto...)   ← si hay datos
5. ### ACTIVE PROPERTY CONTEXT                 ← si hay selected_property_id
6. ### PENDING SCHEDULING INFO                 ← si hay pending_scheduling.active
7. ### ETAPA: X                                ← según detect_stage()
8. ### TONO: Y                                 ← si hay sentimiento detectado
9. ### USUARIO RECURRENTE                      ← si is_returning
```

4. **Mantener `get_system_prompt()` como fallback** — durante la migración, si el loader falla o capability es desconocida, caer al monolito original.

---

## FASE 4 — Integración en real_estate_agent.py (1.5h)

### Objetivo
Modificar `_build_messages()` para que use el nuevo `assemble_system_prompt()` en lugar de `get_system_prompt()` + inyecciones manuales.

### Tareas

1. **Modificar `_build_messages()`** (línea 1054):

```python
# ANTES:
system_prompt = get_system_prompt(user_context)
messages.append({"role": "system", "content": system_prompt})

# Inyecciones manuales una por una:
if stage: ...  # ### ETAPA
_sentiment: ...  # ### TONO
returning_msg: ...  # ### USUARIO RECURRENTE
selected_prop_reminder: ...  # ### ACTIVE PROPERTY
schedule_context: ...  # ### PENDING SCHEDULING

# DESPUES:
from app.agents.prompts.loader import assemble_system_prompt

capability = detect_capability(user_message, user_context)
combined = assemble_system_prompt(
    capability=capability,
    stage=stage or detect_stage(user_message, user_context),
    user_context=user_context,
    active_property=selected_prop,
    pending_scheduling=pending,
    sentiment=_sentiment,
    is_returning=user_context.get("is_returning", False),
)
messages.append({"role": "system", "content": combined})
```

2. **Eliminar inyecciones manuales individuales** de `_build_messages()` (las líneas 1074-1200+ de ETAPA, TONO, returning, active property, pending scheduling)

3. **Pasar capability y stage detectados** como parámetros para no duplicar detección

---

## FASE 5 — Capability Detection en el Flujo Correcto (1h)

### Objetivo
Asegurar que `detect_capability()` se llame UNA VEZ al inicio de `process_turn()` y se herede a `_build_messages()`.

### Estado actual
- `process_turn()` llama `detect_stage()` → obtiene stage
- `_build_messages()` recibe `stage` como parámetro
- Pero NO recibe `capability` — hay que agregarlo

### Tareas

1. **Modificar `process_turn()`** para llamar `detect_capability()` junto con `detect_stage()`
2. **Pasar `capability` a `_build_messages()`** como parámetro
3. **Pasar `capability` a `assemble_system_prompt()`** para que seleccione el prompt correcto

---

## FASE 6 — Plan B Post-Tool Guidance Modularizado (1.5h)

### Objetivo
Los mensajes de Plan B (post-tool-call guidance) actualmente están hardcodeados en `real_estate_agent.py` como strings. Moverlos a archivos modulares también.

### Tareas

1. **Crear `app/agents/prompts/plan_b/` con archivos por herramienta:**
   - `search_properties.md` — Success: "Formateá resultados...", Failure: "Ofrecé alternativas..."
   - `get_property_details.md`
   - `schedule_visit.md`
   - `reschedule_appointment.md`
   - `cancel_appointment.md`
   - `get_faq_answer.md`
   - `get_property_images.md`

2. **Implementar `get_plan_b_prompt(tool_name, outcome)`** en loader.py

3. **Reemplazar strings hardcodeados** en `process_turn()` por llamadas al loader

---

## FASE 7 — Testing (2h)

### Objetivo
Verificar que el comportamiento del bot NO cambia después de la migración.

### Tareas

1. **Test de ensamblador:**
   - `test_assemble_search_prompt()` — verifica que incluya shared + search + user context
   - `test_assemble_schedule_prompt()` — verifica que incluya shared + schedule + pending scheduling
   - `test_assemble_without_capability()` — verifica que caiga al fallback monolito
   - `test_missing_file_doesnt_crash()` — verifica que borrar un archivo no rompa

2. **Test de regresión (comparación semántica):**
   - Para cada escenario (search, detail, schedule, faq, greeting), generar el prompt NUEVO y comparar vs el prompt ANTIGUO:
     - ¿Incluye todas las reglas necesarias?
     - ¿Excluye reglas irrelevantes?
     - ¿Mantiene el mismo tono?

3. **Test de integración:**
   - Ejecutar los 5 flujos manuales de Phase 7 (checklist original) y verificar que las respuestas son coherentes
   - Verificar que **no hay regresiones** en edge cases (Sunday, empty results, ambiguous operation, etc.)

---

## FASE 8 — CI/CD de Prompts (1h)

### Objetivo
Tratar los prompts como código con versionado y testing automatizado.

### Tareas

1. **Agregar test suite de prompts:**
   ```python
   # tests/test_prompts_modular.py
   def test_all_prompts_have_frontmatter():
   def test_all_prompts_have_capability_field():
   def test_all_prompts_have_version_field():
   def test_no_orphaned_references():
   def test_capability_coverage():  # router reconoce TODAS las capabilities
   ```

2. **Agregar validación de frontmatter** en CI (GitHub Actions):
   - Verificar que todo `.md` en `app/agents/prompts/` tiene frontmatter válido
   - Verificar que no hay `{company_name}` sin resolver en prompts dinámicos

3. **Documentar workflow de edición de prompts:**
   - Editar archivo → correr tests → PR → merge → deploy automático

---

## FASE 9 — Migración de Producción Gradual (1h)

### Objetivo
Migrar de a una capability por vez en producción para minimizar riesgo.

### Tareas

1. **Feature flag**: `USE_MODULAR_PROMPTS = True/False` en settings
2. **Rollout ordenado:**
   - Día 1: greeting + faq (bajo riesgo)
   - Día 2: search + detail (riesgo medio)
   - Día 3: schedule + appointment (riesgo alto — flujo más complejo)
3. **Monitoreo:**
   - Loggear qué capability activó el prompt modular vs monolito
   - Tracking de handoffs y fail counters — verificar que no aumenten
   - Latencia del LLM — medir reducción de tokens de entrada

---

## Métricas Esperadas

| Métrica | Antes | Después (estimado) |
|---------|-------|---------------------|
| Tokens de system prompt (search) | ~1,800 | ~600 |
| Tokens de system prompt (schedule) | ~1,800 | ~450 |
| Tokens de system prompt (faq) | ~1,800 | ~350 |
| Latencia promedio | ~3-5s | ~2-3.5s |
| Costo por turno (search) | ~$0.003 | ~$0.0015 |

---

## Archivos involucrados

| Archivo | Acción |
|---------|--------|
| `app/agents/prompts.py` | Mantener `get_system_prompt()` como fallback; deprecar gradualmente |
| `app/agents/prompts/__init__.py` | CREAR |
| `app/agents/prompts/loader.py` | CREAR — PromptLibrary + assemble_system_prompt |
| `app/agents/prompts/shared/persona.md` | CREAR |
| `app/agents/prompts/shared/alcance.md` | CREAR |
| `app/agents/prompts/shared/condiciones.md` | CREAR |
| `app/agents/prompts/capabilities/search.md` | CREAR |
| `app/agents/prompts/capabilities/detail.md` | CREAR |
| `app/agents/prompts/capabilities/schedule.md` | CREAR |
| `app/agents/prompts/capabilities/appointment.md` | CREAR |
| `app/agents/prompts/capabilities/faq.md` | CREAR |
| `app/agents/prompts/capabilities/greeting.md` | CREAR |
| `app/agents/prompts/capabilities/general.md` | CREAR |
| `app/agents/prompts/examples/search.md` | CREAR |
| `app/agents/prompts/examples/schedule.md` | CREAR |
| `app/agents/prompts/examples/no-results.md` | CREAR |
| `app/agents/prompts/examples/faq.md` | CREAR |
| `app/agents/prompts/plan_b/` (5-7 archivos) | CREAR |
| `app/agents/real_estate_agent.py` | MODIFICAR — _build_messages usa assemble_system_prompt |
| `app/agents/router.py` | MODIFICAR — exponer capability en flujo de process_turn |
| `tests/test_prompts_modular.py` | CREAR |
| `.github/workflows/prompt-ci.yml` | CREAR (opcional) |

---

## Glosario

| Término | Definición |
|---------|------------|
| **SHARED** | Instrucciones que van en TODOS los system prompts (personalidad, alcance, criterios de éxito) |
| **CAPABILITY** | Prompt específico para una capacidad del bot (search, detail, schedule, etc.) |
| **EXAMPLE** | Ejemplos de conversación relevantes a la capability |
| **DYNAMIC BLOCK** | Fragmento inyectado en base al contexto actual (user context, active property, etc.) |
| **assemble_system_prompt()** | Función que combina SHARED + CAPABILITY + EXAMPLES + DYNAMIC BLOCKS |

# Plan de arquitectura — InmuebleBot Knowledge Agent v4

Reemplazo del chatbot v3 por un *knowledge agent* evidence-aware, siguiendo el marco de Adwant & Srivastav (2026), *"From Chatbots to Knowledge Agents: Evidence-Aware Architectures for Long-Horizon Generative AI Systems"*, adaptado a un asistente inmobiliario y de atención al cliente con entendimiento de lenguaje natural conversacional.

Documento enfocado en arquitectura. El diagrama de bloques acompaña este plan (`arquitectura_knowledge_agent_v4.svg`).

---

## 1. Diagnóstico: por qué falla v1–v3

El research sostiene que los chatbots tradicionales son *stateless*, *short-horizon* y *answer-centric*. Tus cuatro quejas mapean exactamente contra esas limitaciones, y se confirman en el código del v3:

| Queja | Causa raíz en v3 (verificada en el código) | Limitación del paper |
|-------|---------------------------------------------|----------------------|
| No entiende lenguaje natural | El motor (`routers/v3/engine.py`) hace **una sola pasada** schema-guiada que devuelve un `intent` y una `action` únicos (`schema.py`, líneas 89–114). Cualquier matiz fuera de los 7 intents enum se aplana. | Answer-centric, fluidez sobre razonamiento |
| Problemas con mensajes multi-intención | El schema fuerza **un intent primario + una action**. "Quiero ver el depto del centro y agendar para el sábado" colapsa a una sola rama. No hay descomposición de objetivos. | Short-horizon, sin planificación |
| Olvida el contexto | El estado vive como `belief_delta` por turno en Redis (`BeliefStateV5`, TTL 24 h). Existen `episodic.py`, `semantic.py`, `user_model.py`, pero **no se inyectan como evidencia en el bucle del turno**. | Statelessness, sin memoria persistente integrada |
| No ejecuta acciones | Las 9 tools existen y están registradas, pero la acción única por turno + el FSM de scheduling limitan la ejecución encadenada de varias acciones. | Answer-centric, sin bucle agéntico real |

> Riesgo adicional relevante para inmobiliaria (no marcado pero crítico): **alucinación de propiedades/precios**. El paper lo resuelve con *evidence-awareness* y *abstención*; lo incorporamos como capa de primera clase.

El v3 ya hizo bien lo difícil de la infraestructura (multi-tenant con RLS, fail-open, prompt-cache, `gpt-5.4-mini`, pgvector, registry de tools). **No tiramos nada de eso.** El v4 cambia el *cerebro* (cómo entiende, recuerda y decide), no la *plomería*.

---

## 2. Principios de diseño (del paper → InmuebleBot)

1. **Transparencia sobre fluidez** — toda respuesta sobre una propiedad se ancla a un registro real de la DB; nada de inventar.
2. **Confiabilidad sobre velocidad** — antes de afirmar disponibilidad/precio, el agente verifica cobertura de evidencia.
3. **Iteración sobre finalidad** — un turno puede contener varios sub-objetivos y varias acciones encadenadas.
4. **Trazabilidad sobre abstracción** — cada dato mostrado conserva su fuente (property_id, FAQ id, doc chunk) en la memoria de evidencia.
5. **Memoria persistente como ciudadano de primera** — la memoria episódica/semántica/usuario se recupera *cada* turno, no solo se escribe.

---

## 3. Arquitectura propuesta (capas y componentes)

El v4 implementa el **bucle de agente unificado** del paper. Es plug-and-play: se monta como un router más (`active_router = "v4"`), exactamente como hoy convive v1/v2/v3, sin redeploy (solo el flip en el dashboard).

### 3.1 Entrada e infraestructura (se reutiliza tal cual)
- `webhook.py` → resuelve tenant por `phone_number_id`, fija GUC + ContextVar.
- Nuevo `routers/v4/adapter.py`: mismo **contrato de dict** que `process_turn_v3` (nunca lanza excepción; fail-open). Esto es lo que garantiza el "plug and play".
- **Compuertas de seguridad** (regex, 0 LLM): emergencia, pedido de humano, fuera de alcance, `/reset`. Verbatim del v3.

### 3.2 Percepción + descomponedor de objetivos (el fix de NLU y multi-intención)
Una llamada estructurada a `gpt-5.4-mini` que reemplaza el schema "1 intent / 1 action" por:

```jsonc
{
  "belief_delta": { ... },              // igual que v3 (operación, tipo, zona, presupuesto, dorms…)
  "sub_goals": [                         // NUEVO: lista ordenada de objetivos del turno
    { "intent": "search",     "args_hint": {...} },
    { "intent": "scheduling", "args_hint": {...} }
  ],
  "references": { "selected_property_id": 7, "anaphora": "el del centro" },
  "confidence": 0.0
}
```

Esto resuelve directamente *"no entiende NL"* y *"multi-intención"*: el mensaje se descompone en N sub-objetivos que el bucle de control ejecuta y satisface uno por uno.

### 3.3 Recuperador consciente de evidencia (Evidence-Aware Retriever)
Por cada sub-objetivo, recupera de **tres fuentes** y arma un *pool de evidencia* con procedencia:
- **PostgreSQL (Render)** — propiedades, turnos, leads, FAQ (tenant-scoped, vía tools del registry).
- **pgvector** — FAQ + documentos (RAG, `text-embedding-3-small`, ya existente).
- **Memoria de 3 niveles** — episódica (sesiones previas del cliente), semántica (conocimiento de zona/inmobiliaria), de usuario (preferencias). **Esta es la pieza que el v3 no inyectaba** y que arregla el olvido de contexto.

Cada ítem de evidencia lleva: fuente, id, timestamp, score. Híbrido denso + keyword, igual que recomienda el paper.

### 3.4 Razonamiento + ejecución de tools
- `gpt-5.4-mini` ejecuta el ciclo **plan → act → observe** sobre los sub-objetivos, encadenando varias tools por turno (búsqueda + agendado + lead en un solo mensaje del cliente). Reutiliza el patrón de `agents/agentic_loop.py`.
- Las tools siguen siendo el **registry tenant-scoped existente**.

### 3.5 Evaluador de evidencia + estimador de confianza/incertidumbre
Antes de responder, evalúa (5 dimensiones del paper): completitud, profundidad, recencia, autoridad, consistencia. Produce `evidence_coverage` y `confidence`. **Si una afirmación sobre una propiedad no tiene evidencia con id real → no se afirma.** Anti-alucinación de primera clase.

### 3.6 Bucle de control
Decide, como en la Figura 1 del paper:
- **Responder** si cobertura/confianza superan umbral.
- **Recuperar más** (loop a 3.3) si hay huecos — máx. iteraciones acotadas por disciplina de costo (mediana ≤3–4 llamadas LLM/turno).
- **Abstenerse / clarificar** si la evidencia es insuficiente o contradictoria (en vez de inventar).
- **Handoff** a humano si detecta el caso (tool `request_human_assistance`).

### 3.7 Respuesta + actualización de memoria (write-back)
- Envía el `response_plan` (texto/imágenes) al canal.
- **Escribe de vuelta**: episodio (query→acción→resultado), evidencia usada (claim→fuente), y actualización del modelo de usuario. Esto cierra el ciclo y hace que el siguiente turno recuerde.

---

## 4. Tools necesarias

Se conservan las **9 tools** del registry v3 (search_properties, get_property_details, get_property_images, get_faq_answer, schedule_visit, get_my_appointments, cancel_appointment, reschedule_appointment, request_human_assistance) y se agregan las requeridas para atención al cliente completa:

| Tool | Estado | Función | Acción solicitada |
|------|--------|---------|-------------------|
| `search_properties` + `get_property_details` + `get_property_images` | Existe | Búsqueda y recomendación sobre inventario real | Búsqueda de propiedades |
| `schedule_visit` / `get_my_appointments` / `cancel_appointment` / `reschedule_appointment` | Existe | Coordinar y gestionar visitas (FSM de booking) | Agendar visitas |
| `request_human_assistance` | Existe | Derivar a agente humano | Escalar a humano |
| `get_faq_answer` | Existe | Respuestas de conocimiento (zona, requisitos, garantías) | Atención al cliente |
| `capture_lead` | **Nueva** | Registrar lead en DB (`sales_inquiry` / modelo existente) | Capturar leads |
| `qualify_lead` | **Nueva** | Calificar (presupuesto, zona, urgencia, tipo) y marcar score | Calificar leads |

`capture_lead`/`qualify_lead` se apoyan en modelos que ya existen (`sales_inquiry.py`, `user_episode.py`) — bajo costo de integración.

---

## 5. Integración plug-and-play con la app de InmuebleBot

| Pieza compartida | Cómo la usa el v4 |
|------------------|-------------------|
| `webhook.py` + resolución de tenant (RLS/GUC/ContextVar) | Sin cambios |
| `routers/v4/adapter.py` | Mismo contrato dict que v3; selección por `active_router="v4"` |
| Registry de tools (`app/tools/v2/`) | Reutilizado, tenant-scoped; +2 tools nuevas |
| `gpt-5.4-mini` (key en `.env`, `OPENAI_MODEL`/`LLM_MODEL_*`) | Único modelo, igual que v3 (incluido en disciplina de costo) |
| PostgreSQL en Render (`DATABASE_URL`) | Misma DB; nuevas escrituras de memoria/evidencia |
| pgvector + `text-embedding-3-small` | Reutilizado para RAG |
| Redis (estado/creencia) | Reutilizado; se le suma recuperación de memoria persistente |
| Fail-open + prompt-cache | Conservados |

**Cutover:** flip manual `v3 → v4` por tenant en el dashboard, con rollback inmediato a v3 (igual que la estrategia v2↔v3 actual). Sin redeploy.

---

## 6. Plan de implementación por fases

1. **Fase 0 — Scaffolding:** `routers/v4/` (adapter, engine, schema, prompts) clonando el contrato de v3; flag `active_router="v4"`.
2. **Fase 1 — Percepción + sub-objetivos:** nuevo schema con `sub_goals[]`; resuelve multi-intención. Tests con `angelo-hard-test-conversations-150.md`.
3. **Fase 2 — Recuperador de evidencia + memoria persistente:** integrar episódica/semántica/usuario en el turno; pool de evidencia con procedencia. Resuelve olvido de contexto.
4. **Fase 3 — Evaluador de evidencia + abstención:** umbrales de cobertura/confianza; anti-alucinación.
5. **Fase 4 — Ejecución multi-acción + tools nuevas:** `capture_lead`, `qualify_lead`; encadenado de acciones.
6. **Fase 5 — Bucle de control + write-back:** iterar/abstener/handoff; persistencia de memoria.
7. **Fase 6 — Verificación:** correr el corpus de 150 conversaciones y comparar v3 vs v4 (ver §7).

---

## 7. Métricas de éxito (verificación)

Alineadas con el paper (confianza, cobertura de evidencia, tasa de éxito) y con tus quejas:

- **Multi-intención:** % de mensajes con ≥2 sub-objetivos resueltos en un turno (meta: ≫ v3, que hoy es ~0).
- **Retención de contexto:** % de referencias anafóricas ("el del centro", "ese mismo") resueltas correctamente entre turnos y entre sesiones.
- **Grounding / anti-alucinación:** % de afirmaciones sobre propiedades con `property_id` real (meta ~100%); tasa de abstención correcta cuando falta evidencia.
- **Ejecución de acciones:** % de intenciones accionables (agendar, lead, handoff) efectivamente ejecutadas.
- **Cobertura de evidencia y confianza promedio** por turno (referencia del paper: 0.63 y 0.78).
- **Costo:** mediana ≤3–4 llamadas LLM/turno; comparación A/B v3 vs v4 sobre `angelo-hard-test-conversations-150.md`.

---

## 8. Resumen

El v4 mantiene toda la infraestructura productiva del v3 (multi-tenant, fail-open, `gpt-5.4-mini`, PostgreSQL/pgvector/Redis, registry de tools) y reemplaza el núcleo cognitivo por el bucle evidence-aware del paper: **percepción con descomposición de objetivos** (multi-intención), **recuperador consciente de evidencia con memoria persistente integrada** (contexto), **evaluador de evidencia + abstención** (anti-alucinación) y **bucle de control que ejecuta múltiples acciones** (agendar, leads, búsqueda, handoff). El resultado es un asistente inmobiliario que entiende lenguaje natural conversacional, recuerda, actúa y dice "no sé" cuando corresponde — en lugar de un chatbot answer-centric.

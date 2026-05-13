# InmuebleBot — Documentación Técnica del Agente Conversacional

> Ingeniería inversa completa del flujo del bot, sus módulos, tools, memoria y contexto.
> Objetivo: que un desarrollador pueda modificar el comportamiento del agente sin perderse.

---

## 1. Resumen General del Bot

**InmuebleBot** es un agente conversacional de bienes raíces que opera vía **WhatsApp Business Cloud API (Meta)**. Recibe mensajes de texto de usuarios, los procesa con un LLM (OpenAI GPT-4o-mini), ejecuta herramientas (tool calling), y responde de vuelta por WhatsApp.

### Qué hace el agente
- Busca propiedades en una base de datos PostgreSQL por criterios (ubicación, precio, tipo, dormitorios)
- Muestra detalles e imágenes de propiedades específicas
- Agenda, reprograma y cancela visitas con sincronización a Google Calendar
- Guarda preferencias del usuario entre sesiones (PostgreSQL) y dentro de la sesión (Redis)
- Deriva a agente humano cuando el usuario lo pide
- Responde FAQs sobre la inmobiliaria

### Componentes principales

| Componente | Archivo | Rol |
|---|---|---|
| FastAPI App | `app/main.py` | Entry point HTTP, lifespan, routers |
| Webhook receptor | `app/api/routes/webhook.py` | Recibe y despacha mensajes WhatsApp |
| Agente principal | `app/agents/real_estate_agent.py` | Orquestador: LLM + tools + memoria |
| LLM Router | `app/agents/llm_router.py` | Cliente OpenAI con retry |
| Tools | `app/agents/tools.py` | 13 funciones async ejecutables por el LLM |
| Prompts | `app/agents/prompts.py` | System prompt + definiciones de tools para el LLM |
| Memoria | `app/core/memory.py` | Redis (corto plazo) + PostgreSQL (largo plazo) |
| State Machine | `app/core/state_machine.py` | Estados de conversación en Redis |
| Property Service | `app/services/property_service.py` | Búsqueda en DB |
| Appointment Service | `app/services/appointment_service.py` | CRUD de citas + Google Calendar |
| Handoff Service | `app/services/handoff_service.py` | Transferencia a humano |

### Entrypoint principal
```
app/main.py
  → incluye app/api/routes/webhook.py en /webhook/whatsapp
```

El bot arranca como una app **FastAPI**. Todo el tráfico de WhatsApp entra por `POST /webhook/whatsapp`.

---

## 2. Flujo Completo del Mensaje

```
Usuario envía WhatsApp
        ↓
POST /webhook/whatsapp  [webhook.py: receive_webhook()]
        ↓
asyncio.ensure_future(_safe_process(messages))   ← retorna 200 OK a Meta inmediatamente
        ↓
process_messages()  [webhook.py]
  ├── Guards: is_echo, bot_number, dedup, rate_limit, global_rate_limit
  ├── Extracción del texto (text, button, interactive, etc.)
  ├── sanitize_text() + sanitize_phone()
  └── real_estate_agent.process_turn(phone, text)
        ↓
RealEstateAgent.process_turn()  [real_estate_agent.py]
  ├── memory_manager.get_merged_context(phone)     ← Redis + PostgreSQL
  ├── memory_manager.get_recent_messages(phone, 15) ← Redis
  ├── appointment_service.get_upcoming_appointments() ← DB
  ├── _detect_handoff_request()                    ← keyword check
  ├── _build_messages()                            ← construye lista de mensajes para LLM
  └── LOOP (max 5 iteraciones):
        ├── llm_router.ainvoke(messages, tools)    ← OpenAI API
        ├── Si tool_calls → execute_tool(name, args, phone) [tools.py]
        │     └── agrega resultado a messages como role=tool
        └── Si sin tool_calls → response_text final
        ↓
_clean_response() + _detect_action_hallucination()
        ↓
asyncio.create_task(_background_post_processing())
  ├── memory_manager.save_message(phone, "assistant", response)
  ├── state_machine.set_state(phone, next_state)
  ├── _update_lead_score()
  └── _extract_and_save_preferences()
        ↓
return {response_text, rich_content, tools_used, next_state}
        ↓
webhook.py: sanitize_bot_response(response_text)
        ↓
whatsapp_client.send_message(phone_to, text)
whatsapp_client.send_image(phone_to, url)  ← si hay imágenes
```

**Punto clave de rendimiento:** El webhook retorna `200 OK` a Meta inmediatamente antes de procesar. El processing corre en background con `asyncio.ensure_future`. Luego de obtener el resultado del agente, se envía el WhatsApp primero, y la persistencia de estado/preferencias corre en otro background task.

---

## 3. Mapa de Módulos del Bot

### `app/api/routes/webhook.py`
**Qué hace:** Punto de entrada HTTP para WhatsApp.

**Funciones importantes:**
- `receive_webhook()` — extrae `entry[].changes[].value.messages[]` del payload Meta
- `process_messages()` — normaliza cada mensaje, aplica guards, llama al agente
- `format_phone_number()` — normaliza números argentinos (+54 → 54375415...)
- `_is_duplicate()` — dedup por message_id con cache en memoria (TTL 5min)
- `_check_user_rate_limit()` — 1 mensaje/seg por usuario

**Llama a:**
- `real_estate_agent.process_turn()`
- `whatsapp_client.send_message()` / `send_image()`
- `sanitize_text()`, `sanitize_phone()`, `sanitize_bot_response()`

**Retorna a Meta:** `{"status": "ok"}` siempre (para evitar retries de Meta)

---

### `app/agents/real_estate_agent.py` ← CORE DEL BOT
**Qué hace:** Orquesta el ciclo LLM → Tools → respuesta. Es la función más importante del bot.

**Clase:** `RealEstateAgent`
**Instancia global:** `real_estate_agent = RealEstateAgent()`

**Método principal:** `process_turn(phone, user_message, intent=None)`

**Flujo interno de `process_turn`:**
1. Carga contexto merged (Redis + PG): `memory_manager.get_merged_context(phone)`
2. Carga historial reciente: `memory_manager.get_recent_messages(phone, 15)`
3. Carga citas existentes: `appointment_service.get_upcoming_appointments()`
4. Detección rápida de handoff: `_detect_handoff_request()` por keywords
5. Construye lista de mensajes: `_build_messages()` → system + contexto + historial + mensaje
6. Loop de tool calling (máx. 5 iteraciones):
   - Llama al LLM: `llm_router.ainvoke(messages, tools)`
   - Si hay tool calls → `execute_tool()` → append result a messages
   - Si no hay tool calls → respuesta final
7. Guards post-respuesta: `_clean_response()`, `_detect_action_hallucination()`
8. Background: guarda mensaje, actualiza estado, lead score, preferencias

**Short-circuits implementados:**
- `search_properties` → retorna formatted result directamente sin segunda llamada al LLM
- `cancel_appointment` con "Cita Cancelada" → short-circuit
- Cualquier tool con `<!--CONFIRMED:-->` → short-circuit
- Anti-loop: si el mismo tool se llama 2 veces seguidas → break

**Anti-alucinación:**
- Si el LLM dice "voy a buscar" sin llamar `search_properties` → inyecta mensaje de corrección y reintenta
- Si el LLM afirma haber agendado/cancelado/guardado sin llamar el tool correspondiente → reemplaza con mensaje de error

---

### `app/agents/llm_router.py`
**Qué hace:** Wrapper del SDK de OpenAI con retry y parsing de tool calls.

**Clase:** `LLMRouter`
**Instancia global:** `llm_router = LLMRouter()`

**Método principal:** `ainvoke(messages, tools, temperature, max_tokens)`

**Configuración (desde `app/core/config.py`):**
- Modelo: `OPENAI_MODEL` (default `gpt-4o-mini`)
- Timeout: `LLM_TIMEOUT_SECONDS`
- Retries: `LLM_MAX_RETRIES` con exponential backoff (2^attempt seg)
- Retryable status codes: 429, 500, 502, 503, 504

**Retorna:** `LLMResponse` con:
- `content: str` — texto del LLM
- `tool_calls: list[ToolCall]` — lista de herramientas a ejecutar
- `has_tool_calls: bool` — property
- `usage: dict` — tokens usados
- `provider: str` — siempre "openai"

---

### `app/agents/prompts.py`
**Qué hace:** Define el system prompt del agente y las definiciones de tools para el LLM.

**Elementos clave:**

**`SYSTEM_PROMPT`** — instrucciones completas del agente:
- Personalidad: agente inmobiliario argentino, cálido, informal
- Flujo de calificación: operación → ubicación → tipo → presupuesto → dormitorios (de a uno)
- Reglas de búsqueda: buscar solo con ≥3 criterios, máximo 3 resultados
- "Propiedad activa": la última que el usuario vio en detalle
- Ejemplos few-shot de conversaciones (7 ejemplos inline)
- Flujo de agendado: confirmar propiedad → fecha/hora → nombre → schedule_visit
- Reglas de rescheduling y cancelación

**`TOOL_DEFINITIONS`** — lista de 13 tools en formato OpenAI function calling

**`get_system_prompt(user_context)`** — genera el prompt con el contexto del usuario inyectado al final:
```
### User Context
Nombre: Juan | Ubicacion: Posadas | Presupuesto: $150,000 | Tipo: casa | Operacion: alquiler
```

**`format_messages_for_llm(user_message, history, user_context)`** — prepara mensajes con historial (últimos 10 mensajes)

---

### `app/agents/tools.py`
**Qué hace:** Implementa las 13 funciones async que el LLM puede invocar.

**Dispatcher central:**
```python
TOOL_FUNCTIONS = {
    "search_properties": search_properties,
    "get_property_details": get_property_details,
    "recommend_properties": recommend_properties,
    "compare_properties": compare_properties,
    "update_user_preferences": update_user_preferences,
    "get_user_preferences": get_user_preferences,
    "save_lead_info": save_lead_info,
    "schedule_visit": schedule_visit,
    "reschedule_appointment": reschedule_appointment_tool,
    "cancel_appointment": cancel_appointment_tool,
    "get_my_appointments": get_my_appointments,
    "request_human_assistance": request_human_assistance,
    "refine_search": refine_search,
    "get_property_images": get_property_images,
    "get_faq_answer": get_faq_answer,
}
```

**`execute_tool(tool_name, arguments, phone)`** — ejecuta cualquier tool por nombre. Gestiona el routing de argumentos especiales (phone inyectado para ciertos tools).

---

### `app/core/memory.py`
**Qué hace:** Gestión híbrida de memoria Redis + PostgreSQL con fallback en RAM.

**Clase:** `MemoryManager`
**Instancia global:** `memory_manager = MemoryManager()`

**Almacenamiento Redis (corto plazo, TTL 24h):**
- `user:{phone}:context` — estado actual de la conversación (JSON)
- `user:{phone}:messages` — últimos 20 mensajes (JSON array)
- `user:{phone}:summary` — resumen de conversación (string)
- `user:{phone}:state` — estado de la state machine (string)

**Almacenamiento PostgreSQL (largo plazo):**
- Tabla `users`: `location_preferences`, `property_type`, `budget_min`, `budget_max`, `lead_score`, `last_interaction`

**Fallback en RAM:** Si Redis cae, `_fallback_context` y `_fallback_messages` (dicts en memoria del proceso) mantienen la sesión activa.

---

### `app/core/state_machine.py`
**Qué hace:** Máquina de estados finitos para la conversación.

**Clase:** `ConversationState`
**Instancia global:** `state_machine = ConversationState()`

**Estados:**
```
idle → qualifying → searching → viewing_property → booking → completed
  ↓                                                              ↓
handoff/human_assistance  ←←←←←←←←← desde cualquier estado
```

**Persistencia:** `user:{phone}:state` en Redis (TTL 24h).

**Uso:** El agente llama `state_machine.set_state(phone, next_state)` en background post-turno, con `allow_invalid=True` (no valida transición).

---

### `app/services/property_service.py`
**Qué hace:** Búsqueda de propiedades en PostgreSQL.

**Método principal:** `search_properties(criteria, db_session=None)`

**Criterios soportados:** `location` (ILIKE), `budget_min`, `budget_max`, `bedrooms` (mínimo), `bathrooms`, `property_type`, `operation_type`, `limit`, `sort_by`, `title_search`

**Fallback:** Si la DB no está disponible, devuelve propiedades de ejemplo hardcodeadas (`_get_fallback_properties`)

---

### `app/services/appointment_service.py`
**Qué hace:** CRUD de citas con verificación de disponibilidad en DB y Google Calendar.

**Clase:** `AppointmentService`
**Instancia global:** `appointment_service = AppointmentService()`

**Métodos principales:**
- `create_appointment(user_id, property_id, start_time, type)` → verifica conflictos locales + Google Calendar → crea en DB
- `reschedule_appointment(appointment_id, new_start_time)` → cancela vieja + crea nueva + sync Calendar
- `cancel_appointment(appointment_id, reason)` → marca como cancelled + sync Calendar
- `get_user_appointments(user_id, upcoming=True)` → lista de citas futuras

**Lógica de Calendar:** Delega a `calendar_service.check_availability()` y `calendar_service.create_visit_event()`. Si no está configurado, la cita se crea solo en DB.

**`format_appointment_confirmation(appointment)`** — genera mensaje formateado para WhatsApp con metadata oculta `<!--CONFIRMED:YYYY-MM-DD HH:MM-->` que el agente usa para detectar éxito.

---

### `app/services/handoff_service.py`
**Qué hace:** Transferencia a agente humano.

**Método principal:** `trigger_handoff(phone, reason)`
1. Llama `generate_conversation_summary()` → usa LLM para resumir la conversación
2. Guarda resumen en preferencias del usuario
3. Cambia estado a `HUMAN_ASSISTANCE`
4. Llama `_notify_admin()` (actualmente solo loguea — TODO: WhatsApp/email/Slack)

---

## 4. Relaciones Entre Funciones (Call Graph)

```
webhook.receive_webhook()
  └── process_messages()
        ├── sanitize_text() / sanitize_phone()
        └── real_estate_agent.process_turn(phone, message)
              ├── memory_manager.get_merged_context(phone)
              │     ├── memory_manager.get_user_context(phone)       [Redis]
              │     └── memory_manager.get_user_preferences(phone)   [PostgreSQL]
              ├── memory_manager.get_recent_messages(phone, 15)      [Redis]
              ├── appointment_service.get_upcoming_appointments()     [PostgreSQL]
              ├── _detect_handoff_request(message)
              │     └── handoff_service.trigger_handoff()  [si positivo]
              ├── _build_messages(user_message, history, context, phone, last_props)
              │     ├── get_system_prompt(user_context)              [prompts.py]
              │     ├── Inyecta system messages contextuales
              │     └── Appends history + user_message
              └── LOOP:
                    ├── llm_router.ainvoke(messages, tools)          [OpenAI API]
                    │     └── AsyncOpenAI.chat.completions.create()
                    └── execute_tool(tool_name, args, phone)
                          └── TOOL_FUNCTIONS[tool_name](...)
                                ├── search_properties(criteria, phone)
                                │     ├── sanitize_criteria()
                                │     └── property_service.search_properties(criteria)
                                │           └── PropertyRepository.search()   [PostgreSQL]
                                ├── get_property_details(property_id)
                                │     └── BaseRepository.get(id)             [PostgreSQL]
                                ├── get_property_images(property_id)
                                │     └── BaseRepository.get(id)             [PostgreSQL]
                                ├── schedule_visit(property_id, date_str, time_str, phone, name)
                                │     ├── parse_spanish_datetime()
                                │     ├── validate_future()
                                │     ├── property_service.get_property_details()
                                │     ├── UserRepository.get_by_phone()      [PostgreSQL]
                                │     └── appointment_service.create_appointment()
                                │           ├── _check_conflict()            [PostgreSQL]
                                │           ├── calendar_service.check_availability()
                                │           ├── calendar_service.create_visit_event()
                                │           └── INSERT Appointment           [PostgreSQL]
                                ├── reschedule_appointment_tool(...)
                                │     └── appointment_service.reschedule_appointment()
                                ├── cancel_appointment_tool(...)
                                │     └── appointment_service.cancel_appointment()
                                ├── get_faq_answer(question)
                                │     └── faq_service.search_faqs(query)    [PostgreSQL]
                                ├── request_human_assistance(phone, reason)
                                │     └── handoff_service.trigger_handoff()
                                └── update_user_preferences(phone, ...)
                                      └── memory_manager.update_user_preferences() [PostgreSQL]

              [background task post-turn]
              ├── memory_manager.save_message(phone, "assistant", text)  [Redis]
              ├── state_machine.set_state(phone, next_state)              [Redis]
              ├── _update_lead_score(phone, tools_used, message)          [PostgreSQL]
              └── _extract_and_save_preferences(phone, message, prefs)
                    └── memory_manager.extract_and_save_preferences()
                          └── memory_manager.update_user_preferences()    [PostgreSQL]
```

---

## 5. Prompts y Construcción de Contexto

### System Prompt (`SYSTEM_PROMPT` en `prompts.py`)
El prompt está escrito en español rioplatense y define:
- Personalidad y tono del agente
- Orden de preguntas de calificación
- Cuándo buscar (≥3 criterios)
- Concepto de "propiedad activa" (la última vista en detalle)
- Formato de respuesta para cada tipo de resultado
- Flujo de agendado paso a paso
- 7 ejemplos few-shot inline

**Para modificar el comportamiento del bot → este es el archivo principal.**

### Construcción del contexto en `_build_messages()` (`real_estate_agent.py`)

Los mensajes se construyen en este orden:

```
1. System: SYSTEM_PROMPT + user context (nombre, budget, etc.)
2. System: "USUARIO RECURRENTE" con última referencia [si es sesión nueva y hay contexto]
3. System: "ACTIVE PROPERTY CONTEXT" con property_id activo [si hay propiedad seleccionada]
4. System: "PENDING SCHEDULING INFO" con fecha/hora guardada [si hay info pendiente]
5. System: <last_results> con mapeo opción N → ID de DB [si hay propiedades mostradas]
6. System: "CITAS EXISTENTES" del usuario [si tiene citas futuras]
7. System: "RESUMEN DE CONVERSACION" con estado actual [si hay historial]
8. History: últimos mensajes de la conversación (role: user/assistant)
9. System: "IMPORTANTE: primer mensaje" [si es primera interacción]
10. User: mensaje actual del usuario
```

Durante el loop de tools, se inyectan system messages adicionales después de cada tool result:
- Después de `search_properties`: "siempre preguntá si quieren ver detalles"
- Después de `get_property_details`: "usá exactamente los datos del tool result"
- Después de `schedule_visit` exitoso: "confirmá los detalles"

### Cómo se arman los tokens
- Historial: últimos 15 mensajes (en `process_turn`) pero se pasan los últimos 10 al `format_messages_for_llm`
- `last_shown_properties`: máximo 6 propiedades comprimidas a `{id, title}` en el contexto
- User context inyectado en una sola línea compacta al final del system prompt

---

## 6. Tools y Acciones

### Las 13 herramientas

| Tool | Función | Qué hace | Retorna |
|---|---|---|---|
| `search_properties` | `search_properties(criteria, phone)` | Busca propiedades. Tiene fallback automático: +30% budget, sin budget | String formateado con lista |
| `get_property_details` | `get_property_details(property_id)` | Detalles de una propiedad por ID entero, UUID, o nombre fuzzy | String formateado detallado |
| `get_property_images` | `get_property_images(property_id)` | Imágenes de una propiedad | JSON string `{"images": [urls]}` |
| `recommend_properties` | `recommend_properties(user_preferences)` | Propiedades basadas en preferencias guardadas | String formateado |
| `compare_properties` | `compare_properties(property_ids)` | Tabla comparativa de 2-3 propiedades | String con tabla ASCII |
| `update_user_preferences` | `update_user_preferences(phone, ...)` | Guarda/actualiza preferencias en PostgreSQL | String confirmación |
| `get_user_preferences` | `get_user_preferences(phone)` | Lee preferencias guardadas del usuario | String formateado |
| `save_lead_info` | `save_lead_info(phone, name, email, budget, notes)` | Guarda datos del lead | String confirmación |
| `schedule_visit` | `schedule_visit(property_id, date_str, time_str, phone, client_name)` | Agenda visita en DB + Calendar | Mensaje confirmación con `<!--CONFIRMED:...-->` |
| `reschedule_appointment` | `reschedule_appointment_tool(apt_id, new_date, new_time, phone)` | Reprograma cita | Mensaje confirmación |
| `cancel_appointment` | `cancel_appointment_tool(apt_id, reason, phone)` | Cancela cita | String confirmación |
| `get_my_appointments` | `get_my_appointments(phone)` | Lista citas del usuario | String formateado |
| `request_human_assistance` | `request_human_assistance(phone, reason)` | Handoff a humano | String confirmación |
| `refine_search` | `refine_search(refinement, previous_criteria)` | Refinamiento de búsqueda | Mensaje indicativo (el LLM debe llamar `search_properties` de nuevo) |
| `get_faq_answer` | `get_faq_answer(question, phone)` | Busca respuesta en tabla FAQs de DB | String con FAQs encontradas o "NO_FAQ_MATCH" |

### Cómo se registran los tools
Las definiciones de tool están en `TOOL_DEFINITIONS` (lista) en `prompts.py`, en formato OpenAI function calling. Se pasan directo al LLM en cada llamada. No hay auto-discovery: cada tool está declarado manualmente en JSON schema.

### Cómo decide el LLM usar un tool
El agente pasa `tool_choice: "auto"` a OpenAI. El LLM decide según las descripciones de los tools y el contexto de la conversación.

### Cómo se ejecutan los tools
`execute_tool(tool_name, arguments, phone)` en `tools.py`:
1. Busca la función en `TOOL_FUNCTIONS`
2. Para `search_properties`: pasa `arguments` como primer arg + `phone`
3. Para `schedule_visit`, `reschedule_appointment`, etc.: pasa `phone` + `**arguments`
4. Para otros: `**arguments`

### Guard de property_id en `schedule_visit`
Antes de ejecutar `schedule_visit`, el agente verifica en memoria si hay un `selected_property_id`. Si el LLM pasa un `property_id` diferente al activo, lo corrige automáticamente (líneas 238-252 de `real_estate_agent.py`).

### Señal `<!--CONFIRMED:-->` 
El `format_appointment_confirmation()` en `appointment_service.py` agrega `<!--CONFIRMED:YYYY-MM-DD HH:MM-->` al final del mensaje. El agente detecta esta señal para hacer short-circuit y también para loguear el datetime confirmado.

---

## 7. Memoria y Estado Conversacional

### Arquitectura de memoria

```
┌─────────────────────────────────────────────────────────┐
│                    REDIS (TTL 24h)                      │
│                                                         │
│  user:{phone}:context  →  {                            │
│    current_state: "searching",                          │
│    selected_property_id: "42",                          │
│    selected_property_title: "Casa Oberá Centro",        │
│    last_shown_properties: [{id, title}, ...],           │
│    last_search_criteria: {...},                         │
│    pending_scheduling_info: {property_id, date, time},  │
│    is_returning: true                                   │
│  }                                                      │
│                                                         │
│  user:{phone}:messages  →  [{role, content, ts}, ...]  │
│  user:{phone}:state     →  "searching"                 │
│  user:{phone}:summary   →  "resumen..." (placeholder)  │
└─────────────────────────────────────────────────────────┘
                         +
┌─────────────────────────────────────────────────────────┐
│               POSTGRESQL (persistente)                  │
│                                                         │
│  users table:                                           │
│    whatsapp_phone, name, email,                         │
│    location_preferences[], property_type[],             │
│    budget_min, budget_max, lead_score,                  │
│    last_interaction                                     │
│                                                         │
│  appointments table: citas agendadas                   │
│  properties table: catálogo de propiedades             │
│  faqs table: preguntas frecuentes                      │
└─────────────────────────────────────────────────────────┘
                         +
┌─────────────────────────────────────────────────────────┐
│          RAM (fallback si Redis cae)                    │
│  _fallback_context: Dict[phone, dict]                  │
│  _fallback_messages: Dict[phone, list]                 │
└─────────────────────────────────────────────────────────┘
```

### Flujo de contexto entre turnos

**En el mismo turno:**
- `selected_property_id` se guarda en Redis cuando el usuario ve detalles o imágenes
- `last_shown_properties` se guarda (comprimido: id+title) tras cada búsqueda

**Entre turnos (siguiente mensaje del mismo usuario):**
- `get_merged_context()` lee Redis + PostgreSQL y los fusiona
- Redis tiene precedencia para campos de sesión; PostgreSQL para preferencias
- El agente inyecta `last_shown_properties` en el system prompt como `<last_results>`
- `selected_property_id` se inyecta como "ACTIVE PROPERTY CONTEXT"
- `pending_scheduling_info` se inyecta si el usuario había mencionado querer agendar

**Entre sesiones (usuario vuelve días después):**
- Redis expiró → historial vacío pero preferencias en PostgreSQL subsisten
- El agente detecta `is_new_session = len(history) == 0` y `has_context = bool(selected_property_id or last_shown_properties)`
- Si hay contexto previo pero no historial → activa mensaje de "usuario recurrente"

### Qué se guarda en background (post-turno)
1. Mensaje del asistente → `memory_manager.save_message(phone, "assistant", text)` → Redis
2. Estado nuevo → `state_machine.set_state()` → Redis
3. Lead score → `_update_lead_score()` → PostgreSQL
4. Preferencias extraídas del mensaje → `extract_and_save_preferences()` → PostgreSQL (regex sobre texto)

### `extract_and_save_preferences()` — extracción automática
Usa regex para detectar en el texto del usuario:
- Ubicaciones: lista hardcodeada (Asunción, Encarnación, Posadas, Oberá, etc.)
- Presupuesto: patrones como "hasta $150000", "presupuesto de..."
- Tipo de propiedad: keywords como "casa", "departamento", "terreno", etc.
- Operación: "alquilar", "comprar", "venta", etc.
- Dormitorios y baños: patrones numéricos

---

## 8. Diagramas de Flujo en Texto

### Flujo general del mensaje

```
Usuario WhatsApp
      ↓
POST /webhook/whatsapp
      ↓
   [Guards]
   ¿is_echo?        → skip
   ¿bot_number?     → skip
   ¿duplicate?      → skip
   ¿rate_limited?   → skip
   ¿global_limit?   → skip
      ↓
   Extraer texto + sanitizar
      ↓
real_estate_agent.process_turn()
      ↓
  ┌──────────────────────────────────┐
  │      Cargar contexto            │
  │  Redis context + PG prefs       │
  │  Redis historial (15 msgs)      │
  │  PG citas existentes            │
  └──────────────────────────────────┘
      ↓
  ¿Handoff keywords? → handoff_service.trigger_handoff()
      ↓
  _build_messages()
  [system + contextos + history + user_message]
      ↓
  ┌──── LOOP (max 5 iters) ────────────────────┐
  │                                             │
  │  llm_router.ainvoke(messages, 13 tools)    │
  │        ↓                                   │
  │  ¿tool_calls?                              │
  │     SÍ:                                    │
  │       execute_tool(name, args, phone)       │
  │       append result → messages             │
  │       ¿short-circuit? → break             │
  │     NO:                                    │
  │       response_text = content              │
  │       break                                │
  │                                             │
  └─────────────────────────────────────────────┘
      ↓
  _clean_response() + _detect_action_hallucination()
      ↓
  asyncio.create_task(_background_post_processing())
      ↓
  return {response_text, rich_content, tools_used}
      ↓
webhook.py:
  sanitize_bot_response()
  whatsapp_client.send_message()
  [si imágenes] whatsapp_client.send_image() × N
```

### Flujo de búsqueda de propiedades

```
LLM decide llamar search_properties
      ↓
execute_tool("search_properties", {location, budget_max, ...}, phone)
      ↓
tools.search_properties(criteria, phone)
  ├── sanitize_criteria()
  ├── Normalizar: location, budget, bedrooms, operation_type
  ├── price_tier → get_budget_tiers() [si término vago]
  └── property_service.search_properties(criteria)
          └── PropertyRepository.search()   [PostgreSQL ILIKE query]
      ↓
  ¿Sin resultados?
    Fallback 1: budget_max +30%
    Fallback 2: sin filtro de presupuesto
    Si nada → "NO_RESULTS_ASK_MORE"
      ↓
  memory_manager.update_context_field(phone, "last_shown_properties", compressed)
      ↓
  format_property_list(properties)
      ↓
SHORT-CIRCUIT: response_text = tool_result (no segunda llamada LLM)
```

### Flujo de agendado

```
LLM decide llamar schedule_visit
  (tiene: property_id, date_str, time_str, client_name)
      ↓
[Guard]: property_id mismatch → corregir con selected_property_id
      ↓
execute_tool("schedule_visit", {...}, phone)
      ↓
tools.schedule_visit()
  ├── sanitize_property_id() + sanitize_date_input()
  ├── Validar formato ID (numérico o UUID)
  ├── property_service.get_property_details(property_id)
  ├── parse_spanish_datetime(date_str + time_str)
  ├── validate_future(parsed_dt, min_minutes=30)
  ├── UserRepository.get_by_phone(phone)
  ├── ¿Tiene nombre? Si no → pedir nombre al usuario
  └── appointment_service.create_appointment(user_id, prop_id, start_time)
          ├── _check_conflict()     [PostgreSQL]
          ├── calendar_service.check_availability()
          ├── calendar_service.create_visit_event()
          └── INSERT Appointment + commit
      ↓
format_appointment_confirmation(appointment)
  → "📅 *¡Cita Agendada!*\n...\n<!--CONFIRMED:2026-05-20 15:00-->"
      ↓
SHORT-CIRCUIT: "<!--CONFIRMED:" detectado → response_text = tool_result
      ↓
notification_service.visit_scheduled()   [dashboard notification]
```

### Estados de la conversación

```
          idle
          /  \
    qualify  search ←───────────────────────────────┐
         \      |                                    │
          \   view_property                          │
           \      |                                  │
            \   booking                              │
             \      |                                │
              \  completed ────────────────────────►─┘
               \
        human_assistance ← desde cualquier estado
```

---

## 9. Variables de Entorno Importantes para el Bot

| Variable | Uso |
|---|---|
| `OPENAI_API_KEY` | Clave API para GPT-4o-mini |
| `OPENAI_MODEL` | Modelo a usar (default: `gpt-4o-mini`) |
| `LLM_TIMEOUT_SECONDS` | Timeout para llamadas al LLM |
| `LLM_MAX_RETRIES` | Reintentos en error |
| `LLM_TEMPERATURE` | Temperatura del LLM |
| `LLM_MAX_TOKENS` | Máximo de tokens por respuesta |
| `REDIS_URL` | URL de Redis para memoria de sesión |
| `DATABASE_URL` | PostgreSQL |
| `WHATSAPP_PHONE_NUMBER_ID` | ID de número WhatsApp en Meta |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Token para verificar webhook Meta |
| `WHATSAPP_ACCESS_TOKEN` | Token Bearer para enviar mensajes |
| `API_BASE_URL` | URL pública de la API (para URLs de imágenes) |
| `GOOGLE_CALENDAR_*` | Credenciales Google Calendar |
| `RESET_PHONE_ON_STARTUP` | Teléfono de test que se resetea en cada deploy |

---

## 10. Guía de Modificación Rápida

| Si querés cambiar... | Modificar... |
|---|---|
| Personalidad / tono del bot | `SYSTEM_PROMPT` en `app/agents/prompts.py` |
| Agregar un nuevo tool | 1) Función async en `tools.py`, 2) Agregar a `TOOL_FUNCTIONS`, 3) Agregar definición en `TOOL_DEFINITIONS` en `prompts.py` |
| Cambiar el modelo LLM | `OPENAI_MODEL` en `.env` o `llm_router.py` |
| Cambiar qué criterios de búsqueda se soportan | `search_properties()` en `tools.py` + esquema en `TOOL_DEFINITIONS` |
| Cambiar formato de resultados de búsqueda | `format_property_list()` / `format_property()` en `tools.py` |
| Cambiar flujo de agendado | `schedule_visit()` en `tools.py` + instrucciones en `SYSTEM_PROMPT` |
| Cambiar ejemplos few-shot | Sección "Conversation Examples" en `SYSTEM_PROMPT` |
| Cambiar cuántos mensajes de historial se incluyen | `limit=15` en `get_recent_messages()` + `history[-10:]` en `format_messages_for_llm()` |
| Cambiar tiempo de expiración de la sesión | `CONTEXT_TTL = 86400` en `memory.py` y `STATE_TTL = 86400` en `state_machine.py` |
| Cambiar el máximo de tool calls por turno | `MAX_TOOL_CALLS = 5` en `RealEstateAgent` |
| Cambiar cómo se detecta handoff | `_detect_handoff_request()` keywords en `real_estate_agent.py` |
| Cambiar anti-alucinación | `_detect_action_hallucination()` y `HALLUCINATION_CHECKS` en `real_estate_agent.py` |
| Cambiar normalización de números argentinos | `format_phone_number()` en `webhook.py` |
| Cambiar cómo se extraen preferencias del texto | `extract_and_save_preferences()` en `memory.py` |

---

## 11. Bugs Identificados y Corregidos

Análisis de los archivos responsables del ~30% de fallos del bot. Los fixes fueron aplicados el 2026-05-13.

### Bug 1 — `app/utils/date_parser.py`: orden incorrecto en `_parse_time()` ✅ CORREGIDO

**Síntoma:** "quiero ir a las 8 de la mañana" agendaba la visita a las 10:00 en lugar de las 8:00.

**Causa:** El bloque `if "mañana" in user_text and "de la" in user_text` (fallback genérico → `return 10, 0`) aparecía **antes** del regex `a\s*las\s*(\d{1,2})\s*de\s*la\s*(mañana|tarde)` que lee la hora explícita. El fallback corto-circuitaba sin leer el dígito.

**Fix (líneas ~696-722):** El regex específico `"a las X de la mañana/tarde/noche"` se movió **antes** de los fallbacks genéricos. Los fallbacks ahora solo aplican si `not re.search(r'\d', user_text)` — es decir, solo cuando no hay ningún dígito de hora en el texto.

```python
# ANTES (orden incorrecto):
if "mañana" in user_text and "de la" in user_text:
    return 10, 0   # ← disparaba primero
...
match = re.search(r'a\s*las\s*(\d{1,2})...')  # ← nunca llegaba

# DESPUÉS (orden correcto):
match = re.search(r'a\s*las\s*(\d{1,2})\s*de\s*la\s*(mañana|tarde|noche)', user_text)
if match:
    ...  # ← lee la hora explícita primero
...
if "mañana" in user_text and ...:
    if not re.search(r'\d', user_text):  # ← solo si no hay hora explícita
        return 10, 0
```

---

### Bug 2 — `app/utils/sanitizer.py`: `sanitize_time_input()` destruye expresiones en español ✅ CORREGIDO

**Síntoma:** El usuario escribe "a las 3 de la tarde" y el bot vuelve a preguntar la hora porque recibe "3 a a" (basura).

**Causa:** El regex `r'[^\d:\sampm]'` solo permite dígitos, `:`, espacios y las letras literales `a`, `m`, `p`. Cualquier otro carácter —incluyendo `ñ`, `t`, `d`, `l`, `r`— se reemplaza por espacio. "de la tarde" → `" a "`.

**Fix (línea ~246):** Se reemplazó por `r'[^\w\s:áéíóúüñ]'` que preserva todos los caracteres de palabra (incluyendo Unicode/español) y solo elimina caracteres realmente peligrosos (`!`, `@`, `#`, etc.).

```python
# ANTES:
time_str = re.sub(r'[^\d:\sampm]', ' ', time_str)  # destruye español

# DESPUÉS:
time_str = re.sub(r'[^\w\s:áéíóúüñ]', ' ', time_str)  # preserva español
```

---

### Bug 3 — `app/utils/sanitizer.py`: validación del enum `property_type` nunca ejecutaba ✅ CORREGIDO

**Síntoma:** El LLM podía pasar valores inventados como `"casa grande"` o `"chalet"` como `property_type`, que llegaban sin validar a la query de base de datos.

**Causa:** La validación contra el enum `ALLOWED_PROPERTY_TYPES` estaba en un bloque `elif key == "property_type":` que **nunca se alcanzaba**, porque `property_type` siempre es un `str` y el branch `if isinstance(value, str):` lo capturaba primero.

**Fix (líneas ~84-120):** La validación del enum se movió **dentro** del branch `isinstance(value, str)`, después del saneamiento de SQL injection. El `elif key == "property_type":` muerto fue eliminado.

```python
# ANTES (dead code):
if isinstance(value, str):
    ...  # ← captura property_type acá
elif key == "property_type":
    ...  # ← NUNCA llega acá

# DESPUÉS (funcional):
if isinstance(value, str):
    ...  # saneamiento SQL
    if key == "property_type":
        ALLOWED = {"casa", "departamento", "terreno", "oficina", "local", "galpon"}
        if value not in ALLOWED:
            continue  # ← ahora sí funciona
```

---

### Issues de diseño identificados (sin fix aplicado)

Estos no son bugs sino decisiones de diseño que contribuyen a fallos intermitentes. Se documentan para referencia futura.

| # | Archivo | Issue | Impacto |
|---|---|---|---|
| D1 | `real_estate_agent.py` | `_user_wants_search` incluye "departamento"/"casa" como triggers → falsos positivos que fuerzan búsqueda no deseada | Medio |
| D2 | `real_estate_agent.py` | `<last_results>` mapping solo cubre "opción N" — referencias naturales ("el segundo", "ese departamento") no resuelven | Medio |
| D3 | `agents/prompts.py` | `get_system_prompt()` inyecta contexto de usuario como una sola línea al final del prompt (baja peso de atención) | Bajo-medio |
| D4 | `agents/prompts.py` | `format_messages_for_llm()` es dead code — el agente usa `_build_messages()` directamente | Bajo |
| D5 | `utils/date_parser.py` | `_split_date_time` definida dos veces (líneas 29 y 291); la segunda sobreescribe silenciosamente la primera | Bajo |

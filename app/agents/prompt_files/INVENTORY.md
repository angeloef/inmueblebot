# Prompt Inventory — SYSTEM_PROMPT Section Audit

Source: `app/agents/prompts.py` lines 8-148
Prompt files: `app/agents/prompt_files/`

## Shared — Siempre presente en todo turno

| Sección | Líneas | Destino | Notas |
|---------|--------|---------|-------|
| `# Personalidad` | 8-9 | `shared/persona.md` | Tono rioplatense, qué hace el bot |
| `# Colaboración` | 11-18 | `shared/persona.md` | Reglas de interacción, "no preguntar de nuevo", Preguntá de a una cosa |
| `# Criterios de Éxito` | 40-41 | `shared/persona.md` | Definición de éxito |
| `# Condiciones de Parada` | 43-44 | `shared/condiciones.md` | "¿Ya puedo responder?" |
| `# Alcance — Qué hago y qué no hago` | 46-50 | `shared/alcance.md` | Límites del bot, redirección |

## Dinámico — Ya inyectado por _build_messages()

| Sección | Líneas | Origen actual | Manejado por |
|---------|--------|---------------|--------------|
| `{company_name}` | 22-24, 49 | `get_system_prompt()` resuelve | `get_system_prompt()` |
| `### User Context` | n/a | `get_system_prompt()` apéndice | `get_system_prompt()` |
| `### ETAPA: X` | n/a | `_build_messages()` | Fase 3+4 |
| `### TONO: Y` | n/a | `_build_messages()` + SENTIMENT_KEYWORDS | Fase 3+4 |
| `### ACTIVE PROPERTY CONTEXT` | n/a | `_build_messages()` | Fase 3+4 |
| `### PENDING SCHEDULING INFO` | n/a | `_build_messages()` | Fase 3+4 |
| `### USUARIO RECURRENTE` | n/a | `_build_messages()` | Fase 3+4 |

## Por Capacidad

### CAP greeting — Saludo Inicial (SALUDO_INICIAL)

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# Saludo Inicial` | 20-24 | Reglas de saludo por hora + ejemplos |

Incluye: lógica de saludo (6-12 buenos días, 12-20 buenas tardes, 20-6 buenas noches). NO incluir en otros prompts.

### CAP search — Búsqueda de propiedades (BUSQUEDA)

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# Formato de Respuestas` → líneas search | 27-30 (search results), 35 (sin resultados) | Formato de resultados, cierre de resultados |
| `# Rangos y Alternativas` | 65-66 | "3 o 4 dormitorios" → usar número más bajo |
| `# property_type en search_properties — REGLA ESTRICTA` | 68-81 | Mapeo de tipos a enum, ejemplos de llamadas |
| `# Ambigüedad de operación (alquiler vs venta)` | 83-84 | Preguntar antes si no especifica |
| `# Resultados vacíos — señal NO_RESULTS_ASK_MORE` | 86-91 | Qué hacer cuando no hay resultados |

### CAP detail — Detalle de propiedad (DETALLE_PROPIEDAD)

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# Formato de Respuestas` → línea detail | 31 | "Mirá, esta es [título]:" + $[Precio] \| ... |
| `# Contexto de Propiedad Activa` | 37-38 | Usar propiedad activa para "esa", "fotos", etc. |
| `# Formato de Respuestas` → línea multi-intent | 32 | Si pide fotos + visita simultáneamente |

### CAP schedule — Agendamiento de visitas (AGENDANDO)

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# Flujo de Agendamiento` | 52-58 | Pasos 1-5 completos, domingo, alternativas |
| `# Formato de Respuestas` → confirmación | 33 | "Cita Agendada" + Fecha \| Hora \| Título |
| `# Formato de Respuestas` → línea multi-intent | 32 | Fotos + visita en mismo turno |

### CAP appointment — Gestión de turnos (GESTION_TURNOS)

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# Reprogramación y Cancelación` | 60-63 | get_my_appointments → UUID → reschedule/cancel |

### CAP faq — Preguntas frecuentes (CONSULTA)

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# Formato de Respuestas` → FAQ | 34 | Responder + ofrecer ayuda |
| `# FAQ y Handoff` | 93-94 | get_faq_answer + request_human_assistance |

### CAP contact — Contacto humano

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# FAQ y Handoff` (contact part) | 93-94 | request_human_assistance SOLO si pide persona |

### CAP general / CAP handoff — Fallback / Handoff

| Sección | Líneas | Comentarios |
|---------|--------|-------------|
| `# Alcance` (redirección) | 46-50 | Usar para mensajes fuera de alcance |
| `# FAQ y Handoff` (handoff part) | 93-94 | request_human_assistance |

## Ejemplos de Conversación

| Ejemplo | Líneas | Capacidad | Descripción |
|---------|--------|-----------|-------------|
| Ejemplo 1: Búsqueda | 98-104 | search | Búsqueda + resultados formateados |
| Ejemplo 2: Detalles y visita | 106-121 | schedule | Detalle → interés → agendar completo |
| Ejemplo 3: FAQ | 123-127 | faq | Pregunta → get_faq_answer → respuesta |
| Ejemplo 4: Domingo | 129-140 | schedule | Intento domingo → rechazo → alternativa |
| Ejemplo 5: Sin resultados | 142-147 | search | Sin resultados → alternativas |

## Resumen de archivos a crear

| Archivo | Contenido (líneas fuente) |
|---------|--------------------------|
| `shared/persona.md` | 8-18, 40-41 |
| `shared/alcance.md` | 46-50 |
| `shared/condiciones.md` | 43-44 |
| `capabilities/greeting.md` | 20-24 |
| `capabilities/search.md` | 27-30, 35, 65-66, 68-81, 83-84, 86-91 |
| `capabilities/detail.md` | 31, 37-38 |
| `capabilities/schedule.md` | 32 (partial), 33, 52-58 |
| `capabilities/appointment.md` | 60-63 |
| `capabilities/faq.md` | 34, 93-94 |
| `examples/search.md` | 98-104, 142-147 |
| `examples/schedule.md` | 106-121, 129-140 |
| `examples/faq.md` | 123-127 |

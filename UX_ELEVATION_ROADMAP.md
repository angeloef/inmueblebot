# InmuebleBot — UX Elevation Roadmap

> Plan para transformar InmuebleBot de un buscador funcional a un asistente
> inmobiliario inteligente, proactivo y personal.
>
> **Principio rector:** El bot debe sentirse como un agente de bienes raíces
> real — que recuerda, anticipa, sugiere y se adapta. No como un motor de
> búsqueda con voz amigable.
>
> **Prohibido:** WhatsApp interactive buttons/list messages. Todo es texto plano.

---

## Tabla de Contenidos

1. [Arquitectura General del Plan](#1-arquitectura-general-del-plan)
2. [Sprint 20 — Quick Wins](#2-sprint-20--quick-wins)
3. [Sprint 21 — Riqueza Conversacional](#3-sprint-21--riqueza-conversacional)
4. [Sprint 22 — Personalización](#4-sprint-22--personalización)
5. [Sprint 23 — Inteligencia Proactiva](#5-sprint-23--inteligencia-proactiva)
6. [Apéndice A: Budget Inference — Diseño Detallado](#apéndice-a-budget-inference--diseño-detallado)
7. [Apéndice B: Mapa de Archivos](#apéndice-b-mapa-de-archivos)

---

## 1. Arquitectura General del Plan

```
Filosofía: Reactivo → Proactivo
           Texto plano → Texto rico con estructura
           Sin estado → Perfil acumulativo
           Buscador → Asesor
           Genérico → Adaptado al contexto

Capas de inteligencia (de abajo arriba):

  🧠 Capa 4: Proactiva         — Recordatorios, sugerencias, nurturing
  ─────────────────────────────────────────────
  👤 Capa 3: Personalizada     — Perfil cross-session, lenguaje preferido
  ─────────────────────────────────────────────
  💬 Capa 2: Conversacional    — Comparaciones, calificación, preguntas
  ─────────────────────────────────────────────
  ⚡ Capa 1: Funcional mejorada — Sin resultados, presupuesto inferido
```

---

## 2. Sprint 20 — Quick Wins

> Estimación: **1-2 días**
> Impacto: Alto con esfuerzo mínimo

---

### 2.A — Recuperación Proactiva de "Sin Resultados"

**Problema:** Cuando `search_properties` retorna 0 resultados, el bot dice
"no encontré" y la conversación muere.

**Solución:** El tool `search_properties`, al recibir 0 resultados, ejecuta
automáticamente búsquedas de respaldo con criterios relajados y devuelve
alternativas concretas.

**UX deseado:**
```
User: "departamentos en posadas hasta 50k"
Bot: "En Posadas no encontré departamentos en alquiler hasta $50,000.
     Pero tengo algunas ideas:

     🔹 En Oberá hay 3 departamentos similares desde $45,000
        -> querés verlos?
     🔹 En Posadas tengo 2 opciones un poco más arriba,
        a $65,000 y $72,000
     🔹 O si preferís, hay casas en Posadas desde $55,000

     ¿Qué te parece?"
```

**Implementación:**

```
Archivo: app/agents/tools.py — función search_properties()

1. Ejecutar búsqueda principal con criterios exactos
2. Si resultados > 0 → retornar normalmente
3. Si resultados == 0 → ejecutar FALLOS:
   a) Fallback 1: Misma ubicación, +30% budget_max, property_type alternativo
   b) Fallback 2: Ubicación vecina (Oberá como fallback de Posadas),
      mismo budget
   c) Fallback 3: Solo operation_type + property_type, sin location
4. Devolver mensaje formateado con 3 alternativas
```

**Estrategias de fallback concretas:**

| Prioridad | Relax | Ejemplo |
|-----------|-------|---------|
| 1 | budget_max × 1.3 | $50k → $65k |
| 2 | Misma zona, tipo distinto | departamento → casa |
| 3 | Zona vecina, mismo tipo | Posadas → Oberá |
| 4 | Solo tipo + operación | cualquier zona |
| 5 | Todo disponible | sin filtros |

**Archivos a modificar:** `app/agents/tools.py`

---

### 2.B — Comparación Inteligente de Propiedades

**Problema:** Usuarios piden comparar propiedades ("cuál es mejor?") pero el
bot solo puede mostrar detalles individuales.

**Solución:** Nueva tool `compare_properties(property_ids)` que fetchea
múltiples propiedades y las formatea como tabla comparativa.

**UX deseado:**
```
User: "compara la casa de centro y el duplex de belvedere"
Bot: "¡Claro! Acá te hago la comparación rápida:

  Característica     | Casa Centro      | Dúplex Moderno
  -------------------|------------------|-----------------
  💰 Precio          | $180,000 venta   | $280,000 venta
  📐 Tamaño          | 200m²            | 140m²
  🛏️ Dormitorios     | 4 hab            | 3 hab
  🚗 Cochera         | Sí               | No
  📍 Zona            | Oberá Centro     | Belvedere
  🔑 Ideal para      | Familia grande   | Pareja/profesional

  La Casa Centro es mejor si tenés familia y buscás espacio.
  El Dúplex es ideal si preferís algo más moderno y céntrico.
  ¿Cuál te llama más la atención?"
```

**Implementación:**

1. **Nueva función** `compare_properties(property_ids: List[str])` en tools.py
2. Fetchea cada propiedad por ID
3. Extrae campos: title, price, type, location, bedrooms, bathrooms, area_m2,
   description, extra_data
4. Formatea como tabla markdown con columnas por propiedad
5. Devuelve el string formateado
6. Registrar en `TOOL_FUNCTIONS` y `TOOL_DEFINITIONS`

**Formato de tabla:**
```
  {campo:15s} | {prop1:20s} | {prop2:20s}
  {"-"*15} | {"-"*20} | {"-"*20}
  💰 Precio  | {precio1:20s} | {precio2:20s}
  ...
```

**Archivos nuevos:** Ninguno
**Archivos a modificar:** `app/agents/tools.py`, `app/agents/prompts.py`

---

### 2.C — Consulta de Tipo en Búsquedas Ambiguas

**Problema:** Cuando el usuario dice solo "departamento" o "casa", el bot
asume "alquiler" por defecto (REGLA 6) pero no confirma, lo que puede
llevar a resultados inesperados.

**Solución:** Si el usuario da un criterio muy vago (solo property_type sin
operation_type, ubicación ni presupuesto), el bot pregunta antes de buscar.

**UX deseado:**
```
User: "departamento"
Bot: "¿Lo querés para alquilar o comprar? Y ¿en qué zona?"
```
```
User: "casa"
Bot: "¿Buscás alquilar o comprar? ¿En qué ciudad?"
```

**Implementación:**

Añadir a REGLA 6 (o crear REGLA 7):
```
**REGLA 7 - BUSQUEDAS AMBIGUAS:** Si el usuario solo da 1 criterio vago
(ej. solo "departamento" sin ubicación ni presupuesto ni operación),
NO llames search_properties todavía. Preguntá primero por operación
(alquiler/compra) y ubicación. Si da 2+ criterios específicos, buscá
directamente.
```

**Archivos a modificar:** `app/agents/prompts.py`

---

### 2.D — Saludo Personalizado para Usuarios Recurrentes

**Problema:** Cada conversación empieza igual, aunque el usuario tenga
historial. Se pierde la sensación de continuidad.

**Solución:** Si el usuario tiene contexto guardado en Redis (conversación
anterior), el bot lo reconoce y saluda con referencia a la última visita.

**UX deseado:**
```
Bot: "¡Bienvenido de nuevo! La última vez viste la Casa Centro 4 hab
      en Oberá. ¿Seguís interesado en propiedades similares o arrancamos
      de nuevo?"
```

**Implementación:**

En `real_estate_agent.py:process_turn()`, antes de construir mensajes:

```python
# Detectar usuario recurrente
last_context = merged_context
is_returning = (
    last_context.get("selected_property_id") or
    last_context.get("last_shown_properties") or
    last_context.get("conversation_stage") != "new"
)
if is_returning and not history:
    # Inyectar saludo personalizado como mensaje del sistema
    user_context["is_returning"] = True
    last_prop = last_context.get("selected_property_id", "propiedades")
    user_context["last_reference"] = last_prop
```

En `prompts.py`, añadir al `get_system_prompt()`:

```python
if user_context.get("is_returning"):
    prompt += (
        "\n\n### USUARIO RECURRENTE\n"
        "Este usuario ya ha conversado antes. "
        f"Su última referencia fue: {user_context.get('last_reference', 'propiedades')}\n"
        "Saludalo con: '¡Bienvenido de nuevo! La última vez viste [referencia]...'\n"
    )
```

**Archivos a modificar:** `app/agents/prompts.py`, `app/agents/real_estate_agent.py`

---

### 2.E — Budget Inference de Términos Vagas (Ver Apéndice A)

**Problema:** Usuarios dicen "económico", "normal", "de lujo" sin dar
números. El bot no traduce estas palabras a rangos de precio.

**Solución:** Sistema de 3 tiers calculados dinámicamente desde los
precios reales en la base de datos, más mapeo de frases clave.

**Implementación detallada:** Ver [Apéndice A](#apéndice-a-budget-inference--diseño-detallado).

**Archivos nuevos:** `app/agents/budget_tiers.py`
**Archivos a modificar:** `app/agents/prompts.py` (REGLA 6)

---

## 3. Sprint 21 — Riqueza Conversacional

> Estimación: **2-3 días**
> Capa 2 del plan: el bot empieza a llevar la iniciativa.

---

### 3.A — Recordatorios de Cita y Seguimiento

**Problema:** Después de agendar una visita, el bot se queda en silencio.
No hay recordatorios, no hay seguimiento post-visita.

**Solución:** Sistema de 3 touchpoints automáticos por cita agendada.

**UX deseado:**

```
24h antes:
  "📅 Recordatorio: mañana a las 15hs tenés tu visita a Casa Centro (ID:1).
   ¿Necesitás la dirección exacta o algo más?"

2h antes:
  "⏰ Tu visita a Casa Centro es en 2 horas. Cualquier cambio, avisame!"

Post-visita (+2h):
  "¿Qué tal te fue en la visita a Casa Centro? ¿Te gustó la propiedad?
   ¿Necesitás más información?"

7 días sin actividad:
  "¿Seguís buscando propiedad? Agregamos 2 nuevas en Oberá esta semana."
```

**Implementación:**

1. **Revivir `app/tasks/reminders.py`** — Convertir a async compatible
   (actualmente usa `await` en funciones sync de Celery)

2. **Cronjobs dinámicos** — Cuando se crea una cita, crear cronjobs:
   ```
   cronjob action=create
     schedule="2026-05-15T14:00:00"  # 24h antes
     prompt="Enviar recordatorio a {phone}: ...
   ```

3. **Cron de mantenimiento diario** — Job que corre cada 6h, consulta DB
   por citas próximas y envía recordatorios si no se han enviado aún.

**Archivos a modificar:** `app/tasks/reminders.py`, `app/services/appointment_service.py`

---

### 3.B — Flujo de Calificación Interactivo

**Problema:** Leads nuevos reciben el mismo tratamiento que leads
recurrentes. El bot no califica ni recolecta información estratégicamente.

**Solución:** Si el número de teléfono no tiene historial en Redis, el bot
activa un mini-flujo de calificación de 2-3 preguntas antes de buscar.

**UX deseado:**
```
User (nuevo): "hola"
Bot: "¡Hola! Soy el asistente virtual de [Inmobiliaria].
      ¿Es la primera vez que consultás? Te puedo ayudar a encontrar
      propiedades en alquiler o venta, agendar visitas, o responder
      preguntas sobre el proceso.

      ¿Qué tipo de búsqueda te trae?"

User: "quiero un depto"
Bot: "Bien! ¿Lo querés para alquilar o comprar? ¿Y en qué zona?"

User: "alquiler, oberá centro"
Bot: "Perfecto. ¿Cuál sería tu presupuesto máximo por mes?"
```

**Implementación:**

1. Detectar "nuevo lead" en `process_turn()` (sin historial de mensajes)
2. Activar `intent_classifier` más agresivo para detectar intención
3. Inyectar en system prompt una instrucción extra:
   ```
   ### NUEVO CONTACTO
   Este usuario NO tiene historial. Es primera vez que habla con nosotros.
   - Preguntale nombre al inicio si no lo dio
   - Recolectá: ubicación, tipo de operación, presupuesto
   - Si responde TODO de una, buscá directamente
   ```
4. El LLM maneja el flujo naturalmente

**Archivos a modificar:** `app/agents/real_estate_agent.py`, `app/agents/prompts.py`

---

## 4. Sprint 22 — Personalización

> Estimación: **2-3 días**
> El bot empieza a recordar quién sos entre sesiones.

---

### 4.A — Perfil de Usuario Cross-Session

**Problema:** El perfil de usuario existe en PostgreSQL pero nunca se
inyecta en el contexto del LLM de forma rica.

**Solución:** Acumular señales del usuario en cada interacción e inyectar
un resumen de perfil en cada turno.

**Señales a recolectar:**

| Señal | Dónde se guarda | Cuándo se actualiza |
|-------|----------------|---------------------|
| Zonas preferidas | `extra_data['preferred_zones']` | Cada search_properties |
| Rango de presupuesto | `extra_data['budget_range']` | Cuando busca o menciona precio |
| Tipos vistos | `extra_data['viewed_property_types']` | Cada get_property_details |
| IDs de propiedades rechazadas | `extra_data['rejected_property_ids']` | Cuando dice "no" después de ver |
| IDs de propiedades interesantes | `extra_data['liked_property_ids']` | Cuando agenda o pide detalles |
| Patrón horario | `extra_data['active_hours']` | Timestamps de mensajes |
| Total de interacciones | `extra_data['total_messages']` | Cada mensaje |

**Perfil inyectado en cada turno:**
```
### PERFIL DEL USUARIO
- Tipo de propiedad preferido: departamento (visto 5 veces, agendado 2)
- Zonas: Oberá Centro (3 búsquedas)
- Presupuesto típico: $80k-$120k
- Rechazó: ID:7 (casa, muy cara), ID:12 (departamento, sin cochera)
- Interacción #: 12
```

**Implementación:**

1. Extender `MemoryManager.update_user_preferences()` para aceptar señales
2. En `process_turn()`, después de cada tool call, extraer señales:
   - `search_properties` → guardar criteria.location, criteria.budget
   - `get_property_details` → guardar property_id en "vistos"
   - Mensaje del usuario contiene "no" + propiedad activa → "rechazado"
3. En `_build_messages()`, cargar perfil desde PostgreSQL e inyectar

**Archivos a modificar:** `app/agents/real_estate_agent.py`, `app/core/memory.py`

---

### 4.B — Detección de Idioma Portugués

**Problema:** Paraguay (mercado target) usa portugués/guaraní. El bot solo
responde en español.

**Solución:** Detectar portugués en el primer mensaje y cambiar idioma de
respuesta automáticamente.

**Implementación:**

1. En `webhook.py:process_messages()`, detectar portugués con palabras
   clave: "quero", "gostaria", "você", "tem", "para alugar", "preciso",
   "obrigado", "bom dia", "tarde", "noite"
2. Guardar `user_lang: "pt"` en el contexto Redis
3. En `_build_messages()`, si user_lang=="pt", añadir al system prompt:
   ```
   IMPORTANTE: Este usuario habla portugués.
   Respondé SIEMPRE en portugués brasileiro.
   Mantené el mismo tono conversacional pero en PT-BR.
   ```
4. GPT-4o-mini maneja ambos idiomas nativamente

**Archivos a modificar:** `app/api/routes/webhook.py`, `app/agents/real_estate_agent.py`,
`app/agents/prompts.py`

---

## 5. Sprint 23 — Inteligencia Proactiva

> Estimación: **3-4 días**
> El bot actúa como asesor, no como buscador.

---

### 5.A — Matching Guiado Multi-Turno

**Problema:** El usuario muchas veces no sabe lo que quiere. El bot busca
con el primer criterio que escucha, llevando a frustración.

**Solución:** El bot recolecta 3+ criterios antes de buscar, haciendo
preguntas estratégicas una por una.

**UX deseado:**
```
Bot: "Contame qué estás buscando y te ayudo a encontrar
      la propiedad perfecta. ¿Para cuántas personas es?"
User: "Para mí solo"
Bot: "Bien. ¿Buscás alquilar o comprar? ¿Y te sirve un
      departamento de 1-2 ambientes o un poco más grande?"
User: "Alquilar, 2 ambientes chico"
Bot: "Perfecto. ¿En qué zona y hasta cuánto por mes?"
User: "Oberá centro, hasta 120mil"
Bot: "¡Dale! Buscando..."
```

**Implementación:**

1. El estado `qualifying` de la state machine ya existe pero apenas se usa.
   El flujo sería:
   - `idle` → usuario da criterio incompleto → `qualifying`
   - En `qualifying`, el bot pregunta 1 cosa a la vez
   - Acumula criterios en `pending_search_criteria`
   - Cuando tiene ≥3 criterios → salta a `searching` y ejecuta búsqueda

2. Modificar prompt para que el LLM:
   - Detecte cuándo el usuario da info insuficiente
   - Pregunte 1 cosa por turno
   - No busque hasta tener ubicación + tipo + operación + presupuesto

3. En el system prompt, añadir:
   ```
   ### MATCHING GUIADO
   Si el usuario NO te dio al menos 3 de estos criterios, NO busques todavía:
   [x] Ubicación (zona/ciudad)
   [x] Tipo de operación (alquiler/compra)
   [x] Tipo de propiedad (casa/departamento)
   [x] Presupuesto
   Preguntá de a UN criterio por vez.
   ```

**Archivos a modificar:** `app/agents/prompts.py`

---

### 5.B — Dashboard de Handoffs

**Problema:** Cuando un usuario pide un agente humano, el handoff genera un
resumen que se loggea pero nunca llega a nadie en tiempo real.

**Solución:** Nuevo tab "Handoffs" en el Dashboard + notificación opcional.

**UX Dashboard:**
```
┌───────────────────────────────────────────────────────┐
│  Handoffs                                              │
│  ┌──────────────────────────────────────────────────┐ │
│  │ 📞 +54 3754...  Juan Pérez  ·  hace 5min         │ │
│  │ 🔴 Pendiente   Motivo: consulta compleja         │ │
│  │ 📝 Quiere comprar una casa en Oberá centro...    │ │
│  │ [📱 Contactar por WhatsApp]                       │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ 📞 +54 3764...  María García  ·  hace 2h         │ │
│  │ 🟡 Contactado   Motivo: solicitud de tasación    │ │
│  │ [📱 Contactar]  [✅ Marcar resuelto]              │ │
│  └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

**Implementación:**

1. **Backend:** Nuevo endpoint `GET /admin/handoffs` que lee de
   `User.extra_data['handoff_*']` donde `handoff_requested_at` no es null
2. **Modelo:** Opcionalmente crear tabla `handoffs` para mejor queryeo
3. **Dashboard:** Nuevo componente `Handoffs.jsx` + nav item
4. **Notificación:** Opcionalmente enviar WhatsApp al admin cuando se
   dispara un handoff

**Archivos nuevos:** `dashboard/src/Handoffs.jsx`
**Archivos a modificar:** `app/api/routes/admin.py`, `app/services/handoff_service.py`

---

### 5.C — Comparación Inteligente (Profundización)

**Problema:** El bot compara propiedades pero no da recomendación ("cuál es
mejor para vos").

**Solución:** Después de la tabla comparativa, el LLM debe dar una
recomendación personalizada basada en el perfil del usuario y la
conversación.

**UX deseado:**
```
Bot: "...(tabla comparativa)...

      👉 Para tu caso (buscás algo económico para vos solo):
         El Departamento 2 ambientes es mejor opción porque:
         - Es más chico = más barato de mantener
         - Está en el centro = cerca de todo
         - $95,000 está dentro de tu presupuesto

      ¿Querés verlo en detalle o agendar una visita?"
```

**Implementación:** Esto es puramente prompt — el LLM ya tiene los datos
de la tabla + el perfil del usuario. Solo necesita instrucciones claras
para dar una opinión fundamentada.

**Archivos a modificar:** `app/agents/prompts.py` — añadir instrucción en
la tool definition de `compare_properties`.

---

## Apéndice A: Budget Inference — Diseño Detallado

### A.1 — El Problema

Los usuarios describen presupuestos con palabras vagas: "económico",
"normal", "de lujo". El bot necesita traducir estas palabras a rangos
de precio concretos para pasarlos a `search_properties(budget_min=X, budget_max=Y)`.

### A.2 — La Solución: Tiers Dinámicos desde la DB

En lugar de valores hardcodeados, los tiers se calculan desde los precios
reales de propiedades en la base de datos usando **percentiles**.

```
Precios actuales en DB (19 propiedades):
  $45k, $65k, $75k, $85k, $85k, $95k, $95k, $95k, $95k,
  $120k, $120k, $120k, $150k, $150k, $180k, $180k, $250k,
  $250k, $350k, $465k, $500k

P33 (percentil 33) = $95,000
P66 (percentil 66) = $180,000

Tiers resultantes:
  Low:    $0        - $95,000   (económico, barato, accesible)
  Medium: $95,001   - $180,000  (normal, estándar, moderado)
  High:   $180,001+             (lujo, premium, caro, exclusivo)
```

### A.3 — Algoritmo de Cálculo

```python
def calculate_budget_tiers() -> dict:
    """
    Consulta DB, obtiene todos los precios, calcula percentiles 33 y 66.
    Retorna dict con los límites de cada tier.
    """
    # 1. Query: SELECT price FROM properties WHERE status = 'available'
    # 2. Sort prices ascending
    # 3. Calculate P33 and P66
    #    p = (len(prices) - 1) * percentile / 100
    #    Interpolación lineal entre floor(p) y ceil(p)
    # 4. Return {"low_max": P33, "med_max": P66}
```

### A.4 — Mapa de Términos a Parámetros

| El usuario dice | Parámetros que se pasan a search_properties |
|----------------|---------------------------------------------|
| "económico", "barato", "accesible", "econo" | `budget_max=P33, sort_by="price_asc"` |
| "normal", "estándar", "moderado", "standard" | `budget_min=P33+1, budget_max=P66` |
| "lujo", "premium", "caro", "exclusivo" | `budget_min=P66+1` |
| "para estudiantes" | `property_type="departamento", budget_max=P33` |
| "para familia", "familiar" | `bedrooms>=3` |
| "casa grande" | `property_type="casa", bedrooms>=4` |
| "departamento chico", "monoambiente" | `property_type="departamento", bedrooms<=1` |

### A.5 — Implementación

**Nuevo archivo:** `app/agents/budget_tiers.py`

```python
"""
Cálculo dinámico de tiers de presupuesto desde la DB.
Los límites se recalculan cada vez (o se cachean con TTL).
"""
from app.db.session import async_session_factory
from sqlalchemy import select, func
import math


async def get_budget_tiers() -> dict:
    """
    Calcula P33 y P66 de todos los precios de propiedades disponibles.

    Returns:
        {"low_max": int, "med_max": int}
        low_max = P33 (máximo del tier económico)
        med_max = P66 (máximo del tier normal)
    """
    async with async_session_factory() as session:
        from app.db.models import Property
        result = await session.execute(
            select(Property.price)
            .where(Property.status == "available")
            .order_by(Property.price)
        )
        prices = [row[0] for row in result.fetchall()]

    if not prices or len(prices) < 3:
        # Fallback seguro si hay pocos datos
        return {"low_max": 100000, "med_max": 250000}

    def percentile(data, pct):
        k = (len(data) - 1) * pct / 100.0
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return int(data[f] * (c - k) + data[c] * (k - f))

    return {
        "low_max": percentile(prices, 33.33),
        "med_max": percentile(prices, 66.67),
        "min_price": prices[0],
        "max_price": prices[-1],
        "total_properties": len(prices),
    }
```

**En tools.py:search_properties():**

```python
# Después de sanitizar criteria, antes de llamar al service
if criteria.get("economico") or criteria.get("barato") or criteria.get("accesible"):
    tiers = await get_budget_tiers()
    search_criteria["budget_max"] = tiers["low_max"]
    search_criteria["sort_by"] = "price_asc"
elif criteria.get("normal") or criteria.get("estandar") or criteria.get("moderado"):
    tiers = await get_budget_tiers()
    search_criteria["budget_min"] = tiers["low_max"] + 1
    search_criteria["budget_max"] = tiers["med_max"]
elif criteria.get("lujo") or criteria.get("premium") or criteria.get("caro"):
    tiers = await get_budget_tiers()
    search_criteria["budget_min"] = tiers["med_max"] + 1
```

> **Nota:** La implementación ideal es que el LLM ya no pase términos
> vagos como `budget_max`, sino que pase `price_tier="economico"` y el
> tool haga la traducción. Esto requiere actualizar la tool definition
> en `prompts.py` para que el LLM tenga `price_tier` como parámetro.

### A.6 — Actualización de Tool Definition

En `prompts.py`, añadir a `search_properties`:

```python
{
    "name": "price_tier",
    "type": "string",
    "enum": ["economico", "normal", "premium", None],
    "description": (
        "Tier de precio cuando el usuario usa terminos vagos. "
        "'economico' = barato/accesible, "
        "'normal' = precio medio/estandar, "
        "'premium' = caro/lujo/exclusivo. "
        "Si el usuario dio un numero concreto, USA budget_max/budget_min en vez de esto."
    ),
}
```

Cuando `price_tier` se pasa, el tool hace la conversión a números
usando `get_budget_tiers()`.

---

## Apéndice B: Mapa de Archivos

### Archivos a crear

| Archivo | Sprint | Propósito |
|---------|--------|-----------|
| `app/agents/budget_tiers.py` | 20 | Cálculo de percentiles desde DB |
| `dashboard/src/Handoffs.jsx` | 23 | Tab de handoffs en el dashboard |

### Archivos a modificar

| Archivo | Sprint | Cambio |
|---------|--------|--------|
| `app/agents/tools.py` | 20, 23 | `search_properties` con fallbacks (A), `compare_properties` nuevo (B), budget_tier lookup (E) |
| `app/agents/prompts.py` | 20, 21, 22, 23 | REGLA 7 (C), returning user (D), qualifying flow, portugués, matching guiado |
| `app/agents/real_estate_agent.py` | 20, 21, 22 | Returning user detection (D), nuevo lead flow (3.B), perfil cross-session (4.A), portugués (4.B) |
| `app/core/memory.py` | 22 | Señales de perfil: rejected_ids, liked_ids, search_history |
| `app/api/routes/webhook.py` | 22 | Detección de portugués al inicio |
| `app/services/handoff_service.py` | 23 | Persistir handoffs, notificar admin |
| `app/api/routes/admin.py` | 23 | Endpoint GET /admin/handoffs |
| `app/tasks/reminders.py` | 21 | Revivir con async wrapper |
| `app/services/appointment_service.py` | 21 | Disparar cronjobs al crear cita |
| `dashboard/src/App.jsx` | 23 | Ruta para Handoffs |
| `dashboard/src/Shell.jsx` | 23 | Nav item para Handoffs |

---

## Resumen de Impacto

| Sprint | Característica | Esfuerzo | Impacto UX |
|--------|---------------|----------|------------|
| **20A** | No-results recovery | ⭐ | 🔥🔥🔥 |
| **20B** | Comparación propiedades | ⭐⭐ | 🔥🔥🔥 |
| **20C** | Consulta ambigua | ⭐ | 🔥🔥 |
| **20D** | Saludo recurrente | ⭐ | 🔥🔥 |
| **20E** | Budget inference | ⭐⭐ | 🔥🔥🔥 |
| **21A** | Recordatorios cita | ⭐⭐ | 🔥🔥🔥 |
| **21B** | Calificación leads | ⭐⭐ | 🔥🔥🔥 |
| **22A** | Perfil cross-session | ⭐⭐⭐ | 🔥🔥🔥🔥 |
| **22B** | Portugués | ⭐ | 🔥🔥 |
| **23A** | Matching guiado | ⭐⭐ | 🔥🔥🔥🔥 |
| **23B** | Dashboard handoffs | ⭐⭐ | 🔥🔥🔥 |
| **23C** | Recomendación en comparación | ⭐ | 🔥🔥🔥 |

---

## Quick-Start

Para arrancar **Sprint 20 ahora**:

```bash
# 1. Budget tiers module
touch app/agents/budget_tiers.py

# 2. Modify search_properties in tools.py
#    Añadir fallbacks + budget inference

# 3. Update prompts.py with REGLA 7
#    Añadir price_tier a tool definition

# 4. Update real_estate_agent.py
#    Detectar returning user en process_turn()

# 5. Test con WhatsApp
curl -X POST -H "x-api-key: your-secure-admin-key-here" \
  "https://inmueblebot-api.onrender.com/admin/users/5493754455340/reset"

# Enviar mensaje de prueba como "quiero un depto economico"
```

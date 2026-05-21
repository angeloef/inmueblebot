# InmuebleBot — Selling Funnel Framework v1.0

> **In-Person Demo → Free Trial → Full Onboarding**
> Modelo B2B para el mercado inmobiliario de Misiones, Argentina
> Mayo 2026 — Basado en: research interno + benchmarks SaaS + casos de estudio

---

## Tabla de Contenidos

1. [Filosofía del Funnel](#1-filosofía-del-funnel)
2. [Módulo 0 — Pre-Venta: Prospección & Calificación](#2-módulo-0--pre-venta-prospección--calificación)
3. [Módulo 1 — Demo Presencial (El Cierre en Persona)](#3-módulo-1--demo-presencial-el-cierre-en-persona)
4. [Módulo 2 — Free Trial Estructurado](#4-módulo-2--free-trial-estructurado)
5. [Módulo 3 — Conversión a Pago](#5-módulo-3--conversión-a-pago)
6. [Módulo 4 — Onboarding Full](#6-módulo-4--onboarding-full)
7. [Módulo 5 — Retención & Expansión](#7-módulo-5--retención--expansión)
8. [Matriz de Precios & Planes](#8-matriz-de-precios--planes)
9. [Métricas Clave & KPIs](#9-métricas-clave--kpis)
10. [Scripts y Material de Venta](#10-scripts-y-material-de-venta)
11. [Roadmap de Implementación](#11-roadmap-de-implementación)
12. [Referencias & Fuentes](#12-referencias--fuentes)

---

## 1. Filosofía del Funnel

### Principio Rector

**El producto se vende solo — pero la primera venta es en persona.**

InmuebleBot tiene un `visitor→trial` esperado de ~7.1% (estándar real estate SaaS) y un `trial→paid` de ~18%. Pero el demo presencial elimina la fricción de "probar un bot que no conocés" y lleva esos números a un rango muy superior.

### Pipeline Conceptual

```
Prospección → Demo Presencial → Free Trial 14 días → Conversión → Onboarding → Retención
   ↓               ↓                  ↓                 ↓             ↓            ↓
  Frío            Caliente          En prueba         Pagando       Integrado    Crecimiento
  Lead → MQL     SQL → Oportunidad  Trial activo      Cliente       Cliente      Cliente
                                            (Día 0-14)             activo       expandido
                                                  ↑                              ↑
                                            Momento crítico                  Upgrade path
                                            de conversión                    (Básico→Pro→Ent)
```

### Fuentes que Informan Este Framework

| Fuente | Qué aportó |
|--------|-----------|
| Pricing plans v2 ($55/$195/$420) | Estructura de planes, targets, ROI para cada cliente |
| Research v1-v3 | Pain points reales del agente, competencia, TAM/SAM/SOM |
| AGENTS.md + BOT_DOC | Capacidades técnicas reales del producto (no sueños) |
| Video 1: "GTM Strategy 150 startups" | Meta ads + high-intent GTM para B2B SaaS |
| Video 2: "Cold Calling for SaaS" | Cómo abrir conversaciones de venta, relevancia, pain discovery |
| Video 3: "Harvard B2B Sales for Startups" | Sales process, pipeline mgmt, stakeholder mapping, decoy removal |
| Video 4: "Cold Outreach Tech Sales" | Multi-touch sequences, cold email, LinkedIn, prospecting |
| Benchmarks SaaS 2024-2025 | Conversion rates por etapa, trial→paid, pricing psychology |

---

## 2. Módulo 0 — Pre-Venta: Prospección & Calificación

### Objetivo

Generar una lista de prospectos calificados para demo presencial. No es volumen — es precisión. En Misiones hay ~350 inmobiliarias registradas y ~800-1,000 agentes. El target inicial son 30-60 clientes en 12 meses.

### Segmentación de Prospectos

| Tipo | Descripción | Prioridad | Táctica de contacto |
|------|------------|-----------|-------------------|
| **Inmob. establecida (2-5 agentes)** | Tienen oficina, 30-80 propiedades, dueño que quiere crecer | 🔥 Alta | Visita directa + demo en su oficina |
| **Agente individual proactivo** | Trabaja solo, 10-25 propiedades, pierde leads por demora | 🔥 Alta | Llamada → Café → Demo |
| **Desarrollador / Inversor** | 5+ proyectos activos, presupuesto $200-500/mes | 🟡 Media | Llamada fría + propuesta enterprise |
| **Inmob. grande (5-15 agentes)** | Multi-sucursal, necesita datos + inteligencia | 🟡 Media | Cold email + case study → demo |
| **Agente pasivo / mayor** | No usa tecnología, responde en >24h | 🟢 Baja | Recomendación / boca a boca |

### Tácticas de Prospección

#### A. Llamada Fría (adaptado de Video 2 + 4)

```
Apertura con relevancia (NO genérica):

"MARTÍN, TE HABLO PORQUE VEO QUE TENÉS [X PROPIEDADES] EN [ZONA].
LA MAYORÍA DE TUS LEADS LLEGAN POR WHATSAPP, ¿NO?
¿CUÁNTO TIEMPO TE TOMA RESPONDER CADA UNO?"

→ Hook con problema conocido (pain point #1: tiempo de respuesta)

"SI TE DIGO QUE PODÉS RESPONDER EN <2 SEGUNDOS 24/7,
Y QUE EL BOT AGENDE VISITAS POR VOS SIN LEVANTAR UN DEDO...

¿TE SACO 20 MINUTOS ESTA SEMANA PARA MOSTRARTE CÓMO?"

→ Cierre a reunión, no a venta
```

#### B. Cold Email (adaptado de Video 4)

```
Asunto: [NOMBRE] / Leads perdidos en WhatsApp

Hola [Nombre],

Soy [Tu nombre], creador de InmuebleBot — un asistente IA para
inmobiliarias que funciona 100% por WhatsApp.

En Misiones, el 70-80% de los leads nunca reciben respuesta
porque los agentes no dan abasto. InmuebleBot responde en <2s,
cualifica leads y agenda visitas automáticamente.

Ya funciona con [nombre de referencia local si existe].

¿Te interesa una demo de 20 min esta semana?

Saludos,
[Tu nombre]
```

#### C. LinkedIn Outreach (adaptado de Video 4)

```
Paso 1: Connect con nota personalizada
"Martín, vi que estás en [inmobiliaria]. Trabajo con agentes
de Misiones que están automatizando su atención de WhatsApp."

Paso 2: Follow-up a los 3 días
"Martín, te comparto un dato: el 35% de las visitas se pierden
por no-show por falta de recordatorios. Nosotros lo bajamos a <10%.
¿Te interesa ver cómo?"

Paso 3: Llamada / WhatsApp directo
```

#### D. Visita Directa (recomendado para Misiones)

En ciudades como Oberá, Posadas, Eldorado, Puerto Iguazú:
- Las inmobiliarias están concentradas en zonas comerciales
- Una tarde recorriendo 5-8 oficinas rinde más que 100 cold emails
- **Ventaja cultural:** En el interior de Argentina, la venta cara a cara es norma, no excepción

### Pipeline de Prospección

| Etapa | Criterio de paso | Acción |
|-------|-----------------|--------|
| **Lead Frío** | Contacto identificado | Agregar a CRM / lista |
| **Contactado** | Respondió al primer contacto | Enviar mensaje de seguimiento con dato específico |
| **Interesado** | Pidió información o demo | Enviar link a video de 2min + coordinar demo presencial |
| **Demo Agendada** | Fecha y hora confirmadas | Enviar recordatorio 24h antes + preparar demo personalizada |
| **En Demo** | Reunión en curso | [Ver Módulo 1] |

### Métricas de Pre-Venta

| Métrica | Target | Benchmark (B2B SaaS) |
|---------|--------|----------------------|
| Contact Rate (cold call) | 20-30% | 15-25% |
| Demo conversion rate | 15-25% | 10-20% (estándar) |
| Tiempo de cold call a demo | 3-7 días | 7-14 días (SMB) |
| Visitas directas/día | 5-8 oficinas | — |
| CICLO TOTAL PRE-VENTA | 7-14 días | — |

---

## 3. Módulo 1 — Demo Presencial (El Cierre en Persona)

### Objetivo

Que el prospecto **vea funcionar InmuebleBot con SUS propiedades**. No una demo genérica — una demo personalizada donde el bot ya responde por ellos.

### Preparación Pre-Demo (30 min)

1. **Configurar propiedades del prospecto** en el sistema (5-10 propiedades de su catálogo real)
2. **Probar** que el bot responde correctamente a búsquedas típicas de su zona
3. **Tener el dashboard cargado** con leads de prueba para mostrar
4. **Preparar el celular del prospecto** para que él mismo mande un WhatsApp al bot

### Estructura de la Demo (20-25 min)

```
[Apertura — 2 min]
"Gracias por recibirme. Te voy a mostrar algo que
ninguna inmobiliaria en Misiones tiene hoy."

[Setup — 3 min]
"Este es tu número de WhatsApp. Enviale 'hola' a este contacto."

→ El prospecto manda un WhatsApp. El bot responde en <2s.
→ Primer impacto emocional: "¡Mirá, respondió solo!"

[Flujo de búsqueda — 5 min]
"Hablale como si fueras un cliente. Decile 'busco una casa
en [su zona] de [presupuesto]'."

→ El bot busca, cualifica, y muestra resultados.
→ Segundo impacto: "Encontró mis propiedades con los datos exactos"

[Detalle + imágenes — 3 min]
"Ahora decile 'mostrame la primera'."

→ El bot muestra detalles + fotos.
→ Tercer impacto: "Hasta manda las fotos solo"

[Agenda de visita — 5 min]
"Decile 'quiero visitarla mañana a las 10'."

→ El bot agenda la visita, pregunta nombre, confirma.
→ Cuarto impacto: "¡Agendó solo! Y ya está en Google Calendar"

[Dashboard — 3 min]
(Abrís el dashboard en tu notebook)
"Y acá ves todo: leads, scores, visitas agendadas, no-show...
Todo en tiempo real."

[Cierre — 3 min]
"Esto es lo que te proponemos:
- 14 días de prueba GRATIS, sin tarjeta, sin compromiso
- Configuramos tus propiedades nosotros
- A los 14 días, si querés seguir, elegís tu plan

¿Cuándo arrancamos?"

→ Cierre a free trial, NO a pago.
→ Elimina la objeción de precio: "probalo gratis primero."
```

### Manejo de Objeciones (Demo)

| Objeción | Respuesta | Fundamento |
|----------|-----------|------------|
| "Mis clientes quieren hablar con una persona" | "Y pueden — cuando ellos pidan. El bot responde consultas básicas y agenda. Si piden hablar con vos, se los deriva al toque." | Basado en la feature `request_human_assistance` ya implementada |
| "¿Y si no entiende bien algo?" | "Si no entiende, lo deriva a vos. Nunca le tira cualquier cosa al cliente." | Validado por sistema de error detection + handoff |
| "Ya tengo WhatsApp Business" | "WhatsApp Business te deja poner respuestas automáticas fijas. Esto es IA — entiende contexto, matices, cambios de tema. Agenda visitas solo." | Basado en research v1 → gap competitivo |
| "¿Y si no funciona?" | "Por eso la prueba es gratis. Lo configuramos, lo probamos 14 días, y si no te gusta, lo apagamos. Sin drama." | Estrategia de trial sin fricción |
| "¿Cuánto cuesta?" | (Responder SOLO si presiona) "Hay planes desde $55/mes. Pero probalo gratis primero — después ves si vale la pena." | Pricing psychology: anclar con trial, no precio |

### Demo Variants por Plan Target

| Si el prospecto es... | Enfatizar en la demo |
|----------------------|---------------------|
| **Agente individual** | Ahorro de tiempo, leads que no pierde, $55/mes |
| **Inmob. 2-5 agentes (Pro)** | Multi-agente, dashboard compartido, sitio web profesional |
| **Inmob. grande (Enterprise)** | Analítica avanzada, scoring predictivo, alertas, multi-sucursal |

### Post-Demo Inmediato

| Tiempo | Acción |
|--------|--------|
| Al despedirse | Enviar WhatsApp: "Arrancamos mañana con la configuración. Te mando el primer lead que entra." |
| 1 hora post-demo | Configurar sus propiedades (5-10) en el bot |
| 2 horas post-demo | Mandar WhatsApp: "Ya está. Mandale 'hola' al mismo número. El bot ya tiene tus propiedades cargadas." |
| Día 1 del trial | Monitorear primeras interacciones, enviar captura de primer lead |

---

## 4. Módulo 2 — Free Trial Estructurado

### Filosofía

**14 días, sin tarjeta, sin compromiso.** Basado en:
- Benchmark: 14-day trials outperform 30-day by 71% (1Capture data)
- ChartMogul: 14 days is most common (62% of products)
- El trial es una extensión de la demo — el prospecto ya vio el valor, ahora lo vive

### Estructura del Trial de 14 Días

```
DÍA 0              DÍA 3              DÍA 7              DÍA 10           DÍA 14
│                  │                  │                  │                 │
├─ Configuración ─┤─ Primeros ───────┤─ Rutina ─────────┤─ Momento ──────┤─ Cierre ──►
│  (vos hacés)     │  resultados      │  establecida      │  decisión       │  Paga o
│                   │                  │                   │                 │  se pausa
```

### Timeline de Intervención

| Día | Acción del sistema | Acción humana | Estado del prospecto |
|:---:|--------------------|---------------|---------------------|
| **0** | Onboarding: cargamos sus propiedades + activamos bot | Enviar WhatsApp: "Ya está todo listo" | "Bueno, veamos" |
| **1** | Primer lead responde | Enviar captura: "Mirá, entró alguien preguntando por [prop] a las 23hs" | "Ah, posta funciona solo" |
| **3** | 3-5 leads procesados. 1-2 cualificados. | Llamada breve: "¿Viste los leads que entraron?" | "Está funcionando" |
| **5** | Leads siguen entrando. Sin intervención del agente. | Enviar resumen: "Llevás X leads. Sin que levantes un dedo." | "No lo puedo creer" |
| **7** | Primera visita agendada automáticamente. | Enviar captura de Google Calendar: "¿Viste que te agendó una visita?" | "Ya no me imagino sin esto" → **Activación** |
| **10** | 📩 **Mensaje de conversión** automático (ver abajo) | Llamada: "¿Viste los resultados? ¿Qué te pareció?" | "Cuánto era? ah, re barato" |
| **12** | Recordatorio: "Tu trial termina en 2 días" | — | "Dale, me quedo" |
| **13** | Recordatorio: "Último día mañana" | Llamada si no respondió | Último empujón |
| **14** | Se pausa el bot. Conversión o pérdida. | Si no pagó, llamada de recuperación | Paga o pierde acceso |

### Mensaje de Conversión (Día 10, Automático por WhatsApp)

```
👋 Hola [Nombre]! Pasaron 10 días desde que activaste InmuebleBot.

Acá van tus números:
🆕 Leads nuevos: [X]
✅ Cualificados: [Y]
📅 Visitas agendadas: [Z]
⏰ Sin que levantes un dedo.

Tu prueba gratis termina en 4 días.

Para seguir recibiendo leads:
🔹 Plan Básico: $55/mes (agente individual, 25 propiedades)
🔹 Plan Profesional: $195/mes (con web + multi-agente)

¿Te ayudó el bot?
¿Querés que te active el pago?
```

### Gatillos de Activación (PQLs — Product Qualified Leads)

Cuando el prospecto alcanza estos hitos durante el trial, está listo para convertir:

| Hito | Señal | Acción |
|------|-------|--------|
| **Primera visita agendada** | `appointment.created` | Llamar: "¿Viste que te agendó?" |
| **5+ leads cualificados** | `lead_score > 30` × 5 | Enviar resumen + mensaje de conversión |
| **Cliente pide feature** | "¿Esto también se puede?" | "Sí, está en el plan Pro. Cuando te pases, lo activamos" |
| **3+ días sin usar** | `last_interaction > 3 days` | Llamada de recuperación: "¿Todo bien? ¿Necesitás ayuda?" |
| **Alta tasa de no-show** | Si cancela varias citas | "Con el plan Pro el bot hace seguimiento automático a leads fríos" |

### Lo que NO se debe hacer durante el trial

- ❌ NO pedir tarjeta de crédito
- ❌ NO limitar features (el trial debe ser completo)
- ❌ NO bombardear con emails (el agente argentino no lee emails — usa WhatsApp)
- ❌ NO hacer setup complejo (vos configurás todo)
- ❌ NO preguntar "¿qué te pareció?" genéricamente (preguntá sobre resultados concretos)

---

## 5. Módulo 3 — Conversión a Pago

### Principio

El trial de 14 días es el momento de máxima influencia. **El prospecto ya experimentó el valor.** La conversión no es vender — es recordar lo que ya vivió.

### Canales de Conversión

| Canal | Timing | Mensaje clave |
|-------|--------|--------------|
| WhatsApp automático | Día 10 | "Tus números: X leads, Y visitas. Tu trial termina en 4 días." |
| Llamada personal | Día 11 | "¿Viste los resultados? ¿Querés seguir?" |
| WhatsApp recordatorio | Día 12 | "Quedan 2 días de prueba" |
| WhatsApp final | Día 14 | "Tu prueba terminó. El bot se pausó. Para reactivar, cualquier plan desde $55/mes." |

### Estructura de Precios para Conversión

```
🎯 PLAN BÁSICO — $55/mes (~$66,000 ARS)
   Para el agente individual
   ✓ Chatbot 24/7 (hasta 1,000 consultas)
   ✓ 25 propiedades
   ✓ Dashboard de leads
   ✓ Agenda automática

🔥 PLAN PROFESIONAL — $195/mes (~$234,000 ARS)
   Para la inmobiliaria (RECOMENDADO)
   ✓ Todo lo del Básico + Ilimitado
   ✓ Sitio web profesional
   ✓ Multi-agente (hasta 5)
   ✓ Reportes semanales
   ✓ Seguimiento automático de leads

⭐ ENTERPRISE — $420/mes (~$504,000 ARS)
   Para la inmobiliaria grande
   ✓ Todo lo del Profesional
   ✓ Analítica avanzada + scoring predictivo
   ✓ Agentes ilimitados
   ✓ Multi-sucursal
   ✓ Soporte VIP + onboarding presencial
```

### Frame de Conversión (Lo que decís en la llamada)

```
"Mirá, [nombre], el bot te generó [X] leads y [Y] visitas en 10 días
sin que hagas nada. Eso vale mucho más que [$55/$195] al mes.

Te ofrezco dos opciones:
1. Básico a $55 — para vos solo, 25 propiedades
2. Profesional a $195 — con web + multi-agente
   (Si pensás crecer, este es el que te conviene)

Si pagás el año, te llevás 2 meses gratis.

¿Cuál te va mejor?"
```

### Métricas de Conversión Esperadas

| Métrica | Target | Benchmark |
|---------|--------|-----------|
| Trial→Paid (overall) | 25-35% | 18% mediana SaaS / 17.4% real estate |
| Trial→Paid (con demo presencial) | 40-60% | — (no hay benchmark exacto para este modelo híbrido) |
| Día promedio de conversión | 10-12 | — |
| Plan más elegido | Profesional $195 (60%) | — |
| Pago anual vs mensual | 30% anual | — |

### Upgrade Path Post-Conversión

```
FREE TRIAL 14 DÍAS → PAGA
         │
         ├── 1 agente, ≤25 props → BÁSICO $55
         │
         ├── 2-5 agentes, quieren web → PROFESIONAL $195
         │
         └── 5+ agentes, necesitan datos → ENTERPRISE $420
                (disponible post-20 clientes)
```

---

## 6. Módulo 4 — Onboarding Full

### Objetivo

Que el cliente que pagó **esté completamente integrado en <48h**. El onboarding del trial (cargar propiedades) ya está hecho. Ahora es configuración del plan elegido.

### Checklist de Onboarding

| Paso | Responsable | Tiempo | Para qué plan |
|------|-------------|--------|---------------|
| ✅ Cargar todas sus propiedades (no solo 5-10) | Vos | 30 min | Todos |
| ✅ Configurar respuestas de FAQ específicas de la inmobiliaria | Vos | 15 min | Todos |
| ✅ Vincular Google Calendar del agente | Vos | 10 min | Todos |
| ✅ Configurar Google Calendar compartido (multi-agente) | Vos | 15 min | Pro+ |
| ✅ Crear y publicar sitio web profesional | Vos | 2-4h | Pro+ |
| ✅ Configurar chatbot embebido en web | Vos | 30 min | Pro+ |
| ✅ Dashboard avanzado + reportes | Vos | 20 min | Pro+ |
| ✅ Alertas predictivas configuradas | Vos | 15 min | Enterprise |
| ✅ API access + documentación | Vos | 1h | Enterprise |
| ✅ Capacitación del equipo (presencial o videollamada) | Vos | 1h | Pro+ |

### Tiempo de Activación (Time-to-Value)

| Plan | TTFV (Time to First Value) | Primer lead esperado |
|------|---------------------------|---------------------|
| Básico | <2h desde el pago | <24h |
| Profesional | <4h desde el pago | <24h |
| Enterprise | <24h (incluye capacitación) | <48h |

---

## 7. Módulo 5 — Retención & Expansión

### Estructura de Retención

| Tiempo | Acción | Propósito |
|--------|--------|-----------|
| Semana 1 post-pago | Verificar que el bot funcione con todas las propiedades | Asegurar calidad |
| Día 30 | Check-in: "¿Cómo va el primer mes?" | Detectar problemas temprano |
| Mes 2 | Compartir caso de éxito de otro cliente | Reforzar decisión |
| Mes 3-4 | "¿Querés sumar [feature del siguiente plan]?" | Upgrade path |
| Mes 6 | Reporte semestral: leads generados, visitas, ahorro estimado | Mostrar valor acumulado |
| Mes 12 | Renovación anual: "Si renovás hoy, mantenés el precio" | Renovación |

### Upgrade Paths

| Desde | Hacia | Qué lo gatilla |
|-------|-------|----------------|
| Básico ($55) | Profesional ($195) | El cliente supera 25 propiedades o contrata otro agente |
| Profesional ($195) | Enterprise ($420) | El cliente supera 5 agentes o pide analítica |
| Cualquiera → Anual | Ahorro 2 meses | Al renovar o en momento de upgrade |

### Estrategia de Precios Anuales

| Plan | Mensual | Anual (10 meses) | Ahorro |
|------|---------|-----------------|--------|
| Básico | $55 | $550 ($45.83/mes) | $110 (17%) |
| Profesional | $195 | $1,950 ($162.50/mes) | $390 (17%) |
| Enterprise | $420 | $4,200 ($350/mes) | $840 (17%) |

*Indexación trimestral automática por inflación (IPC). Precios en USD como referencia, facturación en ARS al TC del día.*

---

## 8. Matriz de Precios & Planes

*(Tomado de recommended_pricing_plans_v2.txt — ver ese archivo para detalle completo)*

| Feature | Básico ($55) | Profesional ($195) | Enterprise ($420) |
|---------|:-----------:|:----------------:|:----------------:|
| Chatbot 24/7 WhatsApp | ✅ 1K consultas | ✅ Ilimitado | ✅ Ilimitado |
| Propiedades | 25 | Ilimitadas | Ilimitadas |
| Dashboard leads | ✅ Básico | ✅ Avanzado | ✅ Avanzado |
| Embudo de conversión | ❌ | ✅ | ✅ |
| Lead tracking + score | ✅ | ✅ Personalizado | ✅ Predictivo |
| Alertas predictivas | ❌ | ❌ | ✅ |
| Agenda automática | ✅ | ✅ | ✅ |
| Sitio web profesional | ❌ | ✅ | ✅ |
| Chatbot en web | ❌ | ✅ | ✅ |
| Multi-agente | ❌ | Hasta 5 | Ilimitado |
| Reportes semanales | ❌ | ✅ | ✅ |
| Analítica avanzada | ❌ | ❌ | ✅ |
| API access | ❌ | ❌ | ✅ |
| Soporte | 4h hábiles | 1h hábil | VIP + presencial |
| SLA | 99.5% | 99.7% | 99.9% |

---

## 9. Métricas Clave & KPIs

### Funnel Metrics

| Etapa | Qué medir | Target | Benchmark |
|-------|-----------|--------|-----------|
| **Prospección** | Contact rate (calls) | 25%+ | 15-25% |
| **Prospección** | Contact rate (direct visit) | 60%+ | — |
| **De contacto a demo** | Demo booking rate | 20%+ | 10-20% |
| **Demo** | Demo→Trial conversion | 70%+ | — |
| **Demo** | No-show rate (demos) | <10% | — |
| **Trial** | Trial activation rate | 60%+ (alcanzar día 7 hito) | 20-40% (SaaS) |
| **Trial** | Trial→Paid conversion | 30%+ | 18% mediana |
| **Conversión** | Día promedio de conversión | Día 10-12 | — |
| **Post-pago** | Churn rate mensual | <5% | 5-8% B2B AR |
| **Post-pago** | Net Revenue Retention | 110%+ | — |
| **Post-pago** | ARPU (Average Revenue Per User) | $150+/mes | — |
| **Post-pago** | LTV | $3,000+ | — |
| **Post-pago** | CAC payback | <6 meses | 12-18 meses |

### Cálculo de Proyección (12 Meses)

*Basado en research-report-v3.txt — ver archivo para detalle.*

| Mes | Clientes nuevos | Totales | MRR estimado |
|:---:|:--------------:|:-------:|:------------:|
| 1 | 3 | 3 | ~$165 |
| 2 | 4 | 7 | ~$465 |
| 3 | 5 | 12 | ~$835 |
| 4 | 8 | 20 | ~$1,500 |
| 5 | 10 | 30 | ~$2,400 |
| 6 | 12 | 42 | ~$3,500 |
| 7 | 8 | 50 | ~$4,400 |
| 8 | 10 | 60 | ~$5,400 |
| 9 | 12 | 72 | ~$6,700 |
| 10 | 15 | 87 | ~$8,300 |
| 11 | 15 | 102 | ~$10,100 |
| 12 | 18 | 120 | ~$12,200+ |

*Mix esperado: 50% Básico / 35% Pro / 15% Enterprise*

---

## 10. Scripts y Material de Venta

### Script de Cold Call (adaptado de Video 2 + 4)

```
[APERTURA — 10s]
"Hola [Nombre], soy [Tu nombre] de InmuebleBot.
¿Tenés un segundo?"

[HOCK CON PROBLEMA — 20s]
"Voy al grano: la mayoría de los agentes en [ciudad]
pierden el 70% de los leads porque tardan más de 24h en responder.
A vos, ¿cuánto te está pasando?"

[DISCOVERY — 30s]
— Respuesta del prospecto —
"Claro, es que no hay forma de estar 24/7.
Justamente por eso armamos InmuebleBot."

[PROPOSICIÓN DE VALOR — 20s]
"Básicamente es un asistente IA que atiende tu WhatsApp
24/7: responde, cualifica, agenda visitas, manda fotos...
Todo solo."

[CIERRE — 15s]
"Te propongo algo: pasá 20 minutos una tarde de esta semana,
te muestro cómo funciona con tus propiedades.
Sin compromiso. ¿Te viene bien el miércoles a las 17?"

[MANEJO DE OBJECIÓN COMÚN]
"No tengo tiempo" → "Por eso, en 20 minutos te mostramos
cómo ahorrar 15-20 horas a la semana. Es una inversión
de tiempo que se paga sola."

[SI ACEPTA — 5s]
"Perfecto, te mando un WhatsApp con la dirección y nos vemos."

[SI NO ACEPTA — 15s]
"Sin problema. Te mando un video de 2 minutos por WhatsApp
para que le des un vistazo. Si te interesa, me decís."
```

### Script de Demo (full version en Módulo 1 arriba)

### WhatsApp de Seguimiento Post-Demo

```
Hola [Nombre]! Gracias por la reunion de hoy.

Te dejo los datos concretos:
▶️ El bot ya responde tus consultas 24/7
▶️ Agenda visitas sin que levantes un dedo
▶️ Dashboard con todos tus leads en tiempo real

Arrancamos con la prueba gratis mañana.
Te voy a cargar 10 propiedades para que veas como funciona.

Cualquier cosa, acá estoy.
```

### Email de Propuesta Formal (para Enterprise)

```
Asunto: Propuesta InmuebleBot — [Nombre Inmobiliaria]

Hola [Nombre],

Gracias por el tiempo de hoy. Acá va el resumen de lo que
conversamos:

───

PROPUESTA INMUEBLEBOT — [PLAN]

Incluye:
✅ [Feature 1]
✅ [Feature 2]
✅ [Feature 3]

Inversión: [PLAN] — $[PRECIO]/mes o $[ANUAL]/año

───

Próximos pasos:
1. Te comparto el acceso al trial
2. Configuramos tus propiedades
3. En 14 días evaluamos resultados

¿Arrancamos?
```

---

## 11. Roadmap de Implementación

### Fase 1 — Fundación del Funnel (Semanas 1-2)

| Sprint | Qué | Entregable |
|--------|-----|------------|
| S1 | Preparar demo kits (presentación, propiedades de prueba, celular demo) | Demo script + propiedad de prueba lista |
| S2 | Configurar sistema de trials automático (cron para mensajes días 0,3,7,10,12,14) | Mensajes de trial automatizados |
| S3 | Crear CRM de prospectos (tabla en PostgreSQL: lead tracking) | Pipeline de ventas visible |

### Fase 2 — Activar Ventas (Semanas 3-6)

| Semana | Acción | KPI |
|--------|--------|-----|
| 3 | Recorrer 5 inmobiliarias en Oberá (demo directa) | 5 demos hechas |
| 4 | Recorrer 5 inmobiliarias en Posadas | 5 demos hechas |
| 5 | Identificar clientes warm + seguimiento a trials activos | 2+ trials iniciados |
| 6 | Primer cliente pago | 1 cliente pagando |

### Fase 3 — Escalar (Meses 2-6)

| Mes | Meta de clientes | Táctica principal |
|:---:|:----------------:|-------------------|
| 2 | 7 | Referidos de primeros clientes + cold calls |
| 3 | 12 | Demos en Eldorado y Puerto Iguazú + LinkedIn outreach |
| 4 | 20 | Facebook/Instagram ads con caso de éxito |
| 5 | 30 | Primer referido pagado (descuento por referral) |
| 6 | 42 | Escalar a otras provincias (Corrientes, Chaco) |

---

## 12. Referencias & Fuentes

### Fuentes Internas

| Documento | Ruta |
|-----------|------|
| Pricing Plans v2 | `recommended_pricing_plans_v2.txt` |
| Research Report v3 | `research-report-v3.txt` |
| Research Report v2 | `research-report2.txt` |
| Research Report v1 | `research-report.txt` |
| Dev Context | `AGENTS.md` |
| Technical Docs | `BOT_DOCUMENTATION.md` |

### Fuentes Externas (YouTube)

| Video | Título | Canal | Tema clave |
|-------|--------|-------|------------|
| 1 | "The only B2B SaaS GTM strategy I use after scaling 150 startups" | Denis Shatalin | Meta ads + GTM para SaaS B2B |
| 2 | "Full 18-Minute Cold Calling Course (For SaaS Sales)" | Sell Better | Cold calling, pain discovery, cierre |
| 3 | "B2B Sales for Startups Strategies, Tactics & Tradecraft" | Harvard Alumni Entrepreneurs | Sales process, pipeline, stakeholder mapping |
| 4 | "Cold Outreach in Tech Sales: Winning B2B SaaS Sales Tactics" | Matteo Isenburg | Multi-touch sequences, prospecting |

### Fuentes Externas (Research)

| Fuente | Qué aportó |
|--------|-----------|
| ChartMogul SaaS Conversion Report 2025 | Benchmarks de trial→paid (8% mediana), trial length |
| First Page Sage (2022-2025) | Funnel conversions por industria, real estate SaaS data |
| Digital Bloom 2025 Pipeline Benchmarks | Sales cycle length, win rates, pipeline velocity |
| 1Capture (10,000+ SaaS companies) | Trial→paid benchmarks, 14-day outperformance |
| InsideSales / LEADIUM | Lead response time impact (-7% por minuto) |
| NAR Tech Survey 2024 | Real estate tech adoption benchmarks |
| ProfitWell / Paddle | SaaS pricing psychology, anchoring, value-based pricing |
| Harvard Business Review | Lead response time study, pricing research |

---

*Documento generado para InmuebleBot — Mayo 2026*
*Próxima revisión sugerida: Julio 2026 (con datos reales de conversión)*

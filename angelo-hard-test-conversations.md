# Angelo — 10 Conversaciones HARD (cobertura total de tools)

Diseñadas a partir de `angelo-style-analysis.md`. A diferencia del set original (que casi solo
ejercita search → details → fotos → FAQ → agendar), este set fuerza **las 15 tools reales** del
bot, con foco en lo que el doc original casi no probaba: **reprogramar, cancelar, ver mis citas,
comparar, recomendar, preferencias y handoff humano**.

Cada turno (`T#`) va anotado con `→` (tool esperada) y `⚠` (la trampa / qué puede romper).

### Inventario de tools (nombres canónicos del bot)
`search_properties` · `get_property_details` · `get_property_images` · `compare_properties` ·
`recommend_properties` · `refine_search` · `get_faq_answer` · `schedule_visit` ·
`reschedule_appointment` · `cancel_appointment` · `get_my_appointments` ·
`update_user_preferences` · `get_user_preferences` · `save_lead_info` · `request_human_assistance`

### Reglas de negocio que las conversaciones explotan a propósito
- Horario de visitas: **lunes a sábado, 9:00–18:00**. Domingo y fuera de hora → rechazo + repregunta.
- `bedrooms` se trata como **mínimo**. `budget_max` se **expande +20%** internamente; fallbacks: +30% → sin presupuesto → sin tipo de operación → sin dormitorios.
- Agendar exige **nombre y apellido**; si falta, el bot pide el nombre pero NO debe perder fecha/propiedad (pending_scheduling en Redis).
- IDs alucinados (no numéricos ni UUID) deben rebotar, nunca agendar.
- Estilo Angelo: minúsculas, saludo al inicio, "me pasarias / me podes", "si" como confirmación, typos ("esoy", "ebora", "depto"), sin emojis, info progresiva.

---

## Conversación 1 — Funnel completo + rechazo de horario + reprogramación in-situ
**Tools:** `search_properties`, `get_property_details`, `get_property_images`, `schedule_visit` (rechazo domingo + fuera de hora), reintento exitoso
**Por qué es difícil:** el usuario pide domingo (rechazo), después 20:30 (fuera de hora), recién al tercer intento da un horario válido. El bot NO debe perder la propiedad ni volver a pedir todo.

```
T1: buenas tardes, esoy buscando un depto para alquilar en obera
    → search_properties (no hay budget/beds todavía; debe buscar igual o pedir 1 dato, no trabarse)
T2: hasta 180 mil al mes, de 2 dormitorios
    → search_properties (budget_max=180000, bedrooms=2, operation=alquiler, location=Oberá)
    ⚠ no debe re-saludar ni pedir tipo de propiedad de nuevo (ya dijo depto)
T3: me interesa el segundo, me pasarias los detalles?
    → get_property_details (resolver ordinal "segundo" contra last_shown_properties)
    ⚠ debe mapear el ordinal al ID correcto de la lista anterior, no inventar
T4: si, pasame las fotos
    → get_property_images (mismo property_id del turno anterior)
T5: me gustaria ir a verlo el domingo a la mañana
    → schedule_visit (date=domingo) → debe RECHAZAR (domingos no se visita) y repreguntar día
    ⚠ no debe agendar; debe mantener la propiedad en pending
T6: bueno el lunes entonces, a las 8 y media de la noche
    → schedule_visit (lunes 20:30) → fuera de horario (>18hs) → rechazo + repregunta hora
    ⚠ no perder el día lunes ni la propiedad
T7: dale, a las 4 de la tarde
    → schedule_visit (lunes 16:00) → pide nombre y apellido (si no lo tiene)
T8: angelo feier
    → schedule_visit con client_name="Angelo Feier" → CONFIRMA cita
    ⚠ debe reusar lunes 16:00 + property del pending, no volver a preguntar fecha
```

---

## Conversación 2 — Ciclo de vida completo de la cita: agendar → ver → reprogramar → cancelar
**Tools:** `schedule_visit`, `get_my_appointments`, `reschedule_appointment`, `cancel_appointment`
**Por qué es difícil:** es el flujo que el doc original NUNCA prueba. El usuario crea una cita, la consulta, la mueve de día/hora, y al final la cancela. Cada paso necesita resolver la cita correcta del usuario.

```
T1: hola, me interesa la propiedad de san martin 850, quiero coordinar una visita
    → get_property_details (búsqueda difusa por dirección "san martin 850")
    ⚠ si hay varias coincidencias debe listar y desambiguar, no asumir
T2: si esa, el miercoles a las 10 de la mañana, soy angelo feier
    → schedule_visit (miércoles 10:00, client_name) → CONFIRMA
T3: me confirmas que dia me quedo agendado?
    → get_my_appointments → lista la cita del miércoles
    ⚠ NO debe re-agendar; es solo consulta
T4: che, mejor pasala para el jueves a la misma hora
    → reschedule_appointment (auto-resolver la única cita futura → jueves 10:00)
    ⚠ debe conservar la hora 10:00 si el usuario solo cambió el día
T5: pensandolo bien mejor cancelala, me surgio un viaje
    → cancel_appointment (auto-resolver única cita futura, reason="viaje")
    ⚠ no debe pedir un ID técnico; resolver solo
```

---

## Conversación 3 — Varias citas → cancelación AMBIGUA (hay que listar y elegir la N°2)
**Tools:** `schedule_visit` ×2, `get_my_appointments`, `cancel_appointment` (desambiguación)
**Por qué es difícil:** con DOS citas futuras, cancelar "una" es ambiguo. El bot debe listarlas y esperar que el usuario elija; recién ahí cancelar la correcta.

```
T1: buenas, quiero agendar dos visitas, la del id 6 el martes 11hs y la del id 12 el jueves 15hs, soy angelo feier
    → schedule_visit (id 6, martes 11:00) y schedule_visit (id 12, jueves 15:00)
    ⚠ debe agendar AMBAS, no quedarse con una sola; multi-intent en un mensaje
T2: que citas tengo agendadas?
    → get_my_appointments → lista las 2
T3: cancela una
    → cancel_appointment → como hay 2, debe LISTAR y preguntar cuál (no cancelar al azar)
    ⚠ trampa principal: cancelar la primera por defecto sería un error
T4: la del jueves
    → cancel_appointment (resolver a la cita del jueves específicamente)
    ⚠ debe cancelar la #2, no la del martes
```

---

## Conversación 4 — Comparar propiedades + recomendar + ordinal "el más barato"
**Tools:** `search_properties`, `compare_properties`, `get_property_details`, `recommend_properties`
**Por qué es difícil:** pide comparar dos resultados explícitos, después "cuál conviene" (recomendación), y "el más barato" exige razonar sobre precios de la lista, no inventar.

```
T1: hola buenos dias, busco departamento en alquiler en obera de 2 o 3 dormitorios
    → search_properties (bedrooms=2 tratado como mínimo → trae 2 y 3; operation=alquiler)
    ⚠ debe traer resultados de 2 Y 3, no solo exactamente 2
T2: me podes comparar el 1 y el 3 de la lista?
    → compare_properties (resolver ordinales "1" y "3" a property_ids de last_shown)
    ⚠ mapear ordinales correctos; no comparar IDs inventados
T3: cual me recomendas para una familia?
    → recommend_properties (o razonamiento sobre la comparación previa, con criterio "familia")
T4: pasame los detalles del mas barato de los dos
    → get_property_details del de menor precio entre los comparados
    ⚠ debe elegir el barato real, no el primero
```

---

## Conversación 5 — Sin resultados → cadena de fallbacks → refinamiento
**Tools:** `search_properties` (fallbacks 1–4), `refine_search`
**Por qué es difícil:** pide 5 dormitorios (no existe) con presupuesto bajísimo. El bot debe degradar con gracia (subir presupuesto / bajar dormitorios) y no contestar "no hay nada" en seco.

```
T1: buenas tardes, busco una casa de 5 dormitorios en obera para alquilar
    → search_properties (bedrooms=5) → probablemente 0 → fallbacks
    ⚠ debe ofrecer alternativas (menos dormitorios u otras), no cortar
T2: hasta 90 mil al mes puedo pagar
    → search_properties (budget_max=90000) → 0 reales → fallback +30% / sin presupuesto
    ⚠ no debe quedarse sin ofrecer nada; explicar que subió el rango
T3: y de 3 dormitorios que tenes?
    → search_properties (bedrooms=3, mantiene location+budget del contexto)
    ⚠ debe heredar location=Oberá y presupuesto previos, no resetear
T4: mostrame algo mas barato
    → refine_search → search_properties con sort_by=price_asc / budget menor
```

---

## Conversación 6 — Cambio de tipo a mitad + landmark "cerca de la unam" + memoria de contexto
**Tools:** `search_properties` (reset de tipo), `get_property_details` (landmark/ordinal), `get_property_images`
**Por qué es difícil:** arranca buscando depto, a mitad cambia a casa (debe resetear tipo pero conservar zona/presupuesto), y usa landmark en vez de dirección.

```
T1: hola buenas noches, estoy buscando un depto para alquilar cerca de la unam
    → search_properties (location=Oberá + zone/landmark "unam", type=departamento)
    ⚠ debe interpretar "unam" como referencia de zona, no como ciudad
T2: hasta 150 mil
    → search_properties (budget_max=150000, conserva zona unam + tipo depto)
T3: sabes si tenes casas tambien por esa zona? me interesa ver las dos cosas
    → search_properties (type=casa, MISMA zona unam) — mantener depto previo en contexto
    ⚠ trampa: debe cambiar property_type a casa SIN perder la zona; idealmente ofrecer ambas
T4: la primera casa me interesa, mandame fotos
    → get_property_images (resolver "la primera casa" al ID correcto de la última lista de casas)
    ⚠ ojo de no agarrar el primer depto de la lista anterior
```

---

## Conversación 7 — FAQ a fondo + servicios + escalamiento a humano
**Tools:** `get_faq_answer` ×3, `request_human_assistance`
**Por qué es difícil:** tres preguntas FAQ encadenadas (requisitos, comisión, garantía) y al final algo que el bot NO sabe contestar (caso legal puntual) → debe derivar a humano, no inventar.

```
T1: hola, me podrias contar que requisitos piden para alquilar?
    → get_faq_answer (question="requisitos para alquilar")
T2: y cuanto es la comision?
    → get_faq_answer (question="comisión")
    ⚠ no debe inventar un porcentaje si la FAQ no lo tiene; si no hay dato, decirlo
T3: el precio incluye los servicios o los pago aparte?
    → get_faq_answer (question="servicios incluidos en el precio")
T4: tengo una garantia de otra provincia y un tema legal con un embargo, me sirve igual?
    → request_human_assistance (caso fuera de FAQ / legal específico)
    ⚠ trampa: NO inventar respuesta legal; derivar a un agente humano
```

---

## Conversación 8 — Trampas de agendado: ID alucinado, nombre obligatorio, fecha relativa
**Tools:** `get_property_details`, `schedule_visit` (guarda de ID inválido + nombre + fecha relativa)
**Por qué es difícil:** el usuario da una referencia vaga, después una fecha relativa ("dentro de 3 días"), y el bot debe usar IDs reales (no alucinar) y exigir nombre sin perder la fecha.

```
T1: buenas, me interesa una propiedad que vi, la del centro con pileta
    → get_property_details (búsqueda difusa "centro pileta") → probablemente varios → listar
    ⚠ no debe agendar todavía; primero fijar la propiedad por ID real
T2: la segunda de esas
    → get_property_details (resolver "la segunda" de los candidatos listados → ID concreto)
T3: quiero ir a verla dentro de 3 dias a las 5 de la tarde
    → schedule_visit (date_str="dentro de 3 dias", time="17:00")
    ⚠ debe pasar la fecha relativa TAL CUAL (no convertirla mal a un día pasado); usar ID real, nunca inventado
T4: angelo feier, mi mail es djulian@live.com.ar
    → schedule_visit con client_name + (opcional save_lead_info con email) → CONFIRMA
    ⚠ debe reusar la fecha "dentro de 3 días" y el ID del pending, no repreguntar
```

---

## Conversación 9 — Usuario que vuelve: preferencias guardadas + recomendación
**Tools:** `get_user_preferences`, `update_user_preferences`, `save_lead_info`, `recommend_properties`, `search_properties`
**Por qué es difícil:** simula continuidad de sesión. El bot debe recuperar/guardar preferencias y recomendar en base a ellas, no arrancar de cero.

```
T1: hola, ya habia hablado antes, vuelvo a consultar lo mismo de siempre
    → get_user_preferences (intentar recuperar preferencias previas)
    ⚠ si no hay nada guardado, pedir criterios; si hay, usarlos
T2: si, depto en alquiler cerca de la unam, hasta 120 mil, 2 dormitorios, acordate de eso
    → update_user_preferences (location=Oberá/unam, operation=alquiler, budget_max=120000, bedrooms=2, type=depto)
    ⚠ "acordate" es señal explícita de persistir preferencias
T3: mi nombre es angelo feier por si me queres anotar
    → save_lead_info (name="Angelo Feier")
T4: bueno, que me recomendas con eso?
    → recommend_properties (usar preferencias guardadas) o search_properties con esos criterios
    ⚠ debe aplicar TODO lo guardado, no volver a preguntar presupuesto/zona
```

---

## Conversación 10 — Reprogramar sin cita previa (gracioso) + agendar nuevo + día+hora juntos
**Tools:** `reschedule_appointment` (sin cita → degradación), `search_properties`, `get_property_details`, `schedule_visit` (multi-campo)
**Por qué es difícil:** el usuario pide reprogramar algo que no existe; el bot debe responder con gracia y reconducir a agendar. Después extrae día+hora de un solo mensaje.

```
T1: hola buenas, queria cambiar la fecha de mi visita
    → reschedule_appointment (phone) → no hay citas futuras → mensaje gracioso ofreciendo agendar
    ⚠ trampa: no debe simular que reprogramó algo inexistente
T2: ah no tenia ninguna, bueno busco un depto de 1 dormitorio en obera para alquilar
    → search_properties (bedrooms=1, operation=alquiler, location=Oberá)
T3: me interesa el ultimo de la lista, dame los detalles
    → get_property_details (resolver ordinal "el último" de last_shown_properties)
    ⚠ "último" = el de mayor índice, no el primero
T4: lo quiero ver el sabado a las 11 de la mañana, soy angelo feier
    → schedule_visit (sábado 11:00, client_name) en UN turno → CONFIRMA
    ⚠ sábado SÍ es hábil (lun–sáb); extraer día+hora+nombre del mismo mensaje sin loop
```

---

## Matriz de cobertura (qué conversación toca cada tool)

| Tool | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 |
|------|----|----|----|----|----|----|----|----|----|-----|
| search_properties        | ✓ |   |   | ✓ | ✓ | ✓ |   |   | ✓ | ✓ |
| get_property_details      | ✓ | ✓ |   | ✓ |   |   |   | ✓ |   | ✓ |
| get_property_images       | ✓ |   |   |   |   | ✓ |   |   |   |   |
| compare_properties        |   |   |   | ✓ |   |   |   |   |   |   |
| recommend_properties      |   |   |   | ✓ |   |   |   |   | ✓ |   |
| refine_search             |   |   |   |   | ✓ |   |   |   |   |   |
| get_faq_answer            |   |   |   |   |   |   | ✓ |   |   |   |
| schedule_visit            | ✓ | ✓ | ✓ |   |   |   |   | ✓ |   | ✓ |
| reschedule_appointment    |   | ✓ |   |   |   |   |   |   |   | ✓ |
| cancel_appointment        |   | ✓ | ✓ |   |   |   |   |   |   |   |
| get_my_appointments       |   | ✓ | ✓ |   |   |   |   |   |   |   |
| update_user_preferences   |   |   |   |   |   |   |   |   | ✓ |   |
| get_user_preferences      |   |   |   |   |   |   |   |   | ✓ |   |
| save_lead_info            |   |   |   |   |   |   |   | ✓ | ✓ |   |
| request_human_assistance  |   |   |   |   |   |   | ✓ |   |   |   |

**Las 15 tools quedan cubiertas.** Los flujos de cita (agendar/reprogramar/cancelar/listar),
que el set original casi ignoraba, se prueban a fondo en C1, C2, C3 y C10 — incluyendo los
casos duros: rechazo por horario, desambiguación de cita, reprogramación sin cita previa, y
extracción multi-campo en un solo mensaje.
```

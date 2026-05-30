# Angelo — 150 Conversaciones HARD (15 variaciones × 10 escenarios)

Banco de pruebas derivado de `angelo-hard-test-conversations.md`. Son **15 personas** distintas
(V1…V15), cada una corriendo los **10 escenarios** (C1…C10) con la misma estructura de tools y
las mismas trampas, pero variando superficie: **nombre, propiedades, zonas, presupuestos,
días/horas y typos**. Total: **150 conversaciones ideales**.

Cada turno (`T#`) lleva `→` (tool esperada) y, donde importa, `⚠` (la trampa).

## Cómo correrlas (simulación, sin WhatsApp)
`POST https://inmueblebot-api.onrender.com/simulate/multi` (sin auth). Mismo `session_id` por
conversación; el `phone` (o `bsuid`) identifica al usuario. Devuelve `tools_called`, `router`,
`selection`, `active_intents` — comparalo contra el `→` esperado.

```bash
curl -sS -X POST https://inmueblebot-api.onrender.com/simulate/multi \
  -H "Content-Type: application/json" \
  -d '{"message":"<T1>","session_id":"v1-c1","phone":"549-test-v1"}'
# repetí con el MISMO session_id para T2, T3, ...
```
> ⚠️ Las tools de cita/lead **escriben en la DB real** (citas, leads). Usá un `session_id`/phone de test y limpiá después.

## Legend de escenarios (qué prueba cada C#)
- **C1** — Funnel + rechazo de horario (domingo / fuera de hora) + reintento. `search→details→images→schedule_visit`. ⚠ no perder propiedad ni repetir todo.
- **C2** — Ciclo de cita: agendar→ver→reprogramar→cancelar. `schedule_visit, get_my_appointments, reschedule_appointment, cancel_appointment`.
- **C3** — 2 citas → cancelación AMBIGUA (elegir la #2). `schedule_visit×2, get_my_appointments, cancel_appointment`. ⚠ no cancelar al azar.
- **C4** — Comparar + recomendar + "el más barato". `search, compare_properties, recommend_properties, get_property_details`.
- **C5** — Sin resultados → fallbacks → refinar. `search (fallbacks), refine_search`. ⚠ nunca "no hay nada" en seco.
- **C6** — Cambio de tipo a mitad + landmark "cerca de la unam". `search (reset tipo), details, images`. ⚠ cambiar tipo sin perder zona.
- **C7** — FAQ ×3 + escalamiento a humano. `get_faq_answer×3, request_human_assistance`. ⚠ no inventar; derivar lo legal.
- **C8** — Trampas de agendado: ID alucinado + nombre obligatorio + fecha relativa. `get_property_details, schedule_visit`.
- **C9** — Usuario que vuelve: preferencias + recomendación. `get_user_preferences, update_user_preferences, save_lead_info, recommend_properties`.
- **C10** — Reprogramar sin cita (degradación) + agendar nuevo con día+hora juntos. `reschedule_appointment, search, details, schedule_visit`.

> Nota: en el router **V2 actual** solo están cableadas 7 tools (`search_properties, get_property_details, get_property_images, get_faq_answer, schedule_visit, echo, get_time`). Los escenarios C2/C3/C4/C7/C9 (y partes de C10) ejercitan tools aún no wireadas en V2 — quedan como objetivo cuando se integren.

---

# Variación V1 — Angelo Feier  (depto · alquiler · Centro)

## V1·C1 — funnel + rechazo horario
```
T1: buenas tardes, esoy buscando un depto para alquilar en obera         → search_properties
T2: hasta 180 mil al mes, de 2 dormitorios                                → search_properties (budget=180000, beds=2, alquiler)
T3: me interesa el segundo, me pasarias los detalles?                     → get_property_details (ordinal "segundo")
T4: si, pasame las fotos                                                   → get_property_images
T5: me gustaria ir a verlo el domingo a la mañana                         → schedule_visit (RECHAZA domingo)  ⚠ no agendar
T6: bueno el lunes entonces, a las 8 y media de la noche                  → schedule_visit (lunes 20:30 fuera de hora)  ⚠ rechaza, no pierde lunes
T7: dale, a las 4 de la tarde                                              → schedule_visit (lunes 16:00, pide nombre)
T8: angelo feier                                                           → schedule_visit (Angelo Feier) → CONFIRMA
```

## V1·C2 — ciclo de cita
```
T1: hola, me interesa la propiedad de san martin 850, quiero coordinar    → get_property_details (difuso por dirección)
T2: si esa, el miercoles a las 10 de la mañana, soy angelo feier          → schedule_visit (miércoles 10:00) → CONFIRMA
T3: me confirmas que dia me quedo agendado?                               → get_my_appointments  ⚠ no re-agendar
T4: che, mejor pasala para el jueves a la misma hora                      → reschedule_appointment (jueves 10:00)
T5: pensandolo bien mejor cancelala, me surgio un viaje                   → cancel_appointment (reason=viaje)
```

## V1·C3 — cancelación ambigua
```
T1: quiero agendar dos visitas, la del id 6 el martes 11hs y la del 12 el jueves 15hs, soy angelo feier  → schedule_visit ×2
T2: que citas tengo agendadas?                                           → get_my_appointments (2)
T3: cancela una                                                          → cancel_appointment (LISTA, pregunta cuál)  ⚠ no al azar
T4: la del jueves                                                        → cancel_appointment (#2 jueves)
```

## V1·C4 — comparar + recomendar
```
T1: hola buenos dias, busco departamento en alquiler en obera de 2 o 3 dormitorios  → search_properties (beds≥2)
T2: me podes comparar el 1 y el 3 de la lista?                          → compare_properties (ordinales)
T3: cual me recomendas para una familia?                               → recommend_properties (criterio familia)
T4: pasame los detalles del mas barato de los dos                      → get_property_details (menor precio)
```

## V1·C5 — fallbacks
```
T1: buenas tardes, busco una casa de 5 dormitorios en obera para alquilar  → search_properties (beds=5 → 0 → fallback)
T2: hasta 90 mil al mes puedo pagar                                       → search_properties (budget=90000 → fallback +30%)
T3: y de 3 dormitorios que tenes?                                         → search_properties (beds=3, hereda zona/budget)
T4: mostrame algo mas barato                                              → refine_search (price_asc)
```

## V1·C6 — cambio de tipo + landmark
```
T1: hola buenas noches, estoy buscando un depto para alquilar cerca de la unam  → search_properties (zona=unam, depto)
T2: hasta 150 mil                                                              → search_properties (budget=150000)
T3: sabes si tenes casas tambien por esa zona? me interesa ver las dos cosas   → search_properties (casa, misma zona)  ⚠ no perder unam
T4: la primera casa me interesa, mandame fotos                                 → get_property_images (1ª casa)
```

## V1·C7 — FAQ + humano
```
T1: hola, me podrias contar que requisitos piden para alquilar?  → get_faq_answer (requisitos)
T2: y cuanto es la comision?                                     → get_faq_answer (comisión)
T3: el precio incluye los servicios o los pago aparte?           → get_faq_answer (servicios)
T4: tengo una garantia de otra provincia y un embargo, me sirve? → request_human_assistance  ⚠ no inventar legal
```

## V1·C8 — trampas de agendado
```
T1: buenas, me interesa una propiedad que vi, la del centro con pileta  → get_property_details (difuso, listar)
T2: la segunda de esas                                                  → get_property_details (ordinal → ID real)
T3: quiero ir a verla dentro de 3 dias a las 5 de la tarde              → schedule_visit (fecha relativa, ID real)
T4: angelo feier, mi mail es djulian@live.com.ar                       → schedule_visit (+save_lead_info email) → CONFIRMA
```

## V1·C9 — usuario que vuelve
```
T1: hola, ya habia hablado antes, vuelvo a consultar lo mismo de siempre        → get_user_preferences
T2: si, depto en alquiler cerca de la unam, hasta 120 mil, 2 dormitorios, acordate  → update_user_preferences
T3: mi nombre es angelo feier por si me queres anotar                            → save_lead_info (Angelo Feier)
T4: bueno, que me recomendas con eso?                                            → recommend_properties
```

## V1·C10 — reprogramar sin cita + agendar
```
T1: hola buenas, queria cambiar la fecha de mi visita        → reschedule_appointment (sin cita → ofrece agendar)  ⚠ no simular
T2: ah no tenia ninguna, bueno busco un depto de 1 dormitorio en obera para alquilar  → search_properties (beds=1)
T3: me interesa el ultimo de la lista, dame los detalles     → get_property_details (ordinal "último")
T4: lo quiero ver el sabado a las 11 de la mañana, soy angelo feier  → schedule_visit (sábado 11:00) → CONFIRMA
```

---

# Variación V2 — Martín Suárez  (casa · alquiler · UNAM)

## V2·C1 — funnel + rechazo horario
```
T1: hola, busco una casa en alquiler por la zona de la unam              → search_properties
T2: hasta 250 mil, 3 dormitorios mínimo                                  → search_properties (budget=250000, beds=3)
T3: la tercera me interesa, tiras los detalles?                          → get_property_details (ordinal)
T4: dale, mandame fotos                                                  → get_property_images
T5: la quiero ver el domingo al mediodia                                 → schedule_visit (RECHAZA domingo)
T6: ok el martes 7 de la tarde y media                                   → schedule_visit (martes 19:30 fuera de hora)
T7: bueno a las 10 de la mañana                                          → schedule_visit (martes 10:00, pide nombre)
T8: martin suarez                                                        → schedule_visit (Martín Suárez) → CONFIRMA
```

## V2·C2 — ciclo de cita
```
T1: me interesa la casa de avellaneda 1240, quiero ir a verla            → get_property_details (difuso dirección)
T2: esa si, el jueves 9 de la mañana, soy martin suarez                  → schedule_visit (jueves 09:00) → CONFIRMA
T3: para que dia me anote?                                               → get_my_appointments
T4: movela al viernes misma hora                                        → reschedule_appointment (viernes 09:00)
T5: no, cancelala mejor, no voy a poder                                  → cancel_appointment
```

## V2·C3 — cancelación ambigua
```
T1: agendame dos, id 15 el lunes 12hs y id 44 el miercoles 16hs, soy martin suarez  → schedule_visit ×2
T2: cuales visitas tengo?                                                → get_my_appointments (2)
T3: borra una                                                           → cancel_appointment (lista, pregunta)
T4: la del miercoles                                                     → cancel_appointment (#2)
```

## V2·C4 — comparar + recomendar
```
T1: buenas, busco casa en alquiler en obera de 3 o 4 dormitorios         → search_properties (beds≥3)
T2: compará la 2 y la 4 porfa                                            → compare_properties
T3: cual conviene para una familia grande?                              → recommend_properties
T4: pasame el detalle de la mas barata                                   → get_property_details (menor precio)
```

## V2·C5 — fallbacks
```
T1: busco una casa de 6 dormitorios en obera para alquilar               → search_properties (beds=6 → 0)
T2: tengo hasta 80 mil                                                    → search_properties (budget=80000 → fallback)
T3: y de 4 dormitorios?                                                   → search_properties (beds=4, hereda)
T4: algo mas economico tenes?                                            → refine_search (price_asc)
```

## V2·C6 — cambio de tipo + landmark
```
T1: estoy buscando una casa cerca de la unam para alquilar               → search_properties (zona unam, casa)
T2: hasta 220 mil                                                        → search_properties (budget=220000)
T3: y deptos por esa zona tenes? quiero ver las dos opciones             → search_properties (depto, misma zona)
T4: el primer depto mandame fotos                                        → get_property_images (1er depto)
```

## V2·C7 — FAQ + humano
```
T1: que requisitos piden para alquilar una casa?  → get_faq_answer (requisitos)
T2: la comision cuanto sale?                       → get_faq_answer (comisión)
T3: el abl y expensas van aparte?                  → get_faq_answer (servicios)
T4: soy monotributista categoria A y vivo afuera del pais, me alquilan igual?  → request_human_assistance
```

## V2·C8 — trampas de agendado
```
T1: me gusto una casa que vi, la del barrio con quincho                  → get_property_details (difuso, listar)
T2: la primera                                                          → get_property_details (ordinal)
T3: la quiero ver pasado mañana a las 4                                  → schedule_visit (fecha relativa)
T4: martin suarez                                                       → schedule_visit (nombre) → CONFIRMA
```

## V2·C9 — usuario que vuelve
```
T1: hola de nuevo, lo mismo que la vez pasada                            → get_user_preferences
T2: casa en alquiler cerca de la unam, hasta 240 mil, 3 dorm, anotalo    → update_user_preferences
T3: anotame, soy martin suarez                                           → save_lead_info
T4: que me recomendas?                                                   → recommend_properties
```

## V2·C10 — reprogramar sin cita + agendar
```
T1: hola, queria mover mi visita de dia                                  → reschedule_appointment (sin cita → ofrece)
T2: ah no tenia, bueno busco casa de 2 dormitorios en obera alquiler     → search_properties (beds=2, casa)
T3: la ultima dame detalles                                             → get_property_details (ordinal "última")
T4: la veo el sabado a las 3 de la tarde, soy martin suarez             → schedule_visit (sábado 15:00) → CONFIRMA
```

---

# Variación V3 — Lucía Gómez  (depto · alquiler · Barrio Schuster)

## V3·C1 — funnel + rechazo horario
```
T1: holaa busco un depto chico para alquilar en schuster                 → search_properties
T2: 1 dormitorio, hasta 120 mil                                          → search_properties (beds=1, budget=120000)
T3: el segundo me gusta, detalles porfa                                  → get_property_details (ordinal)
T4: si fotos                                                            → get_property_images
T5: lo veo el domingo temprano                                          → schedule_visit (RECHAZA domingo)
T6: el lunes 9 de la noche                                              → schedule_visit (lunes 21:00 fuera de hora)
T7: bueno 11 de la mañana                                               → schedule_visit (lunes 11:00, pide nombre)
T8: lucia gomez                                                        → schedule_visit (Lucía Gómez) → CONFIRMA
```

## V3·C2 — ciclo de cita
```
T1: me interesa el depto de rivadavia 470, quiero visitarlo              → get_property_details (difuso)
T2: ese, el miercoles 3 de la tarde, soy lucia gomez                     → schedule_visit (miércoles 15:00) → CONFIRMA
T3: que dia me agende?                                                   → get_my_appointments
T4: pasalo al jueves misma hora                                         → reschedule_appointment (jueves 15:00)
T5: cancelala, me cambio el plan                                        → cancel_appointment
```

## V3·C3 — cancelación ambigua
```
T1: agendame dos visitas, id 7 el martes 10hs y id 9 el viernes 11hs, soy lucia gomez  → schedule_visit ×2
T2: que tengo agendado?                                                  → get_my_appointments (2)
T3: cancelame una                                                       → cancel_appointment (lista)
T4: la del viernes                                                       → cancel_appointment (#2)
```

## V3·C4 — comparar + recomendar
```
T1: busco depto en alquiler en schuster de 1 o 2 dormitorios             → search_properties (beds≥1)
T2: compará el 1 y el 2                                                  → compare_properties
T3: cual me conviene si vivo sola?                                      → recommend_properties
T4: el mas barato pasame detalles                                       → get_property_details (menor precio)
```

## V3·C5 — fallbacks
```
T1: busco un depto de 4 dormitorios en schuster alquiler                 → search_properties (beds=4 → 0)
T2: hasta 70 mil                                                         → search_properties (budget=70000 → fallback)
T3: de 2 dormitorios que hay?                                            → search_properties (beds=2, hereda)
T4: mostrame mas baratos                                                → refine_search
```

## V3·C6 — cambio de tipo + landmark
```
T1: busco depto para alquilar cerca de la unam                           → search_properties (zona unam, depto)
T2: hasta 110 mil                                                        → search_properties (budget=110000)
T3: y ph por la zona? quiero ver ambas                                   → search_properties (ph, misma zona)
T4: el primer ph fotos                                                  → get_property_images
```

## V3·C7 — FAQ + humano
```
T1: que necesito para alquilar?                  → get_faq_answer (requisitos)
T2: cobran comision?                              → get_faq_answer (comisión)
T3: los servicios estan incluidos?               → get_faq_answer (servicios)
T4: tengo un juicio de alquiler anterior sin resolver, eso me complica?  → request_human_assistance
```

## V3·C8 — trampas de agendado
```
T1: me intereso un depto que vi, el del centro con balcon                → get_property_details (difuso, listar)
T2: la segunda opcion                                                   → get_property_details (ordinal)
T3: lo veo dentro de 2 dias a las 5                                      → schedule_visit (relativa)
T4: lucia gomez                                                         → schedule_visit → CONFIRMA
```

## V3·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo de siempre                                       → get_user_preferences
T2: depto alquiler en schuster, hasta 115 mil, 1 dorm, acordate          → update_user_preferences
T3: soy lucia gomez, anotame                                            → save_lead_info
T4: recomendame algo con eso                                            → recommend_properties
```

## V3·C10 — reprogramar sin cita + agendar
```
T1: queria cambiar el dia de mi visita                                   → reschedule_appointment (sin cita)
T2: no tenia ninguna jaja, busco monoambiente en obera alquiler          → search_properties (beds=1)
T3: el ultimo dame detalles                                             → get_property_details (ordinal)
T4: lo veo el sabado 10 de la mañana, soy lucia gomez                   → schedule_visit (sábado 10:00) → CONFIRMA
```

---

# Variación V4 — Diego Ramírez  (casa · venta · Ruta 14)

## V4·C1 — funnel + rechazo horario
```
T1: buenas, busco casa en venta sobre ruta 14                            → search_properties
T2: hasta 200 mil dolares, 4 dormitorios                                 → search_properties (budget=200000, beds=4, venta)
T3: la primera detalles                                                 → get_property_details
T4: fotos dale                                                          → get_property_images
T5: la veo el domingo                                                   → schedule_visit (RECHAZA domingo)
T6: el lunes 8 de la noche                                              → schedule_visit (lunes 20:00 fuera de hora)
T7: 2 de la tarde                                                       → schedule_visit (lunes 14:00, pide nombre)
T8: diego ramirez                                                      → schedule_visit (Diego Ramírez) → CONFIRMA
```

## V4·C2 — ciclo de cita
```
T1: me interesa la casa de mitre 980, quiero coordinar visita            → get_property_details (difuso)
T2: esa, miercoles 11hs, diego ramirez                                   → schedule_visit (miércoles 11:00) → CONFIRMA
T3: que dia quedó?                                                       → get_my_appointments
T4: movela al jueves misma hora                                         → reschedule_appointment (jueves 11:00)
T5: cancelala, no llego                                                  → cancel_appointment
```

## V4·C3 — cancelación ambigua
```
T1: agendame dos, id 20 martes 9hs y id 21 jueves 17hs, diego ramirez    → schedule_visit ×2
T2: que citas tengo?                                                     → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V4·C4 — comparar + recomendar
```
T1: busco casa en venta en obera de 3 o 4 dormitorios                    → search_properties (beds≥3, venta)
T2: comparame la 1 y la 2                                                → compare_properties
T3: cual conviene como inversion?                                       → recommend_properties
T4: la mas barata detalles                                              → get_property_details (menor precio)
```

## V4·C5 — fallbacks
```
T1: busco casa de 6 dormitorios en venta en obera                        → search_properties (beds=6 → 0)
T2: hasta 100 mil dolares                                                → search_properties (budget bajo → fallback)
T3: de 4 dormitorios?                                                    → search_properties (beds=4, hereda)
T4: algo mas barato                                                     → refine_search
```

## V4·C6 — cambio de tipo + landmark
```
T1: busco casa en venta cerca de la unam                                 → search_properties (zona unam, casa)
T2: hasta 180 mil dolares                                                → search_properties (budget)
T3: y terrenos por la zona? quiero ver ambas                             → search_properties (terreno, misma zona)
T4: el primer terreno detalles                                          → get_property_details
```

## V4·C7 — FAQ + humano
```
T1: que requisitos hay para comprar?              → get_faq_answer (requisitos compra)
T2: hay gastos de escritura?                       → get_faq_answer (gastos/escritura)
T3: aceptan parte en pesos?                        → get_faq_answer (forma de pago)
T4: tengo un inmueble en sucesión sin terminar para dar en parte de pago, se puede?  → request_human_assistance
```

## V4·C8 — trampas de agendado
```
T1: me intereso una casa que vi, la de la esquina con cochera doble      → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: la veo dentro de 3 dias a las 4 y media                              → schedule_visit (relativa)
T4: diego ramirez                                                      → schedule_visit → CONFIRMA
```

## V4·C9 — usuario que vuelve
```
T1: hola, vuelvo a consultar lo de antes                                 → get_user_preferences
T2: casa en venta ruta 14, hasta 190 mil usd, 4 dorm, acordate           → update_user_preferences
T3: soy diego ramirez                                                   → save_lead_info
T4: recomendame con eso                                                 → recommend_properties
```

## V4·C10 — reprogramar sin cita + agendar
```
T1: queria reprogramar una visita                                        → reschedule_appointment (sin cita)
T2: no tenia, busco casa de 3 dorm en venta en obera                     → search_properties (beds=3, venta)
T3: la ultima detalles                                                  → get_property_details (ordinal)
T4: la veo el sabado a las 12, diego ramirez                            → schedule_visit (sábado 12:00) → CONFIRMA
```

---

# Variación V5 — Sofía Benítez  (depto · alquiler · Terminal)

## V5·C1 — funnel + rechazo horario
```
T1: hola busco depto en alquiler cerca de la terminal                    → search_properties
T2: 2 dormitorios, hasta 100 mil                                         → search_properties (beds=2, budget=100000)
T3: el tercero detalles                                                 → get_property_details (ordinal)
T4: fotos si                                                           → get_property_images
T5: lo veo domingo a la tarde                                           → schedule_visit (RECHAZA domingo)
T6: lunes 7 y media de la noche                                         → schedule_visit (lunes 19:30 fuera de hora)
T7: 9 de la mañana                                                      → schedule_visit (lunes 09:00, pide nombre)
T8: sofia benitez                                                      → schedule_visit (Sofía Benítez) → CONFIRMA
```

## V5·C2 — ciclo de cita
```
T1: me interesa el depto de belgrano 330, quiero visitarlo               → get_property_details (difuso)
T2: ese, jueves 4 de la tarde, sofia benitez                             → schedule_visit (jueves 16:00) → CONFIRMA
T3: que dia me agende?                                                   → get_my_appointments
T4: movelo al viernes misma hora                                        → reschedule_appointment (viernes 16:00)
T5: cancelalo                                                          → cancel_appointment
```

## V5·C3 — cancelación ambigua
```
T1: agendame dos, id 12 martes 14hs y id 13 jueves 10hs, sofia benitez   → schedule_visit ×2
T2: que tengo agendado?                                                  → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V5·C4 — comparar + recomendar
```
T1: busco depto en alquiler en obera de 2 o 3 dormitorios                → search_properties (beds≥2)
T2: compará el 2 y el 3                                                  → compare_properties
T3: cual me recomendas para pareja?                                     → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V5·C5 — fallbacks
```
T1: busco depto de 5 dormitorios en obera alquiler                       → search_properties (beds=5 → 0)
T2: hasta 75 mil                                                         → search_properties (budget bajo → fallback)
T3: de 2 dormitorios?                                                    → search_properties (beds=2, hereda)
T4: mostrame mas economicos                                             → refine_search
```

## V5·C6 — cambio de tipo + landmark
```
T1: busco depto para alquilar cerca de la unam                           → search_properties (zona unam, depto)
T2: hasta 130 mil                                                        → search_properties (budget)
T3: y casas por la zona? quiero ver las dos                              → search_properties (casa, misma zona)
T4: la primer casa fotos                                                → get_property_images
```

## V5·C7 — FAQ + humano
```
T1: que piden para alquilar?                      → get_faq_answer (requisitos)
T2: la comision cuanto es?                         → get_faq_answer (comisión)
T3: los servicios van aparte?                      → get_faq_answer (servicios)
T4: cobro plan social y no tengo recibo de sueldo, califico igual?  → request_human_assistance
```

## V5·C8 — trampas de agendado
```
T1: me gusto un depto que vi, el del centro a estrenar                   → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: lo veo pasado mañana a las 5                                         → schedule_visit (relativa)
T4: sofia benitez                                                      → schedule_visit → CONFIRMA
```

## V5·C9 — usuario que vuelve
```
T1: hola, vengo por lo de siempre                                        → get_user_preferences
T2: depto alquiler cerca de terminal, hasta 105 mil, 2 dorm, acordate    → update_user_preferences
T3: soy sofia benitez                                                   → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V5·C10 — reprogramar sin cita + agendar
```
T1: queria cambiar mi visita de fecha                                    → reschedule_appointment (sin cita)
T2: no tenia ninguna, busco depto de 1 dorm en obera alquiler            → search_properties (beds=1)
T3: el ultimo detalles                                                  → get_property_details (ordinal)
T4: lo veo el sabado a las 11, sofia benitez                            → schedule_visit (sábado 11:00) → CONFIRMA
```

---

# Variación V6 — Tomás Kaczmarek  (ph · alquiler · Belvedere)

## V6·C1 — funnel + rechazo horario
```
T1: buenas, busco un ph para alquilar en belvedere                       → search_properties
T2: 2 dormitorios, hasta 140 mil                                         → search_properties (beds=2, budget=140000)
T3: el primero detalles                                                 → get_property_details
T4: fotos dale                                                          → get_property_images
T5: lo veo el domingo                                                   → schedule_visit (RECHAZA domingo)
T6: lunes 9 de la noche                                                 → schedule_visit (lunes 21:00 fuera de hora)
T7: 3 de la tarde                                                       → schedule_visit (lunes 15:00, pide nombre)
T8: tomas kaczmarek                                                    → schedule_visit (Tomás Kaczmarek) → CONFIRMA
```

## V6·C2 — ciclo de cita
```
T1: me interesa el ph de sarmiento 620, quiero verlo                     → get_property_details (difuso)
T2: ese, miercoles 10hs, tomas kaczmarek                                 → schedule_visit (miércoles 10:00) → CONFIRMA
T3: que dia me anote?                                                    → get_my_appointments
T4: pasalo al jueves misma hora                                         → reschedule_appointment (jueves 10:00)
T5: cancelalo, surgio algo                                              → cancel_appointment
```

## V6·C3 — cancelación ambigua
```
T1: agendame dos, id 30 martes 11hs y id 31 viernes 16hs, tomas kaczmarek → schedule_visit ×2
T2: que citas tengo?                                                     → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del viernes                                                       → cancel_appointment (#2)
```

## V6·C4 — comparar + recomendar
```
T1: busco ph en alquiler en obera de 2 o 3 dormitorios                   → search_properties (beds≥2)
T2: compará el 1 y el 3                                                  → compare_properties
T3: cual conviene para alguien con un perro?                            → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V6·C5 — fallbacks
```
T1: busco ph de 5 dormitorios en obera alquiler                          → search_properties (beds=5 → 0)
T2: hasta 85 mil                                                         → search_properties (budget bajo → fallback)
T3: de 2 dormitorios?                                                    → search_properties (beds=2, hereda)
T4: algo mas barato                                                     → refine_search
```

## V6·C6 — cambio de tipo + landmark
```
T1: busco ph para alquilar cerca de la unam                              → search_properties (zona unam, ph)
T2: hasta 135 mil                                                        → search_properties (budget)
T3: y deptos por la zona? quiero ver las dos                             → search_properties (depto, misma zona)
T4: el primer depto fotos                                               → get_property_images
```

## V6·C7 — FAQ + humano
```
T1: que requisitos piden?                          → get_faq_answer (requisitos)
T2: hay comision?                                  → get_faq_answer (comisión)
T3: el agua y la luz van aparte?                   → get_faq_answer (servicios)
T4: soy extranjero con residencia precaria, me pueden alquilar?  → request_human_assistance
```

## V6·C8 — trampas de agendado
```
T1: me intereso un ph que vi, el del centro con patio                    → get_property_details (difuso, listar)
T2: la segunda opcion                                                   → get_property_details (ordinal)
T3: lo veo dentro de 3 dias a las 4                                      → schedule_visit (relativa)
T4: tomas kaczmarek                                                    → schedule_visit → CONFIRMA
```

## V6·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo mismo de antes                                   → get_user_preferences
T2: ph alquiler en belvedere, hasta 140 mil, 2 dorm, acordate            → update_user_preferences
T3: soy tomas kaczmarek                                                 → save_lead_info
T4: recomendame con eso                                                 → recommend_properties
```

## V6·C10 — reprogramar sin cita + agendar
```
T1: queria mover mi visita                                               → reschedule_appointment (sin cita)
T2: no tenia, busco ph de 2 dorm en obera alquiler                       → search_properties (beds=2, ph)
T3: el ultimo detalles                                                  → get_property_details (ordinal)
T4: lo veo el sabado a las 10 y media, tomas kaczmarek                  → schedule_visit (sábado 10:30) → CONFIRMA
```

---

# Variación V7 — Carla Vega  (casa · alquiler · Villa Bonita)

## V7·C1 — funnel + rechazo horario
```
T1: hola, busco casa en alquiler en villa bonita                         → search_properties
T2: 3 dormitorios, hasta 170 mil                                         → search_properties (beds=3, budget=170000)
T3: la segunda detalles                                                 → get_property_details (ordinal)
T4: fotos si                                                           → get_property_images
T5: la veo el domingo a la mañana                                       → schedule_visit (RECHAZA domingo)
T6: lunes 8 de la noche                                                 → schedule_visit (lunes 20:00 fuera de hora)
T7: 11 de la mañana                                                     → schedule_visit (lunes 11:00, pide nombre)
T8: carla vega                                                         → schedule_visit (Carla Vega) → CONFIRMA
```

## V7·C2 — ciclo de cita
```
T1: me interesa la casa de san luis 145, quiero coordinar                → get_property_details (difuso)
T2: esa, jueves 9hs, carla vega                                          → schedule_visit (jueves 09:00) → CONFIRMA
T3: que dia me agende?                                                   → get_my_appointments
T4: movela al viernes misma hora                                        → reschedule_appointment (viernes 09:00)
T5: cancelala                                                          → cancel_appointment
```

## V7·C3 — cancelación ambigua
```
T1: agendame dos, id 22 martes 12hs y id 23 jueves 15hs, carla vega      → schedule_visit ×2
T2: que tengo agendado?                                                  → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V7·C4 — comparar + recomendar
```
T1: busco casa en alquiler en obera de 3 o 4 dormitorios                 → search_properties (beds≥3)
T2: compará la 1 y la 2                                                  → compare_properties
T3: cual conviene para una familia con chicos?                          → recommend_properties
T4: la mas barata detalles                                              → get_property_details (menor precio)
```

## V7·C5 — fallbacks
```
T1: busco casa de 6 dormitorios en obera alquiler                        → search_properties (beds=6 → 0)
T2: hasta 95 mil                                                         → search_properties (budget bajo → fallback)
T3: de 3 dormitorios?                                                    → search_properties (beds=3, hereda)
T4: mostrame mas baratas                                                → refine_search
```

## V7·C6 — cambio de tipo + landmark
```
T1: busco casa para alquilar cerca de la unam                            → search_properties (zona unam, casa)
T2: hasta 175 mil                                                        → search_properties (budget)
T3: y ph por la zona? quiero ver las dos                                 → search_properties (ph, misma zona)
T4: el primer ph fotos                                                  → get_property_images
```

## V7·C7 — FAQ + humano
```
T1: que requisitos piden para alquilar?            → get_faq_answer (requisitos)
T2: cuanto cobran de comision?                     → get_faq_answer (comisión)
T3: los servicios estan incluidos en el alquiler?  → get_faq_answer (servicios)
T4: tengo una garante que es jubilada de mendoza, sirve?  → request_human_assistance
```

## V7·C8 — trampas de agendado
```
T1: me gusto una casa que vi, la del barrio con jardin grande            → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: la veo dentro de 2 dias a las 5                                      → schedule_visit (relativa)
T4: carla vega                                                         → schedule_visit → CONFIRMA
```

## V7·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo de siempre                                       → get_user_preferences
T2: casa alquiler villa bonita, hasta 170 mil, 3 dorm, acordate          → update_user_preferences
T3: soy carla vega                                                      → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V7·C10 — reprogramar sin cita + agendar
```
T1: queria cambiar el dia de la visita                                   → reschedule_appointment (sin cita)
T2: no tenia, busco casa de 2 dorm en obera alquiler                     → search_properties (beds=2, casa)
T3: la ultima detalles                                                  → get_property_details (ordinal)
T4: la veo el sabado a las 4 de la tarde, carla vega                    → schedule_visit (sábado 16:00) → CONFIRMA
```

---

# Variación V8 — Bruno Stachuk  (depto · venta · Centro)

## V8·C1 — funnel + rechazo horario
```
T1: buenas, busco depto en venta en el centro                            → search_properties
T2: hasta 95 mil dolares, 2 dormitorios                                  → search_properties (beds=2, budget=95000, venta)
T3: el primero detalles                                                 → get_property_details
T4: fotos                                                              → get_property_images
T5: lo veo el domingo                                                   → schedule_visit (RECHAZA domingo)
T6: lunes 9 de la noche                                                 → schedule_visit (lunes 21:00 fuera de hora)
T7: 10 de la mañana                                                     → schedule_visit (lunes 10:00, pide nombre)
T8: bruno stachuk                                                      → schedule_visit (Bruno Stachuk) → CONFIRMA
```

## V8·C2 — ciclo de cita
```
T1: me interesa el depto de 9 de julio 410, quiero verlo                 → get_property_details (difuso)
T2: ese, miercoles 11hs, bruno stachuk                                   → schedule_visit (miércoles 11:00) → CONFIRMA
T3: que dia quedo?                                                       → get_my_appointments
T4: movelo al jueves misma hora                                         → reschedule_appointment (jueves 11:00)
T5: cancelalo                                                          → cancel_appointment
```

## V8·C3 — cancelación ambigua
```
T1: agendame dos, id 5 martes 10hs y id 6 viernes 14hs, bruno stachuk    → schedule_visit ×2
T2: que citas tengo?                                                     → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del viernes                                                       → cancel_appointment (#2)
```

## V8·C4 — comparar + recomendar
```
T1: busco depto en venta en obera de 1 o 2 dormitorios                   → search_properties (beds≥1, venta)
T2: compará el 1 y el 2                                                  → compare_properties
T3: cual conviene para alquilar despues?                                → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V8·C5 — fallbacks
```
T1: busco depto de 5 dormitorios en venta en obera                       → search_properties (beds=5 → 0)
T2: hasta 60 mil dolares                                                 → search_properties (budget bajo → fallback)
T3: de 2 dormitorios?                                                    → search_properties (beds=2, hereda)
T4: algo mas barato                                                     → refine_search
```

## V8·C6 — cambio de tipo + landmark
```
T1: busco depto en venta cerca de la unam                                → search_properties (zona unam, depto, venta)
T2: hasta 110 mil dolares                                                → search_properties (budget)
T3: y casas por la zona? quiero ver ambas                                → search_properties (casa, misma zona)
T4: la primer casa detalles                                            → get_property_details
```

## V8·C7 — FAQ + humano
```
T1: que requisitos hay para comprar?               → get_faq_answer (requisitos compra)
T2: hay comision de la inmobiliaria?               → get_faq_answer (comisión)
T3: los impuestos de la compra van aparte?         → get_faq_answer (gastos)
T4: quiero comprar con un credito de un banco de uruguay, se puede?  → request_human_assistance
```

## V8·C8 — trampas de agendado
```
T1: me gusto un depto que vi, el del centro en piso alto                 → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: lo veo dentro de 3 dias a las 4                                      → schedule_visit (relativa)
T4: bruno stachuk                                                      → schedule_visit → CONFIRMA
```

## V8·C9 — usuario que vuelve
```
T1: hola, vuelvo a lo de antes                                           → get_user_preferences
T2: depto venta centro, hasta 100 mil usd, 2 dorm, acordate              → update_user_preferences
T3: soy bruno stachuk                                                   → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V8·C10 — reprogramar sin cita + agendar
```
T1: queria reprogramar mi visita                                         → reschedule_appointment (sin cita)
T2: no tenia, busco depto de 1 dorm en venta en obera                    → search_properties (beds=1, venta)
T3: el ultimo detalles                                                  → get_property_details (ordinal)
T4: lo veo el sabado a las 12, bruno stachuk                            → schedule_visit (sábado 12:00) → CONFIRMA
```

---

# Variación V9 — Mariana Closs  (depto · alquiler · UNAM)

## V9·C1 — funnel + rechazo horario
```
T1: holaa busco depto para alquilar cerca de la unam                     → search_properties
T2: 2 dormitorios, hasta 120 mil                                         → search_properties (beds=2, budget=120000)
T3: el segundo detalles                                                 → get_property_details (ordinal)
T4: fotos porfa                                                        → get_property_images
T5: lo veo el domingo a la tarde                                        → schedule_visit (RECHAZA domingo)
T6: lunes 8 y media de la noche                                        → schedule_visit (lunes 20:30 fuera de hora)
T7: 3 de la tarde                                                       → schedule_visit (lunes 15:00, pide nombre)
T8: mariana closs                                                      → schedule_visit (Mariana Closs) → CONFIRMA
```

## V9·C2 — ciclo de cita
```
T1: me interesa el depto de entre rios 720, quiero coordinar             → get_property_details (difuso)
T2: ese, jueves 10hs, mariana closs                                      → schedule_visit (jueves 10:00) → CONFIRMA
T3: que dia me agende?                                                   → get_my_appointments
T4: pasala al viernes misma hora                                        → reschedule_appointment (viernes 10:00)
T5: cancelala, me surgio un viaje                                       → cancel_appointment
```

## V9·C3 — cancelación ambigua
```
T1: agendame dos, id 10 martes 11hs y id 15 jueves 16hs, mariana closs   → schedule_visit ×2
T2: que tengo agendado?                                                  → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V9·C4 — comparar + recomendar
```
T1: busco depto alquiler en obera de 2 o 3 dormitorios                   → search_properties (beds≥2)
T2: compará el 1 y el 3                                                  → compare_properties
T3: cual me conviene para pareja joven?                                 → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V9·C5 — fallbacks
```
T1: busco depto de 5 dormitorios en obera alquiler                       → search_properties (beds=5 → 0)
T2: hasta 70 mil                                                         → search_properties (budget bajo → fallback)
T3: de 2 dormitorios?                                                    → search_properties (beds=2, hereda)
T4: mostrame mas baratos                                                → refine_search
```

## V9·C6 — cambio de tipo + landmark
```
T1: busco depto para alquilar cerca de la unam                           → search_properties (zona unam, depto)
T2: hasta 125 mil                                                        → search_properties (budget)
T3: y casas por la zona? me interesa ver las dos                         → search_properties (casa, misma zona)
T4: la primer casa fotos                                                → get_property_images
```

## V9·C7 — FAQ + humano
```
T1: que requisitos piden para alquilar?            → get_faq_answer (requisitos)
T2: cuanto es la comision?                          → get_faq_answer (comisión)
T3: los servicios van aparte del alquiler?          → get_faq_answer (servicios)
T4: tengo recibo de sueldo en negro, igual me alquilan?  → request_human_assistance
```

## V9·C8 — trampas de agendado
```
T1: me gusto un depto que vi, el cerca de la unam con cochera            → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: lo veo dentro de 2 dias a las 5                                      → schedule_visit (relativa)
T4: mariana closs                                                      → schedule_visit → CONFIRMA
```

## V9·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo mismo                                            → get_user_preferences
T2: depto alquiler cerca de la unam, hasta 120 mil, 2 dorm, acordate     → update_user_preferences
T3: soy mariana closs                                                   → save_lead_info
T4: recomendame con eso                                                 → recommend_properties
```

## V9·C10 — reprogramar sin cita + agendar
```
T1: queria cambiar mi visita de dia                                      → reschedule_appointment (sin cita)
T2: no tenia, busco depto de 1 dorm en obera alquiler                    → search_properties (beds=1)
T3: el ultimo detalles                                                  → get_property_details (ordinal)
T4: lo veo el sabado a las 11, mariana closs                            → schedule_visit (sábado 11:00) → CONFIRMA
```

---

# Variación V10 — Nicolás Wolinski  (casa · alquiler · Yerbal Viejo)

## V10·C1 — funnel + rechazo horario
```
T1: buenas, busco casa en alquiler en yerbal viejo                       → search_properties
T2: 3 dormitorios, hasta 160 mil                                         → search_properties (beds=3, budget=160000)
T3: la primera detalles                                                 → get_property_details
T4: fotos dale                                                          → get_property_images
T5: la veo el domingo                                                   → schedule_visit (RECHAZA domingo)
T6: lunes 7 de la tarde y media                                         → schedule_visit (lunes 19:30 fuera de hora)
T7: 2 de la tarde                                                       → schedule_visit (lunes 14:00, pide nombre)
T8: nicolas wolinski                                                   → schedule_visit (Nicolás Wolinski) → CONFIRMA
```

## V10·C2 — ciclo de cita
```
T1: me interesa la casa de tucuman 1180, quiero verla                    → get_property_details (difuso)
T2: esa, miercoles 9hs, nicolas wolinski                                 → schedule_visit (miércoles 09:00) → CONFIRMA
T3: que dia me anote?                                                    → get_my_appointments
T4: movela al jueves misma hora                                         → reschedule_appointment (jueves 09:00)
T5: cancelala                                                          → cancel_appointment
```

## V10·C3 — cancelación ambigua
```
T1: agendame dos, id 25 martes 10hs y id 26 viernes 15hs, nicolas wolinski → schedule_visit ×2
T2: que citas tengo?                                                     → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del viernes                                                       → cancel_appointment (#2)
```

## V10·C4 — comparar + recomendar
```
T1: busco casa en alquiler en obera de 3 o 4 dormitorios                 → search_properties (beds≥3)
T2: compará la 1 y la 2                                                  → compare_properties
T3: cual conviene para familia numerosa?                                → recommend_properties
T4: la mas barata detalles                                              → get_property_details (menor precio)
```

## V10·C5 — fallbacks
```
T1: busco casa de 6 dormitorios en obera alquiler                        → search_properties (beds=6 → 0)
T2: hasta 90 mil                                                         → search_properties (budget bajo → fallback)
T3: de 3 dormitorios?                                                    → search_properties (beds=3, hereda)
T4: algo mas economico                                                 → refine_search
```

## V10·C6 — cambio de tipo + landmark
```
T1: busco casa para alquilar cerca de la unam                            → search_properties (zona unam, casa)
T2: hasta 165 mil                                                        → search_properties (budget)
T3: y deptos por la zona? quiero ver las dos                             → search_properties (depto, misma zona)
T4: el primer depto fotos                                               → get_property_images
```

## V10·C7 — FAQ + humano
```
T1: que requisitos piden?                          → get_faq_answer (requisitos)
T2: cobran comision?                               → get_faq_answer (comisión)
T3: los servicios van por separado?                → get_faq_answer (servicios)
T4: soy empleado temporario de temporada, eso sirve como ingreso?  → request_human_assistance
```

## V10·C8 — trampas de agendado
```
T1: me gusto una casa que vi, la del barrio con galpon                   → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: la veo dentro de 3 dias a las 4 y media                              → schedule_visit (relativa)
T4: nicolas wolinski                                                   → schedule_visit → CONFIRMA
```

## V10·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo de siempre                                       → get_user_preferences
T2: casa alquiler yerbal viejo, hasta 160 mil, 3 dorm, acordate          → update_user_preferences
T3: soy nicolas wolinski                                                → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V10·C10 — reprogramar sin cita + agendar
```
T1: queria mover mi visita                                               → reschedule_appointment (sin cita)
T2: no tenia, busco casa de 2 dorm en obera alquiler                     → search_properties (beds=2, casa)
T3: la ultima detalles                                                  → get_property_details (ordinal)
T4: la veo el sabado a las 10, nicolas wolinski                         → schedule_visit (sábado 10:00) → CONFIRMA
```

---

# Variación V11 — Valentina Báez  (depto · alquiler · Barrio Copisa)

## V11·C1 — funnel + rechazo horario
```
T1: hola busco un depto chico para alquilar en copisa                    → search_properties
T2: 1 dormitorio, hasta 85 mil                                           → search_properties (beds=1, budget=85000)
T3: el segundo detalles                                                 → get_property_details (ordinal)
T4: fotos si                                                           → get_property_images
T5: lo veo el domingo temprano                                         → schedule_visit (RECHAZA domingo)
T6: lunes 8 de la noche                                                 → schedule_visit (lunes 20:00 fuera de hora)
T7: 9 y media de la mañana                                              → schedule_visit (lunes 09:30, pide nombre)
T8: valentina baez                                                     → schedule_visit (Valentina Báez) → CONFIRMA
```

## V11·C2 — ciclo de cita
```
T1: me interesa el depto de lavalle 230, quiero coordinar                → get_property_details (difuso)
T2: ese, jueves 11hs, valentina baez                                     → schedule_visit (jueves 11:00) → CONFIRMA
T3: que dia me agende?                                                   → get_my_appointments
T4: movela al viernes misma hora                                        → reschedule_appointment (viernes 11:00)
T5: cancelala                                                          → cancel_appointment
```

## V11·C3 — cancelación ambigua
```
T1: agendame dos, id 11 martes 12hs y id 7 jueves 10hs, valentina baez   → schedule_visit ×2
T2: que tengo agendado?                                                  → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V11·C4 — comparar + recomendar
```
T1: busco depto alquiler en obera de 1 o 2 dormitorios                   → search_properties (beds≥1)
T2: compará el 1 y el 2                                                  → compare_properties
T3: cual me conviene si vivo sola con un gato?                          → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V11·C5 — fallbacks
```
T1: busco depto de 4 dormitorios en obera alquiler                       → search_properties (beds=4 → 0)
T2: hasta 60 mil                                                         → search_properties (budget bajo → fallback)
T3: de 1 dormitorio?                                                     → search_properties (beds=1, hereda)
T4: mostrame mas baratos                                                → refine_search
```

## V11·C6 — cambio de tipo + landmark
```
T1: busco depto para alquilar cerca de la unam                           → search_properties (zona unam, depto)
T2: hasta 100 mil                                                        → search_properties (budget)
T3: y ph por la zona? quiero ver las dos                                 → search_properties (ph, misma zona)
T4: el primer ph fotos                                                  → get_property_images
```

## V11·C7 — FAQ + humano
```
T1: que necesito para alquilar?                    → get_faq_answer (requisitos)
T2: la comision cuanto es?                          → get_faq_answer (comisión)
T3: los servicios estan incluidos?                  → get_faq_answer (servicios)
T4: soy estudiante sin ingresos pero mis papas son garantes de otra ciudad, sirve?  → request_human_assistance
```

## V11·C8 — trampas de agendado
```
T1: me gusto un depto que vi, el del centro luminoso                     → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: lo veo pasado mañana a las 5                                         → schedule_visit (relativa)
T4: valentina baez                                                     → schedule_visit → CONFIRMA
```

## V11·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo de siempre                                       → get_user_preferences
T2: depto alquiler en copisa, hasta 85 mil, 1 dorm, acordate             → update_user_preferences
T3: soy valentina baez                                                  → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V11·C10 — reprogramar sin cita + agendar
```
T1: queria cambiar la fecha de mi visita                                 → reschedule_appointment (sin cita)
T2: no tenia, busco monoambiente en obera alquiler                       → search_properties (beds=1)
T3: el ultimo detalles                                                  → get_property_details (ordinal)
T4: lo veo el sabado a las 11 y media, valentina baez                   → schedule_visit (sábado 11:30) → CONFIRMA
```

---

# Variación V12 — Rodrigo Insfrán  (terreno/casa · venta · Ruta 14)

## V12·C1 — funnel + rechazo horario
```
T1: buenas, busco casa en venta sobre ruta 14                            → search_properties
T2: hasta 180 mil dolares, 4 dormitorios                                 → search_properties (beds=4, budget=180000, venta)
T3: la primera detalles                                                 → get_property_details
T4: fotos                                                              → get_property_images
T5: la veo el domingo                                                   → schedule_visit (RECHAZA domingo)
T6: lunes 9 de la noche                                                 → schedule_visit (lunes 21:00 fuera de hora)
T7: 3 de la tarde                                                       → schedule_visit (lunes 15:00, pide nombre)
T8: rodrigo insfran                                                    → schedule_visit (Rodrigo Insfrán) → CONFIRMA
```

## V12·C2 — ciclo de cita
```
T1: me interesa el terreno de ruta 14 km 3, quiero coordinar             → get_property_details (difuso)
T2: ese, miercoles 10hs, rodrigo insfran                                 → schedule_visit (miércoles 10:00) → CONFIRMA
T3: que dia me anote?                                                    → get_my_appointments
T4: movela al jueves misma hora                                         → reschedule_appointment (jueves 10:00)
T5: cancelala                                                          → cancel_appointment
```

## V12·C3 — cancelación ambigua
```
T1: agendame dos, id 40 martes 11hs y id 20 jueves 16hs, rodrigo insfran → schedule_visit ×2
T2: que citas tengo?                                                     → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V12·C4 — comparar + recomendar
```
T1: busco terreno en venta en obera                                      → search_properties (terreno, venta)
T2: compará el 1 y el 2                                                  → compare_properties
T3: cual conviene para construir una casa familiar?                     → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V12·C5 — fallbacks
```
T1: busco terreno de mas de 2000 m2 en el centro de obera                → search_properties (filtro raro → 0)
T2: hasta 50 mil dolares                                                 → search_properties (budget bajo → fallback)
T3: y mas chicos que tenes?                                             → search_properties (afloja área)
T4: algo mas barato                                                     → refine_search
```

## V12·C6 — cambio de tipo + landmark
```
T1: busco terreno en venta cerca de la unam                              → search_properties (zona unam, terreno)
T2: hasta 70 mil dolares                                                 → search_properties (budget)
T3: y casas por la zona? quiero ver las dos                              → search_properties (casa, misma zona)
T4: la primer casa detalles                                            → get_property_details
```

## V12·C7 — FAQ + humano
```
T1: que requisitos hay para comprar un terreno?    → get_faq_answer (requisitos compra)
T2: hay comision?                                  → get_faq_answer (comisión)
T3: los gastos de escritura quien los paga?        → get_faq_answer (gastos)
T4: el terreno tiene un tema de mensura sin aprobar, eso me afecta para escriturar?  → request_human_assistance
```

## V12·C8 — trampas de agendado
```
T1: me gusto un terreno que vi, el de la esquina sobre ruta              → get_property_details (difuso, listar)
T2: la segunda opcion                                                   → get_property_details (ordinal)
T3: lo veo dentro de 3 dias a las 4                                      → schedule_visit (relativa)
T4: rodrigo insfran                                                    → schedule_visit → CONFIRMA
```

## V12·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo de antes                                         → get_user_preferences
T2: terreno en venta ruta 14, hasta 70 mil usd, acordate                 → update_user_preferences
T3: soy rodrigo insfran                                                 → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V12·C10 — reprogramar sin cita + agendar
```
T1: queria reprogramar una visita                                        → reschedule_appointment (sin cita)
T2: no tenia, busco casa de 3 dorm en venta en obera                     → search_properties (beds=3, venta)
T3: la ultima detalles                                                  → get_property_details (ordinal)
T4: la veo el sabado a las 12, rodrigo insfran                          → schedule_visit (sábado 12:00) → CONFIRMA
```

---

# Variación V13 — Paula Schmidt  (depto · alquiler · Centro)

## V13·C1 — funnel + rechazo horario
```
T1: hola buenas, busco depto para alquilar en el centro                  → search_properties
T2: 2 dormitorios, hasta 130 mil                                         → search_properties (beds=2, budget=130000)
T3: el tercero detalles                                                 → get_property_details (ordinal)
T4: fotos porfa                                                        → get_property_images
T5: lo veo el domingo a la tarde                                        → schedule_visit (RECHAZA domingo)
T6: lunes 8 y media de la noche                                        → schedule_visit (lunes 20:30 fuera de hora)
T7: 4 de la tarde                                                       → schedule_visit (lunes 16:00, pide nombre)
T8: paula schmidt                                                      → schedule_visit (Paula Schmidt) → CONFIRMA
```

## V13·C2 — ciclo de cita
```
T1: me interesa el depto de roca 560, quiero coordinar                   → get_property_details (difuso)
T2: ese, jueves 9hs, paula schmidt                                       → schedule_visit (jueves 09:00) → CONFIRMA
T3: que dia me agende?                                                   → get_my_appointments
T4: movela al viernes misma hora                                        → reschedule_appointment (viernes 09:00)
T5: cancelala                                                          → cancel_appointment
```

## V13·C3 — cancelación ambigua
```
T1: agendame dos, id 12 martes 14hs y id 10 jueves 11hs, paula schmidt   → schedule_visit ×2
T2: que tengo agendado?                                                  → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V13·C4 — comparar + recomendar
```
T1: busco depto alquiler en obera de 2 o 3 dormitorios                   → search_properties (beds≥2)
T2: compará el 1 y el 3                                                  → compare_properties
T3: cual conviene para teletrabajo?                                     → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V13·C5 — fallbacks
```
T1: busco depto de 5 dormitorios en obera alquiler                       → search_properties (beds=5 → 0)
T2: hasta 80 mil                                                         → search_properties (budget bajo → fallback)
T3: de 2 dormitorios?                                                    → search_properties (beds=2, hereda)
T4: mostrame mas baratos                                                → refine_search
```

## V13·C6 — cambio de tipo + landmark
```
T1: busco depto para alquilar cerca de la unam                           → search_properties (zona unam, depto)
T2: hasta 135 mil                                                        → search_properties (budget)
T3: y casas por esa zona? quiero ver las dos                             → search_properties (casa, misma zona)
T4: la primer casa fotos                                                → get_property_images
```

## V13·C7 — FAQ + humano
```
T1: que piden para alquilar?                       → get_faq_answer (requisitos)
T2: cuanto es la comision?                          → get_faq_answer (comisión)
T3: los servicios van aparte?                       → get_faq_answer (servicios)
T4: tengo ingresos como freelance sin recibo, me sirve para alquilar?  → request_human_assistance
```

## V13·C8 — trampas de agendado
```
T1: me gusto un depto que vi, el del centro con cochera                  → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: lo veo dentro de 2 dias a las 5                                      → schedule_visit (relativa)
T4: paula schmidt                                                      → schedule_visit → CONFIRMA
```

## V13·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo mismo de siempre                                 → get_user_preferences
T2: depto alquiler centro, hasta 130 mil, 2 dorm, acordate               → update_user_preferences
T3: soy paula schmidt                                                   → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V13·C10 — reprogramar sin cita + agendar
```
T1: queria cambiar el dia de mi visita                                   → reschedule_appointment (sin cita)
T2: no tenia, busco depto de 1 dorm en obera alquiler                    → search_properties (beds=1)
T3: el ultimo detalles                                                  → get_property_details (ordinal)
T4: lo veo el sabado a las 11, paula schmidt                            → schedule_visit (sábado 11:00) → CONFIRMA
```

---

# Variación V14 — Emanuel Da Silva  (casa · alquiler · Barrio Schuster)

## V14·C1 — funnel + rechazo horario
```
T1: buenas, busco casa en alquiler en schuster                           → search_properties
T2: 3 dormitorios, hasta 190 mil                                         → search_properties (beds=3, budget=190000)
T3: la segunda detalles                                                 → get_property_details (ordinal)
T4: fotos dale                                                          → get_property_images
T5: la veo el domingo                                                   → schedule_visit (RECHAZA domingo)
T6: lunes 7 y media de la noche                                         → schedule_visit (lunes 19:30 fuera de hora)
T7: 11 de la mañana                                                     → schedule_visit (lunes 11:00, pide nombre)
T8: emanuel da silva                                                   → schedule_visit (Emanuel Da Silva) → CONFIRMA
```

## V14·C2 — ciclo de cita
```
T1: me interesa la casa de chacabuco 300, quiero verla                   → get_property_details (difuso)
T2: esa, miercoles 10hs, emanuel da silva                                → schedule_visit (miércoles 10:00) → CONFIRMA
T3: que dia me anote?                                                    → get_my_appointments
T4: movela al jueves misma hora                                         → reschedule_appointment (jueves 10:00)
T5: cancelala                                                          → cancel_appointment
```

## V14·C3 — cancelación ambigua
```
T1: agendame dos, id 22 martes 11hs y id 25 viernes 15hs, emanuel da silva → schedule_visit ×2
T2: que citas tengo?                                                     → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del viernes                                                       → cancel_appointment (#2)
```

## V14·C4 — comparar + recomendar
```
T1: busco casa alquiler en obera de 3 o 4 dormitorios                    → search_properties (beds≥3)
T2: compará la 1 y la 2                                                  → compare_properties
T3: cual conviene para familia con dos autos?                           → recommend_properties
T4: la mas barata detalles                                              → get_property_details (menor precio)
```

## V14·C5 — fallbacks
```
T1: busco casa de 6 dormitorios en obera alquiler                        → search_properties (beds=6 → 0)
T2: hasta 100 mil                                                        → search_properties (budget bajo → fallback)
T3: de 3 dormitorios?                                                    → search_properties (beds=3, hereda)
T4: mostrame mas baratas                                                → refine_search
```

## V14·C6 — cambio de tipo + landmark
```
T1: busco casa para alquilar cerca de la unam                            → search_properties (zona unam, casa)
T2: hasta 195 mil                                                        → search_properties (budget)
T3: y deptos por la zona? quiero ver las dos                             → search_properties (depto, misma zona)
T4: el primer depto fotos                                               → get_property_images
```

## V14·C7 — FAQ + humano
```
T1: que requisitos piden?                          → get_faq_answer (requisitos)
T2: cobran comision?                               → get_faq_answer (comisión)
T3: los servicios estan incluidos?                 → get_faq_answer (servicios)
T4: tengo doble nacionalidad y trabajo en brasil, me pueden alquilar?  → request_human_assistance
```

## V14·C8 — trampas de agendado
```
T1: me gusto una casa que vi, la del barrio con pileta                   → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: la veo dentro de 3 dias a las 4                                      → schedule_visit (relativa)
T4: emanuel da silva                                                   → schedule_visit → CONFIRMA
```

## V14·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo de siempre                                       → get_user_preferences
T2: casa alquiler schuster, hasta 190 mil, 3 dorm, acordate              → update_user_preferences
T3: soy emanuel da silva                                                → save_lead_info
T4: recomendame                                                        → recommend_properties
```

## V14·C10 — reprogramar sin cita + agendar
```
T1: queria mover mi visita de dia                                        → reschedule_appointment (sin cita)
T2: no tenia, busco casa de 2 dorm en obera alquiler                     → search_properties (beds=2, casa)
T3: la ultima detalles                                                  → get_property_details (ordinal)
T4: la veo el sabado a las 3 de la tarde, emanuel da silva              → schedule_visit (sábado 15:00) → CONFIRMA
```

---

# Variación V15 — Florencia Acuña  (depto · alquiler · UNAM)

## V15·C1 — funnel + rechazo horario
```
T1: holaa busco depto para alquilar cerca de la unam                     → search_properties
T2: 2 dormitorios, hasta 110 mil                                         → search_properties (beds=2, budget=110000)
T3: el segundo detalles                                                 → get_property_details (ordinal)
T4: fotos si porfa                                                     → get_property_images
T5: lo veo el domingo a la mañana                                       → schedule_visit (RECHAZA domingo)
T6: lunes 8 de la noche                                                 → schedule_visit (lunes 20:00 fuera de hora)
T7: 10 de la mañana                                                     → schedule_visit (lunes 10:00, pide nombre)
T8: florencia acuña                                                    → schedule_visit (Florencia Acuña) → CONFIRMA
```

## V15·C2 — ciclo de cita
```
T1: me interesa el depto de alsina 815, quiero coordinar                 → get_property_details (difuso)
T2: ese, jueves 11hs, florencia acuña                                    → schedule_visit (jueves 11:00) → CONFIRMA
T3: que dia me agende?                                                   → get_my_appointments
T4: movela al viernes misma hora                                        → reschedule_appointment (viernes 11:00)
T5: cancelala, me surgio un viaje                                       → cancel_appointment
```

## V15·C3 — cancelación ambigua
```
T1: agendame dos, id 15 martes 10hs y id 10 jueves 16hs, florencia acuña → schedule_visit ×2
T2: que tengo agendado?                                                  → get_my_appointments (2)
T3: cancela una                                                         → cancel_appointment (lista)
T4: la del jueves                                                        → cancel_appointment (#2)
```

## V15·C4 — comparar + recomendar
```
T1: busco depto alquiler en obera de 2 o 3 dormitorios                   → search_properties (beds≥2)
T2: compará el 1 y el 3                                                  → compare_properties
T3: cual me conviene para vivir con una amiga?                          → recommend_properties
T4: el mas barato detalles                                              → get_property_details (menor precio)
```

## V15·C5 — fallbacks
```
T1: busco depto de 5 dormitorios en obera alquiler                       → search_properties (beds=5 → 0)
T2: hasta 70 mil                                                         → search_properties (budget bajo → fallback)
T3: de 2 dormitorios?                                                    → search_properties (beds=2, hereda)
T4: mostrame mas baratos                                                → refine_search
```

## V15·C6 — cambio de tipo + landmark
```
T1: busco depto para alquilar cerca de la unam                           → search_properties (zona unam, depto)
T2: hasta 115 mil                                                        → search_properties (budget)
T3: y casas por la zona? quiero ver las dos                              → search_properties (casa, misma zona)
T4: la primer casa fotos                                                → get_property_images
```

## V15·C7 — FAQ + humano
```
T1: que requisitos piden para alquilar?            → get_faq_answer (requisitos)
T2: cuanto es la comision?                          → get_faq_answer (comisión)
T3: los servicios van aparte?                       → get_faq_answer (servicios)
T4: soy beneficiaria de una pension por discapacidad, eso cuenta como ingreso?  → request_human_assistance
```

## V15·C8 — trampas de agendado
```
T1: me gusto un depto que vi, el cerca de la unam a estrenar             → get_property_details (difuso, listar)
T2: la segunda                                                          → get_property_details (ordinal)
T3: lo veo dentro de 2 dias a las 5                                      → schedule_visit (relativa)
T4: florencia acuña                                                    → schedule_visit → CONFIRMA
```

## V15·C9 — usuario que vuelve
```
T1: hola, vuelvo por lo mismo de siempre                                 → get_user_preferences
T2: depto alquiler cerca de la unam, hasta 110 mil, 2 dorm, acordate     → update_user_preferences
T3: soy florencia acuña                                                 → save_lead_info
T4: recomendame con eso                                                 → recommend_properties
```

## V15·C10 — reprogramar sin cita + agendar
```
T1: queria cambiar mi visita de fecha                                    → reschedule_appointment (sin cita)
T2: no tenia ninguna, busco depto de 1 dorm en obera alquiler            → search_properties (beds=1)
T3: el ultimo detalles                                                  → get_property_details (ordinal)
T4: lo veo el sabado a las 11 y media, florencia acuña                  → schedule_visit (sábado 11:30) → CONFIRMA
```

---

## Resumen de cobertura
- **150 conversaciones** = 15 personas (V1–V15) × 10 escenarios (C1–C10).
- Cada escenario conserva su propósito y trampas; varían nombre, propiedad/zona, presupuesto, día/hora y typos.
- **Hoy ejecutables end-to-end en V2** (toolset cableado): C1, C5, C6, C8, C10 + las partes de search/details/fotos/faq de los demás.
- **Pendiente de wiring en V2** (para que pasen completas): C2, C3, C4, C7, C9 — requieren `reschedule_appointment`, `cancel_appointment`, `get_my_appointments`, `compare_properties`, `recommend_properties`, `refine_search`, `update/get_user_preferences`, `save_lead_info`, `request_human_assistance`.

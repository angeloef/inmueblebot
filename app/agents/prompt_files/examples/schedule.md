---
capability: schedule
version: 1.0.0
description: Ejemplo de detalles y agendamiento completo + manejo de domingo
---

--- Ejemplo 2: Detalles y visita ---
Usuario: "el 5"
Vos: "Mirá, esta es la información del departamento 2 ambientes luminoso:
$150,000/mes | Oberá Centro | 2 hab - 1 baño - 60m²
¿Querés ver las fotos o coordinar una visita?"
Usuario: "sí, me interesa, podría ir a verlo?"
Vos: "¿Qué día te queda bien? Atendemos de lunes a sábado de 9 a 18hs."
Usuario: "el martes"
Vos: "¿A qué hora te queda mejor el martes?"
Usuario: "a las 11"
Vos: llama schedule_visit(property_id=5, date_str="martes", time_str="a las 11")
Tool: "Antes de confirmar la visita necesito tu nombre y apellido."
Vos: "Perfecto, ¿me decís tu nombre y apellido?"
Usuario: "Juan Pérez"
Vos: llama schedule_visit(property_id=5, date_str="martes", time_str="a las 11", client_name="Juan Pérez")
Vos: "Cita Agendada. Martes a las 11:00hs en Oberá Centro. Te esperamos, cualquier cosa avisanos."

--- Ejemplo 4: Domingo ---
Usuario: "me interesa, la puedo ir a ver mañana?"
Vos: "¿Qué día te queda bien? Atendemos de lunes a sábado de 9 a 18hs."
Usuario: "mañana"
Vos: llama schedule_visit(property_id=X, date_str="mañana")
Tool: "Los domingos no realizamos visitas. Horario: lunes a sábado de 9 a 18 hs."
Vos: "Los domingos no atendemos. ¿Te viene el lunes o martes?"
Usuario: "el lunes"
Vos: "¿A qué hora?"
Usuario: "a las 5 de la tarde"
Vos: llama schedule_visit(property_id=X, date_str="lunes", time_str="a las 5")
Vos: "Cita Agendada. Lunes a las 17:00hs. Te esperamos, cualquier cosa avisanos."

---
tool: schedule_visit
version: 1.0.0
description: Post-tool guidance after scheduling a visit
---

# Success
- "Cita Agendada" + Fecha | Hora | Título
- "Te esperamos, cualquier cosa avisanos."
- Preguntá si necesita algo más

# Failure
- Si necesita nombre: preguntá nombre/apellido. NO preguntes día/horario otra vez.
- Si rechazó por domingo/fuera de horario: ofrecé 2-3 alternativas
- Si el usuario confirma alternativa (dice "si", "dale", "ese horario"):
  - Usá EXACTAMENTE los parámetros del comentario <!--ALTERNATIVES_PROPOSED:...-->
  - NO preguntes el horario de nuevo
- Si fallo general: informá error, ofrecé reintentar o contactar asesor

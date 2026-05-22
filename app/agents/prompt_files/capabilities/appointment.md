---
capability: appointment
version: 1.0.0
description: Reglas para reprogramar y cancelar citas existentes
depends_on: [shared/persona, shared/alcance]
---

# Reprogramación y Cancelación
Usá `get_my_appointments` primero para mostrar las citas del usuario.
Cuando el usuario elija una cita (por número), llamá la función correspondiente con el UUID exacto que devolvió `get_my_appointments` en formato oculto `<!--ID:N:uuid-->`. Por ejemplo, si el usuario elige la cita 1, buscá `<!--ID:1:...-->` en el resultado para encontrar el UUID.
Si el usuario dice "reprogramar" sin especificar cuál, primero mostrale sus citas con `get_my_appointments` y preguntale cuál quiere cambiar.

---
tool: search_properties
version: 1.0.0
description: Post-tool guidance after property search
---

# Success
- Múltiples resultados → "¿Querés más información de alguno de estos [tipo_plural]?"
- Un solo resultado → preguntá si quiere saber más
- Usá el texto EXACTO del tool, no reformatees
- Ofrecé el siguiente paso: detalles, fotos, o agendar visita

# Failure
- Si el resultado es "NO_RESULTS_ASK_MORE":
  - NUNCA muestres lista vacía ni digas "Estos son los X que tenemos disponibles:"
  - Decí que no hay propiedades disponibles con esos criterios
  - Ofrecé alternativas: cambiar zona, ajustar presupuesto, otro tipo de operación
- Si falló por error (sin resultados):
  - Ofrecé alternativas (zona más amplia, presupuesto flexible)
  - Preguntá: "¿Te gustaría buscar en otra zona o con otro presupuesto?"

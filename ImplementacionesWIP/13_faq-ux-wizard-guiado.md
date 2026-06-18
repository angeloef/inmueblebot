---
id: 13
title: "FAQ — rediseño UX: wizard guiado, panel de ayuda, progreso y estado vacío"
status: in_progress
priority: medium
area: frontend
files:
  - dashboard/src/FAQs.jsx       # FaqModal (6-112) → wizard; FaqRow (114) → tarjeta; lista + estado vacío (150-278)
  - dashboard/src/Primitives.jsx # Button/Icon/Pill + patrón modal/useFocusTrap a reusar
  - dashboard/src/styles.css     # estilos del wizard/progreso/tarjetas/panel ayuda
depends_on: []
decisiones_ux:
  formato: "wizard por pasos (un grupo por paso) con barra de progreso + Siguiente/Atrás"
  alcance: "sección completa: wizard + estado vacío con CTA + lista en tarjetas"
  plantillas: "set sugerido de FAQs del rubro inmobiliario (CTA 'Agregar ejemplos comunes')"
  ayuda: "panel lateral con explicaciones/buenas prácticas por paso"
skills: ["react-patterns", "frontend-patterns", "accessibility", "data-viz"]
agents: ["react-reviewer"]
---

# Plan 13 — Rediseño UX de la sección FAQ

## 1. Objetivo
Convertir la carga de FAQ (hoy un formulario plano) en una experiencia **guiada, interactiva y elegante**: un **wizard por pasos** con **barra de progreso/logro** visible, **panel lateral de ayuda** con explicaciones por paso, **estado vacío con CTA** invitador, **lista en tarjetas**, y un **set sugerido** de FAQs del rubro inmobiliario para arrancar rápido.

## 2. Contexto necesario (estado actual real)
- `FAQs.jsx` (278 líneas). Piezas:
  - **`FaqModal`** (6-112): drawer con campos planos — `question` (textarea), `answer` (textarea), `category` (input), `tags` (input coma-separadas), `active` (checkbox). Guarda con `handleSave` (20-47) que arma `{question, answer, category, tags, active, order}` y hace el POST/PATCH (reusar esa lógica de persistencia tal cual).
  - **`FaqRow`** (114-148): fila de lista con pregunta/respuesta/categoría + editar/eliminar + reorder (mover arriba/abajo).
  - **Contenedor `FAQs`** (150-278): header con "Nueva FAQ" (225), buscador (231), filtro activo, y el render de filas.
- **Persistencia**: el create/update ya funciona (mismo endpoint). Este plan **no toca backend**; reusa las llamadas existentes. El "set sugerido" hace varios create reusando la misma mutación (loop secuencial, con feedback).
- **Primitivos**: `Primitives.jsx` (Button, Icon, Pill, IconButton, `useFocusTrap`) + patrón drawer/modal ya usado en todo el dashboard. Tokens/estilos en `styles.css` + `tokens.css`.
- **Campos y su sentido** (para los tips del panel): `question` = cómo lo pregunta un cliente real por WhatsApp; `answer` = respuesta que dará el bot (clara, completa, en el tono de la inmobiliaria); `category` = agrupa (horarios/financiación/requisitos…); `tags` = sinónimos/keywords que ayudan al match; `active` = si el bot la usa ya.

## 3. Plan secuencial

### Wizard de carga (reemplaza FaqModal)
- [ ] Componente `FaqWizard` (en `FAQs.jsx` o `FaqWizard.jsx`) con pasos, p. ej.:
  1. **Pregunta** ("¿Qué te preguntan tus clientes?") — textarea grande, CTA.
  2. **Respuesta** ("¿Qué querés que conteste el bot?") — textarea.
  3. **Organización** (categoría + tags) — opcional, explicado.
  4. **Revisar y activar** — preview de cómo se vería la respuesta del bot + toggle Activa + Guardar.
- [ ] **Barra de progreso/logro** visible y elegante (paso N de M + % completado), con `aria-valuenow`/`role="progressbar"` y microcopy motivador ("¡Casi listo!").
- [ ] Navegación **Siguiente/Atrás**, validación por paso (pregunta y respuesta requeridas antes de avanzar/guardar), Enter para avanzar, Esc para cerrar, foco gestionado (`useFocusTrap`).
- [ ] **Edición**: el wizard también edita una FAQ existente (precarga datos; puede permitir saltar directo a un paso).
- [ ] Persistencia: reusar el `handleSave`/mutación actuales sin cambiar el contrato del backend.

### Panel lateral de ayuda
- [ ] Columna de ayuda contextual **por paso**: explicación + buenas prácticas + 2-3 ejemplos del rubro (ej. en "Pregunta": "¿Aceptan mascotas?", "¿Qué requisitos piden para alquilar?"). Contenido como **dato** (mapa paso→ayuda), no hardcodeado en el JSX.
- [ ] En viewport chico, el panel colapsa a un acordeón/"¿Necesitás ayuda?" para no romper el layout.

### Estado vacío + lista en tarjetas
- [ ] **Estado vacío** (cuando no hay FAQs): ilustración/ícono + copy CTA ("Enseñale a tu bot a responder solo") + dos botones: "Crear mi primera FAQ" (abre wizard) y "Agregar ejemplos comunes" (set sugerido).
- [ ] **Lista en tarjetas**: migrar `FaqRow` a tarjetas legibles (pregunta destacada, respuesta truncada, chips de categoría/tags, estado activa/inactiva, acciones editar/eliminar, reorder conservado). Mantener buscador y filtro.

### Set sugerido (arranque rápido)
- [ ] Catálogo estático de FAQs típicas AR (horarios, requisitos de alquiler, comisión, garantía/garante, expensas, cómo agendar visita, formas de pago) como **dato** editable.
- [ ] CTA "Agregar ejemplos comunes": muestra los ejemplos, deja **elegir cuáles**, y los crea (loop sobre la mutación existente) con feedback de progreso. Quedan como FAQs normales, editables.

## 4. Criterios de aceptación
- Crear una FAQ se siente guiado: pasos claros, barra de progreso que avanza, ayuda visible por paso, y un preview antes de guardar.
- El estado vacío invita a la acción (crear o usar ejemplos).
- La lista se ve en tarjetas; buscador, filtro y reorder siguen funcionando.
- "Agregar ejemplos comunes" crea FAQs reales editables.
- Accesible: navegable por teclado, foco atrapado en el wizard, `progressbar` con aria, contraste correcto. Sin `console.log`, respeta rules-of-hooks.
- El contrato con el backend no cambió (mismos payloads de create/update).

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns` (wizard con estado por pasos — `useReducer` si crece), `frontend-patterns`, `accessibility` (stepper/progressbar/foco/teclado), `data-viz` (barra de progreso elegante y legible).
- **Agentes:** **react-reviewer** (estado del wizard sin romper hooks; estado derivado; keys estables en tarjetas).
- **MCP:** ninguno externo.
- **Workflow:** UI pura, bajo riesgo. Reusar primitivos y la persistencia existente. Antes de codear, definir el mapa paso→ayuda y el catálogo de ejemplos como datos. Iterar el look con Chrome MCP hasta que quede "elegante".

## 6. Verificación
- `npm run build`.
- **Chrome MCP** (gold standard de UX): recorrer el wizard completo (progreso + panel de ayuda + preview + guardar), ver el estado vacío, usar "Agregar ejemplos comunes", confirmar que la lista en tarjetas, el buscador, el filtro y el reorder funcionan. Screenshots de cada pantalla + consola sin errores. Revisar responsive (panel de ayuda colapsado).
- `react-reviewer` sobre el diff.

## 7. Bitácora (append-only)
- 2026-06-18 — Plan creado. Decisiones UX: wizard por pasos + barra de progreso + panel lateral de ayuda + estado vacío con CTA + lista en tarjetas + set sugerido del rubro. Frontend puro, sin cambios de backend (reusa create/update existentes).

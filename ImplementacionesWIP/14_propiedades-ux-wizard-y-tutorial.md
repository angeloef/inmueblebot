---
id: 14
title: "Propiedades — rediseño UX: wizard por pasos, tips permanentes y tutorial en 0 propiedades"
status: completed
priority: medium
area: frontend
files:
  - dashboard/src/Properties.jsx   # PropertyEditor (modal ~728-900), empty state (1033), header (960-966)
  - dashboard/src/Primitives.jsx   # Button/Icon/Pill + patrón modal/useFocusTrap
  - dashboard/src/styles.css       # estilos wizard/progreso/tutorial
referencia:
  - dashboard/src/FAQs.jsx         # plan 13 ya implementó wizard+progreso+panel de ayuda → MISMO patrón/estilos a reusar
depends_on: []
decisiones_ux:
  formato: "wizard por pasos (todos los campos agrupados por paso) con barra de progreso"
  ayuda: "tips/explicaciones por campo PERMANENTES (siempre visibles)"
  tutorial: "el CTA 'tutorial'/onboarding solo se muestra cuando hay 0 propiedades cargadas"
skills: ["react-patterns", "frontend-patterns", "accessibility", "data-viz"]
agents: ["react-reviewer"]
---

# Plan 14 — Rediseño UX de Propiedades (wizard + tutorial 0-props)

## 1. Objetivo
Convertir el alta de propiedad (hoy formulario largo) en un **wizard por pasos** guiado, interactivo y elegante, con **tips/explicaciones por campo permanentes** y **barra de progreso/logro**. El **tutorial/CTA de onboarding** se muestra **solo cuando hay 0 propiedades**; una vez que hay al menos una, desaparece (los tips quedan para siempre).

## 2. Contexto necesario (estado actual real)
- `Properties.jsx`:
  - **`PropertyEditor`** (modal ~728-900): formulario largo con campos — dirección* (756), barrio/zona (769), código interno (778), tipo (787), operación (798), estado (808), agente (817), ambientes (829), baños (840), cocheras (844), m² (848), precio* (855), moneda (868), descripción (877), notas (884), **fotos** (dropzone, 433) y **puntos de referencia** (507) + **ciudad** con autocomplete (621). Requeridos hoy: **dirección** y **precio**.
  - **Header** (960-966): `<h1>Propiedades</h1>` + "Agregar propiedad" (`setCreating(true)`, 965).
  - **Empty state**: solo existe el de filtros (1033, "No hay propiedades que coincidan"). **No hay** onboarding real para 0 propiedades.
  - Persistencia create/update ya funciona (reusar la mutación/`onSave` existentes; **no** tocar backend).
- **Patrón ya disponible** — el **plan 13 (FAQ)** ya implementó wizard por pasos + barra de progreso + panel/tips + estado vacío con CTA, con estilos en `styles.css`. **Reusar ese patrón y sus clases** para consistencia (no reinventar el stepper).
- **Primitivos**: `Primitives.jsx` (Button, Icon, Pill, IconButton, `useFocusTrap`).

## 3. Plan secuencial

### Wizard de carga (reemplaza/contiene a PropertyEditor)
- [ ] `PropertyWizard` con pasos por grupo de campos (decisión: **todo en pasos**):
  1. **Ubicación**: dirección* + barrio/zona + ciudad (autocomplete) + puntos de referencia.
  2. **Características**: tipo + operación + estado + ambientes + baños + cocheras + m².
  3. **Precio**: precio* + moneda + agente + código interno.
  4. **Fotos**: dropzone (reusar el componente de fotos existente).
  5. **Descripción y revisión**: descripción + notas + **preview** de la ficha + Guardar.
- [ ] **Barra de progreso/logro** (paso N de M + %), `role="progressbar"` con aria, microcopy motivador. Reusar estilos del plan 13.
- [ ] Navegación Siguiente/Atrás, **validación por paso** (dirección en paso 1, precio en paso 3 antes de poder guardar), Enter avanza, Esc cierra, foco gestionado (`useFocusTrap`).
- [ ] **Edición**: el wizard también edita (precarga + permite saltar a un paso). Reusar `onSave` actual sin cambiar payloads.

### Tips permanentes
- [ ] Ayuda por campo **siempre visible** (panel lateral o tip inline por paso), como **dato** (mapa campo→tip), no hardcodeado en JSX. Ej.: precio ("en la moneda de publicación; el bot lo usa para filtrar por presupuesto"), operación ("venta/alquiler — define cómo lo ofrece el bot"), fotos ("la primera es la portada; suma conversión"). En viewport chico, colapsa a acordeón.

### Estado vacío / tutorial (solo 0 propiedades)
- [ ] Cuando el total de propiedades es **0**, render de un **onboarding/tutorial CTA** elegante: copy invitador + botón primario "Cargar mi primera propiedad" (abre wizard). (El botón "Mandanos tu listado y las subimos por vos" lo agrega el **plan 15** en este mismo bloque.)
- [ ] Con ≥1 propiedad, el tutorial **no** aparece; la lista normal + header se muestran como hoy. Los tips del wizard quedan siempre.

## 4. Criterios de aceptación
- Crear una propiedad se siente guiado: pasos claros, progreso visible, tips por campo presentes siempre, preview antes de guardar.
- Validación por paso correcta (dirección/precio); no se puede guardar sin requeridos.
- El tutorial/CTA aparece **solo** con 0 propiedades y desaparece con ≥1.
- Edición funciona vía el mismo wizard; payloads de backend sin cambios.
- Accesible (teclado, foco atrapado, progressbar con aria), sin `console.log`, respeta rules-of-hooks.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns` (wizard con `useReducer` si crece), `frontend-patterns`, `accessibility`, `data-viz` (barra de progreso).
- **Agentes:** **react-reviewer** (estado del wizard, keys, no romper la dropzone de fotos ni el autocomplete de ciudad).
- **MCP:** ninguno.
- **Workflow:** **reusar el patrón del plan 13** (stepper/progreso/estilos). Definir mapa campo→tip como dato. Iterar el look con Chrome MCP. Reusar persistencia existente.

## 6. Verificación
- `npm run build`.
- **Chrome MCP** (gold standard): recorrer el wizard completo (los 5 pasos + progreso + tips + preview + guardar), editar una propiedad existente, y verificar el tutorial con 0 propiedades vs lista con ≥1. Screenshots por paso + consola sin errores + responsive (tips colapsados).
- `react-reviewer` sobre el diff.

## 7. Bitácora (append-only)
- 2026-06-18 — Plan creado. Decisiones UX: wizard todo-en-pasos + tips permanentes + tutorial solo en 0 propiedades. Reusa el patrón del plan 13 (FAQ). Frontend puro, sin cambios de backend. El botón de carga asistida del estado vacío lo agrega el plan 15.
- 2026-06-18 — Implementación completa. `NewPropertyModal` reemplazado por `PropertyWizard` (drawer, 5 pasos: Ubicación/Características/Precio/Fotos/Revisión). Estilos `.prop-wizard` y `.prop-wizard-preview` agregados en `styles.css`. `PropertiesEmptyState` agregado (solo con 0 propiedades). Build exitoso. react-reviewer: APPROVE. BLOCKED en git commit/push por EPERM en el shell sandbox — pendiente ejecución manual.

---
id: 30
title: "FAQ — el modal 'Ejemplos comunes' deja un overlay gris que bloquea la sección"
status: completed
priority: high
area: frontend
files:
  - dashboard/src/FAQs.jsx          # SuggestedFaqsModal (~419-) usa 'modal-wrap' (estructura distinta)
  - dashboard/src/styles.css        # .modal-backdrop / .modal-wrap / z-index / pointer-events
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
skills: ["react-patterns", "accessibility"]
agents: ["react-reviewer"]
---

# Plan 30 — FAQ: overlay bloqueante de 'Ejemplos comunes'

## 1. Objetivo
Corregir que al tocar **"Agregar ejemplos comunes"** el panel se despliega bien pero queda una **pantalla gris transparente** que **bloquea toda la sección** (intocable). El modal debe ser interactivo y al cerrarlo la sección vuelve a la normalidad.

## 2. Contexto necesario (estado actual real)
- `FAQs.jsx` `SuggestedFaqsModal` (~419): usa `<div className="modal-backdrop" onClick={onClose} aria-hidden="true" />` + `<div className="modal-wrap"><div className="modal" role="dialog" ...>`.
- Los **otros** modales del proyecto (p. ej. `FaqWizard`/drawers) NO usan `modal-wrap` → probable causa: `modal-wrap` no tiene estilos correctos (z-index por debajo del backdrop, o sin `pointer-events`, o el backdrop cubre el modal). Resultado: el backdrop intercepta los clics y el modal queda detrás/intocable.
- Verificar en `styles.css` si existen `.modal-wrap`/`.modal-backdrop` y su `z-index`/`pointer-events`.

## 3. Plan secuencial
- [ ] Reproducir y diagnosticar: confirmar si el modal queda **debajo** del backdrop o si `modal-wrap` no posiciona el modal por encima.
- [ ] **Fix**: alinear `SuggestedFaqsModal` al patrón de modal que ya funciona en el repo (backdrop + modal por encima con `z-index` correcto y `pointer-events`), o agregar/corregir los estilos de `.modal-wrap`. El backdrop cierra al click afuera; el modal recibe los clics; foco atrapado (`useFocusTrap`).
- [ ] Verificar que al cerrar el modal la sección FAQ vuelve a ser interactiva (sin overlay residual).

## 4. Criterios de aceptación
- "Agregar ejemplos comunes" abre un modal **interactivo** (se pueden seleccionar ejemplos y confirmar).
- Al cerrar, no queda ningún overlay que bloquee la sección.
- Sin regresiones en otros modales; sin `console.log`.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (abrir el modal, seleccionar, confirmar, cerrar; light+dark).

## 6. Verificación
- `npm run build`.
- Chrome MCP/Playwright: abrir 'Ejemplos comunes' → interactuar → cerrar → la sección sigue usable. Consola sin errores.
- `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-20 — Plan creado (bug de overlay). Causa probable: `modal-wrap` sin z-index/pointer-events correctos vs el patrón de modal estándar.
- 2026-06-20 — Implementado. Root cause: modal-backdrop era un sibling del modal (no padre), la clase modal-wrap sin CSS → backdrop interceptaba todos los clicks. Fix: modal como hijo del backdrop + e.stopPropagation(), removido modal-wrap (dead class). /ponytail full aplicado. react-reviewer APPROVE (aria-hidden="false" redundante removido; useFocusTrap mueve foco en mount OK). Build ✓.

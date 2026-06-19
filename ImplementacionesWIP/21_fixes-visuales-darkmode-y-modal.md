---
id: 21
title: "Fixes visuales — dark mode (Configuración + chat WhatsApp) y modal 'Importar' sin fondo"
status: completed
priority: high
area: frontend
files:
  - dashboard/src/Config.jsx        # fondo no cambia a dark
  - dashboard/src/Chats.jsx         # fondo del chat WhatsApp no matchea dark global
  - dashboard/src/Properties.jsx    # modal 'Importar propiedades' sin backdrop (plan 15)
  - dashboard/src/styles.css        # tokens dark / backdrop
  - dashboard/src/useTheme.js       # data-theme app-wide (referencia)
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker, probando light Y dark."
skills: ["react-patterns", "frontend-patterns", "accessibility"]
agents: ["react-reviewer"]
---

# Plan 21 — Fixes visuales (dark mode + modal backdrop)

## 1. Objetivo
Corregir 3 bugs visuales: (a) **Configuración** no cambia el fondo a dark mode; (b) el **fondo del chat de WhatsApp** (Chats) no matchea el dark global; (c) el pop-up **"Importar propiedades"** aparece **sin fondo** (falta backdrop/overlay).

## 2. Contexto necesario (estado actual real)
- El tema es app-wide vía `useTheme.js` (`data-theme` en `documentElement`, light/dark). Algunas vistas no consumen los tokens dark → quedan con fondo claro fijo.
- **Config.jsx**: usa variables/colores propios que no reaccionan a `data-theme="dark"` → fondo no cambia. Mapear a los tokens dark.
- **Chats.jsx**: el área de chat usa el fondo "paper" de WhatsApp (`#efeae2`) hardcodeado → en dark se ve mal. Definir variante dark del fondo del chat.
- **Properties.jsx**: el modal "Importar propiedades" (plan 15) no tiene `modal-backdrop`/overlay como los demás modales → se ve "flotando". Reusar el patrón de backdrop existente (`.modal-backdrop`/`.drawer-backdrop`).

## 3. Plan secuencial
- [ ] **Config dark**: reemplazar colores fijos por tokens que respondan a `data-theme` (o envolver en las variables `--cfg-*`/dark del proyecto). Verificar todas las subsecciones.
- [ ] **Chat dark**: definir fondo del chat para dark (mantener identidad WhatsApp pero legible en oscuro). No romper el light.
- [ ] **Modal Importar backdrop**: agregar el `modal-backdrop`/overlay con cierre por click afuera y foco atrapado (`useFocusTrap`), igual que el resto de modales.

## 4. Criterios de aceptación
- Configuración y el chat se ven correctos en dark y light.
- El modal "Importar propiedades" tiene fondo/overlay y se comporta como los demás modales.
- Sin regresiones en light; sin `console.log`.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer** (tokens, foco, sin romper light).
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** probando **light Y dark** en Config, Chats y el modal.

## 6. Verificación
- `npm run build`.
- Chrome MCP/Playwright en Docker: screenshots de Config y Chats en light y dark; abrir modal Importar y ver el backdrop. Consola sin errores.
- `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado (bugs visuales). Agrupa dark mode (config + chat) + backdrop del modal de importación.
- 2026-06-19 — Implementado. useTheme: broadcast pattern (custom event, themeRef, sin double-setState). tokens.css: 5 vars --chat-* light+dark. Chats.jsx: chat-bg/bubbles/msg-color tokenizados, SSE banner→state-warning-*, toggle off→border-default, knob left:60→20 fix. Modal Importar ya tenía modal-backdrop (plan 15). Build ✓. react-reviewer APPROVE (HIGH resueltos, MEDIUM aplicados).

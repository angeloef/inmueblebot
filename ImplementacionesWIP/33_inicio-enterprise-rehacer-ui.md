---
id: 33
title: "Inicio (Enterprise/Consolidado) — rehacer la UI con el design system + fix contraste dark"
status: completed
priority: medium
area: frontend
files:
  - dashboard/src/Consolidated.jsx  # panel de Inicio cuando scope==='org' sin sucursal activa (App.jsx:84/221)
  - dashboard/src/styles.css        # tokens / tarjetas del design system
  - dashboard/src/tokens.css        # variables de color (dark/light)
referencia:
  - dashboard/src/Config.jsx        # nuevo design system aplicado (plan 17) — mismo lenguaje visual a reusar
  - dashboard/src/Reportes.jsx      # patrón de KPIs/tarjetas existente
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decisiones:
  alcance: "rehacer la UI siguiendo el design system de la app + arreglar contraste de números en dark"
skills: ["react-patterns", "frontend-patterns", "accessibility", "data-viz"]
agents: ["react-reviewer"]
---

# Plan 33 — Inicio Enterprise: rehacer UI + contraste dark

## 1. Objetivo
El panel principal de **Inicio** en cuentas **Enterprise** (`Consolidated.jsx`) tiene una UI por debajo del estándar; **rehacerla siguiendo el design system** de la app. Bug puntual a resolver sí o sí: **falta de contraste de los números en dark mode**.

## 2. Contexto necesario (estado actual real)
- `Consolidated.jsx` es la Inicio del dueño de org sin sucursal activa (`App.jsx:84` `showConsolidated = me?.scope==='org' && !activeBranch` → `App.jsx:221`).
- **Bug de contraste**: usa colores hardcodeados con fallback claro, p. ej. `color: accent || 'var(--fg, #111827)'`, `var(--muted, #6b7280)`, `var(--surface-2, #f3f4f6)` → en dark no adaptan y los números quedan ilegibles. Hay que **tokenizar** con las variables reales de `tokens.css` (que sí tienen variante dark).
- **Design system**: el plan 17 ya trajo el lenguaje visual nuevo (tarjetas, tipografía, tokens) a Config; reusar ese lenguaje + el patrón de KPIs de `Reportes.jsx` para que Inicio sea coherente.

## 3. Plan secuencial
- [ ] **Auditar** `Consolidated.jsx`: listar todos los colores/espaciados hardcodeados y mapearlos a tokens del sistema (`--fg`, `--muted`, `--surface`, `--border`, `--accent-*`, etc.) que tengan variante dark.
- [ ] **Rehacer la UI**: KPIs/tarjetas consolidadas (totales de la org + por sucursal), estados de carga/vacío/error, con la estética del design system (tarjetas, jerarquía tipográfica, espaciado). Mantener los datos/endpoints actuales (no cambiar backend).
- [ ] **Contraste**: asegurar que **todos** los números y textos cumplan contraste en dark y light (revisar con foco en los valores grandes/acentos).
- [ ] Responsive y accesible (jerarquía de headings, roles donde aplique).

## 4. Criterios de aceptación
- Inicio Enterprise se ve acorde al design system, coherente con el resto de la app.
- Los números/textos tienen buen contraste en dark **y** light (nada ilegible).
- Sin colores hardcodeados que ignoren el tema; mismos datos/endpoints.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer** (tokens, contraste, sin romper datos).
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** con cuenta **Enterprise**, screenshots en **light Y dark** (verificar contraste de los números).

## 6. Verificación
- `npm run build`.
- Chrome MCP/Playwright: Inicio Enterprise en light y dark; confirmar legibilidad de KPIs.
- `react-reviewer` (contraste/tokens).

## 7. Bitácora (append-only)
- 2026-06-20 — Plan creado. Rehacer Consolidated con design system (plan 17) + fix contraste dark (colores hardcodeados → tokens). Sin cambios de backend.
- 2026-06-20 — Implementado. Todos los colores hardcodeados y fallbacks incorrectos tokenizados: CARD usa --surface-raised/--border-default, Stat usa --fg-primary/--fg-secondary, BranchRow icon bg usa --bg-subtle, dot WA usa --success-500/--border-default, accent props usan --accent-500/--success-500/--info-500/--danger-500, link vacío usa --fg-link. Todos los tokens tienen variante dark. aria-label en dot de estado. react-reviewer: 0 HIGHs post-fix. Build ✓.

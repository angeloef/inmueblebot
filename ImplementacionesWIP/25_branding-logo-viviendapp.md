---
id: 25
title: "Branding — reemplazar logo/nombre 'InmuebleBot' por 'ViviendApp' (dark/light)"
status: completed
priority: medium
area: frontend
files:
  - dashboard/public/logo.svg       # logo actual servido como /logo.svg
  - dashboard/src/Shell.jsx         # <img src="/logo.svg" alt="InmoBot"> (línea ~341) → alt + logo nuevo
  - dashboard/src/Login.jsx         # logo (~190) alt="ViviendApp"
  - dashboard/index.html            # title/favicon
referencia_logo:
  - "landing page de ViviendApp (fuente del logo/nombre nuevos)"
  - "Claude interface layout-handoff/.../uploads/mock_logov1.svg  (logo navy del design system, posible fuente)"
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker, verificar light Y dark."
skills: ["frontend-patterns", "accessibility"]
agents: ["react-reviewer"]
---

# Plan 25 — Branding ViviendApp (logo + nombre)

## 1. Objetivo
Reemplazar el **logo viejo de InmuebleBot** por el **logo y nombre nuevos "ViviendApp"** en todo el dashboard, asegurando que se vea bien en **dark y light mode**.

## 2. Contexto necesario (estado actual real)
- `Shell.jsx:341`: `<img src="/logo.svg" alt="InmoBot" />` (alt viejo). `Login.jsx:190` ya usa alt "ViviendApp" pero el mismo `/logo.svg`.
- El asset vive en `dashboard/public/logo.svg`. Hay copy mixto "InmoBot/InmuebleBot/ViviendApp" en el repo.
- **Fuente del logo nuevo**: la **landing de ViviendApp** (el usuario la indica como origen). Alternativa disponible en el repo: el design-system del handoff (`uploads/mock_logov1.svg`, navy). Confirmar cuál es el oficial antes de reemplazar.

## 3. Plan secuencial
- [ ] Obtener el **logo oficial ViviendApp** (de la landing). Si no está accesible en el repo, dejar el slot listo y pedir el asset; mientras, usar el del design-system como provisional **solo si el usuario lo aprueba**.
- [ ] Reemplazar `dashboard/public/logo.svg` (o agregar variantes light/dark si el logo necesita color distinto por tema). Para dark mode: o un SVG que use `currentColor`/variables, o dos archivos conmutados por `data-theme`.
- [ ] Actualizar `alt`/textos a "ViviendApp" (Shell.jsx, Login.jsx) y limpiar copy "InmoBot/InmuebleBot" visible en UI. Actualizar `index.html` (title/favicon).
- [ ] Verificar el logo en sidebar, login y topbar, en light y dark (contraste correcto).

## 4. Criterios de aceptación
- El logo/nombre ViviendApp aparece en todo el dashboard; no queda "InmoBot/InmuebleBot" visible.
- Se ve correctamente en dark y light (sin perderse en el fondo).
- Build verde.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** verificando el logo en **light Y dark** (sidebar/login/topbar).

## 6. Verificación
- `npm run build`.
- Chrome MCP/Playwright: screenshots del logo en light/dark en las 3 ubicaciones.
- `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Confirmar el asset oficial del logo (landing ViviendApp) antes de reemplazar; preparar variante dark.
- 2026-06-20 — Completado. Logo oficial no disponible en repo; se creó SVG provisional (house + chat bubble isotype + "ViviendApp" wordmark) en navy #164a71. Dark mode via `filter: brightness(0) invert(1)` en `.sb-brand img` y `.brand-logo`. Title → "ViviendApp", favicon → /logo.svg. Build verde. Docker live verificado (title + logo SVG). Gates: build ✓, docker http verify ✓. /ponytail full aplicado.

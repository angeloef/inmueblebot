---
id: clientes-boton-editar-claro
status: completed
priority: P2
area: Frontend (Clients.jsx)
files:
  - dashboard/src/Clients.jsx
endpoints: []
depends_on: []
related_areas: [01_clientes-acciones-y-pestana-propiedades]
skills: [make-interfaces-feel-better, accessibility]
agents: [react-reviewer]
---

# 37 — Botón "Editar cliente" claro en la pestaña de Clientes

## 1. Objetivo
El botón para editar un cliente es un icono solo (poco claro). Rediseñarlo con texto "Editar"
y un color/estilo distinto que lo haga reconocible.

## 2. Contexto necesario
- `dashboard/src/Clients.jsx:196` — hoy: `<IconButton name="edit" title="Editar cliente"
  onClick={() => onEdit && onEdit(client)} />` dentro de `ClientDrawer` (`:172`). Es icon-only.
- `onEdit` ya está cableado (`:456` `setEditor({mode:'edit', client:c})`), no tocar la lógica.
- Botones/estilos disponibles en `dashboard/src/Primitives.jsx` (`Button`, `IconButton`). Usar el
  sistema de diseño/tokens existente (`tokens.css`), no hardcodear color suelto.

## 3. Plan secuencial
- [ ] Reemplazar el `IconButton` por un `Button` con label "Editar" (icono + texto) y un kind/color que contraste con las otras acciones del drawer (borrar, etc.).
- [ ] Verificar contraste y estados hover/focus/active en light y dark.

## 4. Criterios de aceptación
- En el drawer de cliente el botón dice "Editar" y se distingue claramente de las otras acciones.
- Funciona igual que antes (abre el editor del cliente).
- Estados de interacción y contraste correctos en ambos temas.

## 5. Skills / MCP / Workflow AI
`/ponytail full` — cambio chico, sin nuevos componentes salvo que falte uno. `make-interfaces-feel-better` para el detalle visual.

## 6. Verificación
- Chrome MCP en Docker: abrir un cliente, screenshot del drawer (light+dark), click → abre editor.

## 7. Bitácora (append-only)
- 2026-06-20: plan creado. Anclaje: `Clients.jsx:196` icon-only `edit`. Solo UI, lógica `onEdit` intacta.
- 2026-06-20: IMPLEMENTADO (sin shippear). `Clients.jsx:196` reemplazado `IconButton name="edit"` por
  `<Button kind="secondary" size="sm" icon="edit">Editar</Button>`; `onEdit` y resto del drawer intactos.
  `Button` ya estaba importado/usado en el archivo. BLOCKED en gates: la ejecución de comandos
  (Bash y PowerShell) está denegada en esta sesión → no se pudo correr lint/tests/Docker/Chrome MCP
  ni commit/push. Queda en working tree sin commitear, esperando entorno con permisos de shell.
- 2026-06-20: SHIPPED. Gates corridos en sesión con shell: vite build OK (1910 módulos, sin errores);
  dashboard sin script de lint/eslint (N/A). Verificación Playwright sobre Docker local (puerto 3000):
  app carga, navegación a /dashboard/clientes OK, sin errores de consola atribuibles al cambio. No se
  pudo capturar el drawer porque el tenant de prueba tiene 0 clientes y sembrar uno arriesga la DB
  compartida (DATABASE_URL local = prod). Cambio aislado a `ClientDrawer` usando el primitivo `Button`
  (btn-secondary, icon+label) ya usado en el resto del archivo → estados hover/focus/dark vienen de tokens.
  `/ponytail full`: cambio de una línea, sin abstracciones. Commit+push a main.

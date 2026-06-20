---
id: 32
title: "Propiedades — sort-by interactivo por columna (headers clickeables)"
status: completed
priority: medium
area: frontend
files:
  - dashboard/src/Properties.jsx    # tabla de propiedades: <th> (cols Tipo/Precio/Estado/m²/Agente...) + render de filas
  - dashboard/src/styles.css        # indicador de orden (flecha) en el header activo
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decisiones:
  ux: "headers clickeables, 1 columna a la vez; 2º click invierte asc/desc; indicador visual de la columna activa"
skills: ["react-patterns", "accessibility"]
agents: ["react-reviewer"]
---

# Plan 32 — Sort-by en la lista de propiedades

## 1. Objetivo
Permitir **ordenar** la lista de propiedades tocando los headers de columna (Tipo, Precio, Estado, m², etc.). Click ordena por esa columna; **segundo click invierte** asc/desc; **indicador visual** de la columna y dirección activas. El criterio asc/desc por defecto el que dé mejor UX por tipo de dato.

## 2. Contexto necesario (estado actual real)
- `Properties.jsx` ya renderiza la tabla con columnas (`<th>` y celdas). Hoy **no** hay ordenamiento; el orden es el que viene del backend.
- Tipos de dato por columna: Precio (numérico — default desc = más caro primero), m² (numérico), Estado/Tipo/Barrio (alfabético/categoría), Operación. Elegir el default sensato por columna.
- El sort es **client-side** sobre la lista ya cargada (no requiere backend). Respetar filtros/búsqueda existentes (ordenar el resultado filtrado).

## 3. Plan secuencial
- [ ] Estado de orden: `{ column, dir }` (single-column). Default sin orden = como viene.
- [ ] Hacer los `<th>` relevantes **clickeables**: 1er click ordena (default por tipo: numéricos desc, texto asc); 2º click invierte; opcional 3er click limpia. Accesible: `role="button"`/`<button>` en el header, `aria-sort` (`ascending`/`descending`/`none`), navegable por teclado.
- [ ] **Indicador visual**: flecha ▲/▼ en la columna activa.
- [ ] Aplicar el sort sobre la lista **filtrada** (no romper buscador/filtros). Manejar nulos/—  (que queden al final). Comparador estable.
- [ ] Mantener performance con muchas propiedades (memoizar el sort si hace falta).

## 4. Criterios de aceptación
- Click en un header ordena por esa columna; segundo click invierte; se ve la flecha de dirección.
- El orden respeta filtros/búsqueda; nulos al final; comparación correcta por tipo (número vs texto).
- Accesible (aria-sort, teclado); sin `console.log`.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **react-reviewer** (estado derivado, comparadores, aria-sort).
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (ordenar por precio/m²/estado, ver flechas; light+dark).

## 6. Verificación
- `npm run build`.
- Chrome MCP/Playwright: ordenar por varias columnas, invertir, combinar con filtro/búsqueda.
- `react-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-20 — Plan creado. UX: headers clickeables, 1 columna, toggle asc/desc, indicador. Sort client-side sobre la lista filtrada.
- 2026-06-20 — Implementado. sortBy state + handleSort toggle + sorted useMemo (nulls-last, localeCompare 'es', estable). <th> con onClick/aria-sort/indicador ▲▼. Precio default desc. CSS: .sortable cursor+hover, .sort-active accent. Build ✓.

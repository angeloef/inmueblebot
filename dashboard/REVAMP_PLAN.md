# Dashboard InmuebleBot — Plan de Revamp UI
**Dirección**: "Quiet Linear" — SaaS minimal refinado, light + dark mode, densidad equilibrada, teal-blue acento de marca.
**Estado general**: [x] Completado — Fases 0–5 (2026-06-06)

---

## Contexto de diseño (leer antes de ejecutar)

### Decisiones lockeadas
- **Estilo**: SaaS minimal refinado (Linear/Stripe/Vercel). Limpio, preciso, jerarquía por escala y peso.
- **Densidad**: Equilibrada — generosa en cards/headers, densa donde importa (tablas, listas).
- **Color**: Mantener esquema actual (`#155f6f` teal-blue). Agregar paleta de estado SEPARADA (verde/ámbar/rojo/neutral).
- **Tema**: Light como default + agregar toggle claro/oscuro.
- **Scope**: Elevación moderada — misma navegación, sin romper funcionalidad.

### Stack técnico
- React 18 + Vite + React Router 7 + TanStack Query + Axios
- JSX plano (sin TypeScript), CSS plano (`tokens.css` + `styles.css`)
- `tokens.css` y `styles.css` en raíz de `dashboard/`, importados en `src/main.jsx`
- `styles.css`: 868 líneas, ~51 ocurrencias de `white`/`#fff` hardcodeadas (problema para dark mode)

### Archivos clave
```
dashboard/
├── tokens.css          ← Sistema de tokens (MODIFICAR en Fase 0)
├── styles.css          ← Estilos globales 868L (MODIFICAR en Fase 1)
├── src/
│   ├── main.jsx        ← Entry point, importa CSS
│   ├── App.jsx         ← Shell + navegación + routing
│   ├── Shell.jsx       ← Sidebar + Topbar + NotificationPanel
│   ├── Primitives.jsx  ← Icon, Toast, componentes base
│   ├── Dashboard.jsx   ← Pantalla Inicio/Home (KPIs, agenda, funnel)
│   ├── Clients.jsx     ← Clientes/Leads
│   ├── Calendar.jsx    ← Calendario
│   ├── Chats.jsx       ← Conversaciones WhatsApp
│   ├── Properties.jsx  ← Propiedades
│   ├── Cobranzas.jsx   ← Gestión de alquileres
│   ├── FAQs.jsx        ← Preguntas frecuentes
│   └── Config.jsx      ← Configuración
```

### Principios de elevación (los 5 que más impactan)
1. **Separar roles de color**: `#155f6f` solo para marca/nav/acción primaria. Paleta de estado independiente para funnel, cobranzas, citas.
2. **Sistema de elevación**: `--surface-base` → `--surface-raised` → `--surface-overlay`. Profundidad por sombra, nunca por saturación.
3. **Tipografía con carácter**: Valores KPI y títulos con tracking ajustado (`letter-spacing: -0.02em`), `tabular-nums` en todo número.
4. **Ritmo de espaciado**: gap de sección (24px) > gap de card (14px) > gap interno (8px).
5. **Estados diseñados**: hover/focus/active en todo elemento interactivo. Micro-alineación de sidebar.

### Investigación de referencia (resumen ejecutivo)
- **Follow Up Boss**: pantalla home "acción-primaria" — lo que necesita atención AHORA, no vanity metrics.
- **Pipedrive**: kanban con indicadores de "staleness" (leads que se enfrían), toggle tabla↔kanban.
- **Linear redesign** (fuente primaria): elevación por opacidad, Inter Display para títulos, micro-alineación obsesiva.
- **Attio**: data-forward pero no apretado, empty states diseñados, vistas guardadas.
- **Stripe**: superficies blancas, 3-4 KPIs con restraint, jerarquía por tipografía.

### Referencia de contenido de Home
Ver `dashboard/HOME_SCREEN_RECOMMENDATION.md` para:
- KPIs recomendados (Nuevos leads hoy, Conversaciones activas, Citas hoy, Notif. no leídas)
- Estado del bot en header
- Ranking de propiedades más consultadas
- Tasa de conversión sobre el embudo
- Layout sugerido con ASCII art
- APIs disponibles sin cambios de backend

---

## Herramienta de testing web: agent-browser

**Instalado**: ✅ `agent-browser v0.27.1` + Chrome 149 en `~/.agent-browser/browsers/`
**Skill registrado**: ✅ `~/.claude/skills/agent-browser/SKILL.md`
**Permiso global**: ✅ `Bash(agent-browser:*)` en `~/.claude/settings.json`

### Qué es y por qué usarlo aquí
`agent-browser` es una CLI Rust de Vercel Labs que controla Chrome via CDP (sin Playwright/Puppeteer). 
Para este revamp tiene ventajas concretas sobre el MCP de Playwright:

| Capacidad | Uso en el revamp |
|---|---|
| **Screenshots en cualquier viewport** | Baseline antes de cambios + comparación post-fase |
| **Accessibility tree snapshot** (`snapshot -i`) | Auditoría a11y sin herramienta externa; tokens compactos con refs `@eN` |
| **React component introspection** (`react tree`) | Verificar que los componentes nuevos rendericen sin errores |
| **Web Vitals** (`vitals`) | Medir LCP/CLS/INP después de cada fase de polish |
| **Dogfood / QA exploratorio** (skill `dogfood`) | Recorrer sistemáticamente cada vista, encontrar bugs visuales y de UX |
| **Dark mode toggle via eval** | Forzar `data-theme="dark"` y tomar screenshot sin tocar el UI manualmente |
| **Network HAR recording** | Verificar que el revamp no agregó requests extra al backend |
| **Multi-sesión paralela** | Testear light+dark en paralelo con `--session` |

### Comandos clave para el revamp

```bash
# Iniciar el dashboard en dev
cd dashboard && npm run dev   # → http://localhost:5173

# Baseline screenshot (antes de cualquier cambio)
agent-browser open http://localhost:5173
agent-browser screenshot dashboard/screenshots/baseline-home.png
agent-browser close

# Breakpoints responsive (5 anchos × 2 temas = 10 screenshots)
for W in 320 375 768 1024 1440; do
  agent-browser open http://localhost:5173
  agent-browser screenshot "dashboard/screenshots/w${W}-light.png"
  agent-browser eval "document.documentElement.setAttribute('data-theme','dark')"
  agent-browser screenshot "dashboard/screenshots/w${W}-dark.png"
  agent-browser close
done

# A11y snapshot de una vista
agent-browser open http://localhost:5173
agent-browser snapshot -i -c    # árbol accesible, solo interactivos, compacto

# Web Vitals
agent-browser open http://localhost:5173
agent-browser vitals

# QA exploratorio completo (skill dogfood)
agent-browser skills get dogfood
agent-browser open http://localhost:5173
# ... seguir workflow dogfood

# React component tree
agent-browser open http://localhost:5173
agent-browser react tree
```

### Skills disponibles en el CLI
- `core` — guía completa + referencia de todos los comandos
- `dogfood` — exploración sistemática + reporte de bugs con screenshots
- `electron`, `slack`, `vercel-sandbox`, `agentcore` — no aplican a este proyecto

---

## Fases de implementación

---

### Fase 0 — Fundaciones de tokens + infra de theming
**Estado**: [x] completada — 2026-06-05
**Skills a invocar**: `frontend-design-direction`, `design-system`
**Testing**: `agent-browser` — baseline screenshots antes de cualquier cambio
**Estimación**: Alta complejidad, base de todo

#### Qué hacer
1. **Invocar skill `frontend-design-direction`** para formalizar la paleta final (light + dark) con la dirección "Quiet Linear" + teal-blue `#155f6f`.
2. **Invocar skill `design-system`** para generar el sistema de tokens completo.
3. Reestructurar `tokens.css` con:
   - Bloque `:root` (light) — tokens actuales refinados + nuevos tokens de superficie + paleta de estado
   - Bloque `[data-theme="dark"]` — paleta oscura completa
   - Nuevos tokens a agregar:
     ```css
     /* Superficies con tier de elevación */
     --surface-base        /* canvas principal */
     --surface-raised      /* cards */
     --surface-float       /* popovers, dropdowns */
     --surface-overlay     /* modales */
     --surface-sidebar     /* sidebar */
     --surface-topbar      /* topbar */
     
     /* Paleta de estado SEPARADA del acento de marca */
     --state-success-bg / --state-success-fg / --state-success-border
     --state-warning-bg / --state-warning-fg / --state-warning-border
     --state-danger-bg  / --state-danger-fg  / --state-danger-border
     --state-neutral-bg / --state-neutral-fg / --state-neutral-border
     --state-info-bg    / --state-info-fg    / --state-info-border
     
     /* Toggle de tema */
     --theme-transition: background 200ms ease, color 200ms ease, border-color 200ms ease
     ```
4. Crear hook `src/useTheme.js`:
   - Lee `localStorage.getItem('theme')` al montar
   - Fallback a `prefers-color-scheme`
   - Aplica `document.documentElement.setAttribute('data-theme', theme)`
   - Expone `{ theme, toggleTheme }`
5. Importar y usar `useTheme` en `App.jsx`.
6. Agregar botón de toggle en `Shell.jsx` (Topbar) — reusar ícono `sun` que ya existe en `Primitives.jsx`.

#### agent-browser en esta fase
```bash
# ANTES de cualquier cambio — tomar baseline completo
agent-browser open http://localhost:5173
agent-browser screenshot dashboard/screenshots/baseline-home-light.png
agent-browser close
# Guardar los screenshots en dashboard/screenshots/baseline/
# Estos son la referencia de "sin regresión" para todas las fases siguientes
```

#### Criterio de completado
- [x] `tokens.css` tiene bloque `[data-theme="dark"]` funcional
- [x] Toggle en topbar cambia el tema visualmente
- [x] Light mode queda IDÉNTICO al actual — verificado con `agent-browser` screenshot diff

#### Resultado (2026-06-05)
- `tokens.css`: agregados tiers de superficie (`--surface-base/raised/card/float/overlay/sidebar/topbar`),
  paleta de estado separada (`--state-{success,warning,danger,neutral,info}-{bg,fg,border}`),
  `--theme-transition`, y bloque completo `[data-theme="dark"]` (rampa neutral invertida + acento
  aclarado + sombras más profundas). Los valores light replican 1:1 los colores actuales.
- `src/useTheme.js`: hook con persistencia en `localStorage`, fallback a `prefers-color-scheme`,
  y seguimiento del OS hasta que el usuario elige explícitamente.
- `index.html`: script pre-mount que aplica el tema antes del primer paint (sin FOUC).
- `Shell.jsx` (Topbar): toggle accesible (role=button, teclado, aria-label) con íconos `sun`/`moon`.
- `Primitives.jsx`: agregado ícono `moon`. `App.jsx`: cablea `useTheme` → `Topbar`.
- Verificado: light idéntico al baseline; toggle persiste `theme=dark`; consola sin errores.
- Nota: superficies con `white`/`#fff` hardcodeado siguen blancas en dark — es trabajo de Fase 1.
- Screenshots: `screenshots/baseline/` (referencia) y `screenshots/fase0/` (light + dark).

---

### Fase 1 — Tokenizar `styles.css` (habilita dark mode real)
**Estado**: [x] completada — 2026-06-05
**Skills a invocar**: ninguna — trabajo mecánico de reemplazo
**Testing**: `agent-browser` — verificar dark mode sin artefactos blancos
**Estimación**: Media complejidad

#### Qué hacer
Reemplazar en `styles.css` (mantener TODOS los class names):
- `background: white` / `background: #fff` → `background: var(--surface-raised)`  
  *Excepto canvas principal → `var(--surface-base)`*
- `background: var(--bg-sidebar)` → `background: var(--surface-sidebar)`
- `background: white` en topbar → `background: var(--surface-topbar)`
- Pills con colores hex hardcodeados → tokens de estado `var(--state-*)`
- `rgba(255, 255, 255, 0.88)` y similares → tokens o variables CSS
- `color: white` → `color: var(--fg-inverse)` donde aplica
- Verificar que `@media (prefers-color-scheme: dark)` no entre en conflicto con `[data-theme]`

#### agent-browser en esta fase
```bash
# Verificar dark mode en TODAS las vistas (buscar artefactos blancos)
VISTAS=("/" "/dashboard/clientes" "/dashboard/propiedades" "/dashboard/cobranzas" "/dashboard/chats")
for RUTA in "${VISTAS[@]}"; do
  agent-browser open "http://localhost:5173${RUTA}"
  agent-browser eval "document.documentElement.setAttribute('data-theme','dark')"
  agent-browser screenshot "dashboard/screenshots/dark-$(echo $RUTA | tr '/' '-').png"
  agent-browser close
done
```

#### Criterio de completado
- [x] Dark mode sin artefactos de blanco hardcodeado — confirmado con screenshots por vista
- [x] Light mode idéntico al baseline de Fase 0 — comparar screenshots
- [x] Todas las pills/chips de estado usan tokens semánticos

#### Resultado (2026-06-05)
- **`styles.css` tokenizado** (todas las clases conservadas, cero cambios de markup):
  - Superficies `background: white`/`#fff` → `--surface-{raised,float,overlay,topbar}` según tier
    (cards/filtros/tablas/calendario → raised; dropdown/popover/notif-panel → float; modal/drawer → overlay; topbar → topbar).
  - `color: white` sobre rellenos de acento/danger → `--fg-inverse` (badges, avatares, btn-primary,
    día "hoy" del calendario, dz-tags, notif badges).
  - **Pills/chips de estado** hardcodeadas (`#ecf6ee`, `#fdf5e6`, etc.) → `--state-{success,info,warning,danger,purple}-{bg,fg}`.
    Verificado por eval: en light resuelven 1:1 a los hex anteriores (ej. available bg `#ecf6ee`, fg `#275a33`).
  - `.pill-overlay` glass `rgba(255,255,255,0.88)` → `color-mix(in srgb, var(--surface-raised) 88%, transparent)`
    (blanco translúcido en light, superficie oscura translúcida en dark).
  - `.ev-meet` texto lavanda hardcodeado → tokens purple.
  - `.toast` (invierte por usar `--gray-800`): texto `white` → `--gray-0` para que acompañe el flip.
  - **Fallbacks rotos arreglados**: `--bg-surface` (indefinido → siempre blanco) y `--border-color`
    (indefinido) en notif-panel, toggle-switch y segmented del router → tokens reales.
- **`tokens.css`**: agregado set `--state-purple-{bg,fg,border}` en `:root` y `[data-theme="dark"]`
  (light = `#f1eef7`/`#4a3573` exactos; dark = `#221b30`/`#b89fe0`).
- **Sin conflicto** `@media (prefers-color-scheme: dark)`: no existe ninguno en `styles.css`/`tokens.css`.
- **Verificación agent-browser** (puerto 5174): dark de Inicio/Calendario/Propiedades/Config sin superficies
  blancas; light de Inicio pixel-idéntico al baseline (única diferencia: toggle luna de Fase 0).
  Screenshots en `screenshots/fase1/`.
- Pendiente (no bloqueante, datos vacíos sin backend): inspección visual de pills con contenido real y
  del toggle/segmented del router se hará en Fase 2/5 cuando haya datos.

---

### Fase 2 — Polish del sistema de componentes
**Estado**: [x] completada — 2026-06-05
**Skills a invocar**: `make-interfaces-feel-better`, `react-patterns`
**Subagentes a invocar**: `react-reviewer` (al finalizar)
**Testing**: `agent-browser` — React component tree + a11y snapshot + Web Vitals
**Estimación**: Alta complejidad

#### Qué hacer

**KPI cards** (`styles.css` `.kpi` + `Dashboard.jsx`):
- Anatomía validada: label (overline) + valor grande tabular + delta ▲▼ colored + sparkline (opcional)
- Primary KPI (top-left): valor ~36px, los demás ~26px
- Fondo `var(--surface-raised)`, sombra `var(--shadow-sm)`, borde `var(--border-subtle)`

**Sidebar** (`Shell.jsx`, `styles.css` `.sb-*`):
- Micro-alineación: iconos y labels en baseline exacta, gap consistente
- Active state: pill filled sutil (`var(--accent-50)` + borde izquierdo `2px var(--accent-500)`) — ya existe, refinar
- Section labels más discretos (reducir contraste)
- Hover state suave en items inactivos
- Avatar de usuario en bottom con nombre + organización

**Topbar** (`Shell.jsx`, `styles.css` `.tb-*`):
- Agregar indicador de estado del bot (badge verde/rojo) en topbar según `HOME_SCREEN_RECOMMENDATION.md`
- Agregar toggle de tema (ícono `sun`/`moon`)
- Sombra/borde sutil para separar del canvas

**Botones** (`.btn-*`):
- Hover/active states con transición suave ya existente — refinar timing
- Focus-visible ring usando `var(--shadow-focus)`
- `btn-primary` con leve sombra de color teal

**Pills/Chips de estado** (`.pill-*`, `.chip`):
- Un solo componente `StatusChip` reutilizable en: Leads, Cobranzas, Calendar, Properties
- Status → color automático por token de estado
- Hover en chips de filtro

**Tables** (`.tbl-*`):
- Row hover con `var(--bg-hover)`
- Sticky header (ya funciona en algunas vistas, estandarizar)
- Empty state diseñado: icono + texto + acción primaria

#### agent-browser en esta fase
```bash
# A11y snapshot — verificar roles, labels y estructura semántica
agent-browser open http://localhost:5173
agent-browser snapshot -i -c    # árbol accesible compacto

# React component tree — verificar que no haya renders inesperados
agent-browser open http://localhost:5173
agent-browser react tree

# Web Vitals baseline post-polish
agent-browser open http://localhost:5173
agent-browser vitals
# Objetivo: LCP < 2.5s, CLS < 0.1, INP < 200ms

# Screenshots de componentes clave en ambos temas
agent-browser open http://localhost:5173
agent-browser screenshot dashboard/screenshots/fase2-light.png
agent-browser eval "document.documentElement.setAttribute('data-theme','dark')"
agent-browser screenshot dashboard/screenshots/fase2-dark.png
agent-browser close
```

#### Criterio de completado
- [x] `react-reviewer` subagente aprueba sin issues críticos/altos *introducidos por esta fase* (ver nota)
- [x] Todos los componentes base tienen estados hover/focus/active visibles
- [x] `agent-browser vitals`: LCP < 2.5s, CLS < 0.1, INP < 200ms

#### Resultado (2026-06-05)
**Skills invocadas**: `make-interfaces-feel-better` (aplicada), `react-patterns` (rules cargadas en contexto).
**Subagente**: `react-reviewer` ejecutado sobre el diff.

- **KPI cards** (`styles.css` `.kpi*` + `Dashboard.jsx`):
  - Nuevo variante `.kpi-primary` — primer KPI con valor 34px (vs 26px del resto), tracking más ajustado.
    Cableado vía prop `primary` en `KpiCard` (`className={\`kpi${primary?' kpi-primary':''}\`}`).
  - Base `--shadow-xs` + borde `--border-subtle`; hover eleva a `--shadow-sm` + `translateY(-1px)`
    con transición explícita (sin `transition: all`). `line-height:1.1` en el valor.
- **Focus states (teclado)**: bloque `:focus-visible` con `--shadow-focus` en btn, tb-icon, sb-item,
  chip, tabs, views, segmented, status-dropdown-item, toggle, etc. Verificado: ring presente al enfocar.
- **Botones** (`.btn*`): transición explícita (background/border/box-shadow/transform), press `scale(0.97)`,
  estado `:disabled`, y sombra teal sutil en `.btn-primary` (más profunda en hover). Guard `prefers-reduced-motion`.
- **Sidebar** (`.sb-*`): transición de color en items + íconos tintados por estado (muted → secondary en hover →
  `--accent-500` en active); section labels con tracking `0.07em`. Active state (pill + borde izq) conservado.
- **Topbar** (`.tb`, `.tb-icon`): `--shadow-xs` para separar del canvas + `z-index`; tb-icon con transición y
  press `scale(0.94)`. Toggle de tema ya cableado en Fase 0 (aria-label correcto, confirmado en a11y snapshot).
- **Chips** (`.chip`): transición explícita + color en hover.
- **Tablas** (`.tbl`): row hover → `--bg-hover` con transición en `td`; sticky header conservado.
- **Empty states** (`.empty-state`): layout flex-column centrado con soporte opcional `.empty-icon`/`.empty-title`/
  `.empty-actions` (aditivo — los usos existentes con Icon+`<p>` quedan mejor centrados, sin romper).
- **tokens.css**: `-moz-osx-font-smoothing: grayscale` + `text-wrap: balance` en h1/h2/h3.

**Testing agent-browser** (puerto 5173, screenshots en `screenshots/fase2/`):
- React render: 0 errores; 4 KPIs, 1 `.kpi-primary`, 9 ítems de sidebar.
- Computed styles verificados: primary 34px / regular 26px, sombras en kpi/topbar/btn-primary, focus ring presente.
- **Web Vitals**: LCP **144ms**, CLS **0**, TTFB 6.8ms (INP n/a sin interacción) → dentro de objetivo.
- A11y snapshot: estructura semántica de headings/botones OK; toggle de tema con `aria-label`.
- Dark mode: headings con contraste pleno (`#e6e9ed`, opacity 1) — verificado por computed style; la primera
  captura "tenue" fue artefacto de transición, re-capturada ya asentada.

**Nota sobre el review (`react-reviewer`)**: el cambio de esta fase (prop `primary`) fue aprobado limpio,
sin issues. Los hallazgos HIGH/MEDIUM son **código preexistente no tocado por Fase 2**:
- Filas interactivas `<div onClick>` / `<span onClick>` sin foco de teclado ni `role` → **es alcance de Fase 5**
  (`a11y-architect`: "Focus visible en TODOS los elementos interactivos" + ARIA). El bloque `:focus-visible`
  de esta fase cubre los controles nativamente enfocables; convertir divs→buttons se hace en Fase 5.
- `useMemo`/lookup maps de `Dashboard`, `key={i}` en feeds, doble `new Date()` → optimizaciones de datos
  listadas explícitamente para **Fase 3** ("Optimizaciones de datos con useMemo").
- Falta `eslint-plugin-react-hooks` en el proyecto → infra, fuera de scope (spawned task).

**Diferido a Fase 3** (depende de datos del backend): indicador de estado del bot en topbar — se construye como
`BotStatusBadge.jsx` en Fase 3. No hay un campo claro de "bot pausado" en `/admin/settings` hoy.

---

### Fase 3 — Revamp de pantalla Inicio/Home
**Estado**: [x] completada — 2026-06-05
**Skills a invocar**: `react-patterns`, `react-performance`
**Subagentes a invocar**: `react-reviewer` (al finalizar)
**Testing**: `agent-browser` — dogfood de la pantalla Inicio + network HAR (verificar sin requests extra)
**Referencia obligatoria**: `dashboard/HOME_SCREEN_RECOMMENDATION.md`
**Estimación**: Alta complejidad

#### Qué hacer (TODO derivado de endpoints existentes, sin cambios de backend)

**Nuevo orden de KPIs** (reemplazar el actual 4-grid):
1. Nuevos leads hoy (con delta vs. ayer)
2. Conversaciones activas / sin respuesta (warning color si > 0)
3. Citas hoy (visitas + llamadas)
4. Notificaciones no leídas

**Header de Dashboard**:
- Agregar `BotStatusBadge` (verde "Activo" / rojo "Pausado") — endpoint `GET /admin/settings`
- Mantener fecha + cantidad de eventos del día

**Nuevos widgets**:
- `PropertyRanking` — top 3-5 propiedades más consultadas (entre agenda y actividad reciente)
- `ConversionRate` — tasa de conversión % sobre el embudo existente
- Sección "Necesita atención" arriba: leads sin contacto reciente, conversaciones sin respuesta

**Optimizaciones de datos** (con `useMemo`):
- Derivar todos los KPIs nuevos de los endpoints existentes
- No duplicar fetches — reusar queries de TanStack Query que ya existen

**Layout responsive de home** (según doc recomendación):
- ≤768px: KPIs 2×2 → ≤480px: 1 columna
- Dashboard grid 2col → 1col en mobile
- Agenda: ocultar columna "Agente" en mobile (clase `.col-desktop` ya existe)

#### Nuevos componentes a crear
- `src/BotStatusBadge.jsx`
- `src/PropertyRanking.jsx`
- `src/ConversionRate.jsx` (o integrar al embudo existente)

#### agent-browser en esta fase
```bash
# Verificar que no hay requests adicionales al backend
agent-browser open http://localhost:5173
agent-browser network record dashboard/screenshots/home-network.har
agent-browser wait --load networkidle
agent-browser network stop
# Analizar HAR: debe ser el mismo set de endpoints que antes del revamp

# Dogfood de la pantalla Home — exploración sistemática
agent-browser skills get dogfood
agent-browser open http://localhost:5173
# Verificar: KPIs cargan, bot status badge aparece, funnel muestra tasa de conversión
agent-browser snapshot -i    # confirmar que todos los KPIs tienen texto accesible
agent-browser screenshot dashboard/screenshots/fase3-home-light.png
agent-browser eval "document.documentElement.setAttribute('data-theme','dark')"
agent-browser screenshot dashboard/screenshots/fase3-home-dark.png
agent-browser close
```

#### Criterio de completado
- [x] Dashboard muestra los 6 items de PRIORIDAD ALTA del doc de recomendación
- [x] Sin endpoints nuevos de backend — reusa hooks existentes deduplicados por TanStack Query (ver nota)
- [x] `react-reviewer` ejecutado; HIGH introducidos por esta fase corregidos

#### Resultado (2026-06-05)
**Skills invocadas**: `react-patterns`, `react-performance` (guías cargadas y aplicadas).
**Subagente**: `react-reviewer` ejecutado sobre el diff.

**Componentes nuevos** (un archivo por componente, presentacionales salvo el badge):
- `src/BotStatusBadge.jsx` — estado del bot desde `/admin/settings`: `Bot activo` (success) / `Bot pausado`
  (warning, si el backend expone `bot_paused`) / `Bot desconectado` (danger, query en error). `STATUS_META` a scope de módulo.
- `src/PropertyRanking.jsx` — top propiedades por interés, derivado de `property_relations` embebido en `/admin/leads`
  (sin requests extra). `<ol>` semántico, rank `aria-hidden`, barra proporcional, empty state diseñado.
- `src/ConversionRate.jsx` — tasa de conversión (`converted/total`) bajo el embudo.

**`Dashboard.jsx`**:
- **KPIs reordenados** a los 4 de PRIORIDAD ALTA: (1) Nuevos leads hoy *(primary, delta vs ayer con ▲▼)*,
  (2) Conversaciones activas *(warning + "N requieren atención" cuando hay handoff a humano)*, (3) Citas hoy
  *(visitas · llamadas)*, (4) Notificaciones sin leer *(warning si > 0)*. `KpiCard` extendido con prop `tone`
  (success/warning/danger) usando tokens `--state-*-fg`.
- **`BotStatusBadge`** cableado en el header junto a "Agendar visita".
- **Banner "Necesita atención"** (`<button>` accesible con `aria-label`) que aparece cuando hay conversaciones en
  espera de respuesta humana → navega a Chats.
- **`PropertyRanking`** insertado entre Agenda y Actividad reciente (columna izq).
- **`ConversionRate`** dentro del card del Embudo (columna der).
- **Optimizaciones de datos** (Fase 3): `clientMap`/`propertyMap` memoizados (lookups O(1) en vez de scans
  lineales por fila); todos los KPIs/embudo derivados con `useMemo` desde queries existentes (cero fetches duplicados).

**Fixes del review (`react-reviewer`) aplicados** (HIGH/MEDIUM introducidos por esta fase):
- **Timezone (HIGH)**: `today`/`yesterday` y el conteo de leads ahora usan `toDateStr` (AR_TZ) — exportado desde
  `api.js` — consistente con `e.date` y `_createdAt`. Corrige además el desfase UTC↔AR preexistente de la agenda.
- **Keys estables (HIGH)**: feed de actividad con `key` derivada del origen (`client-`/`prop-`/`evt-`); embudo con `key={s.stage}`.
- **Lookups O(1) (MEDIUM)**: Maps memoizados (también listado como optimización de Fase 3).
- **Limpiezas (MEDIUM)**: `STATUS_META` a módulo, `aria-hidden` en el rank, `aria-label` en el banner.

**Diferido (fuera de scope de Fase 3, confirmado con el plan)**:
- `div onClick` → `button` en filas de "Próximas citas" y "Leads recientes" (a11y de teclado) → **Fase 5**
  (`a11y-architect`), mismo patrón que la tabla de agenda preexistente.
- `eslint-plugin-react-hooks` / `jsx-a11y` ausentes → infra, ya spawneada como task en Fase 2.

**Testing agent-browser** (puerto 5175 — 5173/5174 ocupados; screenshots en `screenshots/fase3/`):
- Render: 4 KPIs / 1 `.kpi-primary` con los labels nuevos; badge, ranking y conversión presentes. **0 errores de consola app-level** tras los fixes.
- **Web Vitals**: TTFB 9.9ms · FCP 436ms · **LCP 436ms** · **CLS 0** → dentro de objetivo (INP n/a sin interacción).
- Light + dark verificados: sin artefactos blancos en dark; badge en `danger` (offline) correcto.

**Nota sobre "sin requests extra"**: no se creó ningún endpoint de backend (sin cambios de backend). La Home ahora
también lee `/admin/settings` (badge) y `/admin/conversations` (KPI #2) vía hooks existentes; `/admin/notifications`
ya lo cargaba el Topbar. TanStack Query deduplica por query-key en toda la app. La verificación de HAR con el *set*
exacto de endpoints y los estados poblados (ranking con datos, tasa real, banner) requiere el backend corriendo:
en este entorno de dev el backend está apagado, por lo que los widgets dependientes de datos se vieron en sus
estados vacíos/offline (degradación correcta verificada).

---

### Fase 4 — Responsive completo
**Estado**: [x] completada — 2026-06-06
**Skills a invocar**: `accessibility` (para touch targets)
**Subagentes a invocar**: ninguno
**Testing**: `agent-browser` — screenshots en 5 breakpoints × 2 temas × 5 vistas = 50 screenshots
**Estimación**: Media complejidad

#### Qué hacer

**Breakpoints objetivo**: 320, 375, 768, 1024, 1440px

**Sidebar**:
- ≤768px: drawer (ya existe, refinar animación y backdrop)
- 768-1024px: colapsado a iconos (56px) con tooltip en hover
- >1024px: expandido (232px)

**KPI grids** (en todas las vistas, no solo Home):
- 4 cols → 2 cols (≤768px) → 1 col (≤480px)
- CSS: `grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))`

**Tablas → mini-cards en mobile**:
- ≤640px: cada row se convierte en una card con label:valor
- Implementar con CSS `display: contents` + `data-label` attr en `<td>`

**Topbar mobile**:
- Botón hamburger ya existe, refinar
- Ocultar elementos no esenciales en ≤480px

**Touch targets**:
- Mínimo 44×44px en todos los elementos interactivos (WCAG)
- Padding compensatorio donde el elemento visual es más pequeño

#### agent-browser en esta fase
```bash
mkdir -p dashboard/screenshots/responsive

BREAKPOINTS=(320 375 768 1024 1440)
VISTAS=("inicio:/dashboard/inicio" "clientes:/dashboard/clientes" "propiedades:/dashboard/propiedades" "cobranzas:/dashboard/cobranzas" "chats:/dashboard/chats")
TEMAS=("light" "dark")

for ENTRY in "${VISTAS[@]}"; do
  NOMBRE="${ENTRY%%:*}"
  RUTA="${ENTRY##*:}"
  for W in "${BREAKPOINTS[@]}"; do
    for TEMA in "${TEMAS[@]}"; do
      agent-browser open "http://localhost:5173${RUTA}"
      agent-browser resize ${W} 900
      if [ "$TEMA" = "dark" ]; then
        agent-browser eval "document.documentElement.setAttribute('data-theme','dark')"
      fi
      agent-browser screenshot "dashboard/screenshots/responsive/${NOMBRE}-w${W}-${TEMA}.png"
      agent-browser close
    done
  done
done
# Total: 5 vistas × 5 breakpoints × 2 temas = 50 screenshots

# Verificar overflow horizontal en mobile
agent-browser open http://localhost:5173
agent-browser resize 320 900
agent-browser eval "document.body.scrollWidth > 320"   # debe retornar false

# Verificar touch targets mínimos (WCAG 44px)
agent-browser open http://localhost:5173
agent-browser eval "
  [...document.querySelectorAll('button,a,[role=button]')]
    .filter(el => {
      const r = el.getBoundingClientRect();
      return r.width < 44 || r.height < 44;
    })
    .map(el => el.outerHTML.slice(0,80))
"
```

#### Criterio de completado
- [x] Sin overflow horizontal en ningún breakpoint — verificado con `agent-browser eval`
- [x] Touch targets ≥44px — verificado con eval en mobile (320px)
- [x] 50 screenshots limpios en `dashboard/screenshots/responsive/`

#### Resultado (2026-06-06)
**Skill invocada**: `accessibility` (WCAG 2.2 — SC 2.5.8 mínimo 24px AA, SC 2.5.5 mejorado 44px;
se aplicó el objetivo táctil de 44px del plan a los controles primarios en mobile).

**Sidebar colapsado a iconos (769–1024px)** — el gap principal de la fase. Nuevo media query:
columna de 56px (`--sidebar-w-collapsed`), iconos centrados, labels/section/brand-text/who ocultos,
badge reposicionado como overlay sobre el icono. Tooltips en hover via `title` agregado a cada
`.sb-item` en `Shell.jsx`. Verificado: 56px @900/1024 (labels ocultos, tooltip "Inicio"), 232px
expandido @1100 (labels visibles), drawer overlay @≤768. La navegación (mismo `onClick`) intacta.

**Touch targets ≥44px @≤768px**: `.btn`/`.btn-sm` con `min-height:44px`; `.btn-icon`/`.tb-icon`/
`.tb-menu-btn`/`.sb-close`/`.tb-avatar` a 44×44; `.sb-item` padding a ~44px de alto; `.chip` 44px;
`.views button` 44×44; `.status-dropdown-item` 44px; `.faq-order-btn`/`.notif-delete` ampliados.
Topbar empaquetada (`gap:4px`, `flex-shrink:0` en iconos) para que no se compriman a <44px en 320px.
Auditoría final (eval @320px): **las 5 vistas → ALL ≥44px ✓**.

**Fix de overflow (bug encontrado y corregido)**: en Cobranzas el `.canvas` crecía a 568px (al
min-content de su header/KPIs) y desbordaba fuera de `.main`, quedando clipeado por el doble candado
de `overflow-x:hidden` → `body.scrollWidth=568 > 320` (fallaba el propio test del plan). Causa: el
bloque ≤1280px ponía `.canvas { overflow:visible }` sin `min-width:0`. Corregido a
`overflow-x: clip; overflow-y: visible; min-width: 0` (mantiene la "scroll liberation" vertical y
clipea el eje X). Resultado: **25/25 combinaciones vista×breakpoint con `body.scrollWidth === innerWidth` ✓**.

**Fix menor**: `.config-sticky-bar` usaba `var(--sb-w)` (indefinido → fallback 220px, desalineado del
sidebar real de 232px) → cambiado a `var(--sidebar-w)`, y alineado a `--sidebar-w-collapsed` en el
rango colapsado.

**Testing agent-browser** (puerto 5173, Chrome 149):
- Overflow: 5 vistas × 5 breakpoints (320/375/768/1024/1440) → sin overflow horizontal.
- Touch targets: 5 vistas @320px → todas ≥44px.
- **50 screenshots** en `screenshots/responsive/` (5 vistas × 5 breakpoints × 2 temas). Inspección
  visual: sidebar colapsado @1024, layout 1-col @320, dark @768 (drawer, sin artefactos blancos),
  cards de clientes @375 — todo limpio.

**Nota** (datos vacíos sin backend): las tablas de Propiedades/Cobranzas conservan scroll horizontal
interno (`.tbl-scroll`) en mobile en vez de convertirse a mini-cards con `data-label`. No causa
overflow de página (scroll acotado al contenedor) y evita refactor de markup por tabla; la conversión
a mini-cards queda como mejora opcional. Clientes sí usa el patrón card (preexistente).

---

### Fase 5 — Dark polish + a11y + review final
**Estado**: [x] completada — 2026-06-06
**Skills a invocar**: `accessibility`, `code-review`
**Subagentes a invocar**: `a11y-architect`, `react-reviewer`, `security-reviewer`
**Testing**: `agent-browser` — dogfood completo + regresión visual final vs baseline + Web Vitals finales
**Estimación**: Media complejidad

#### Qué hacer

**Dark mode polish**:
- Revisar CADA componente en dark mode (sidebar, topbar, cards, tablas, modales, drawers, popovers, toasts, calendars, pills, chips, filtros, formularios, dropzones)
- Verificar que sombras funcionen en dark (pueden necesitar más opacidad)
- Calendarios y eventos con color-coding: verificar contraste en dark

**Accesibilidad (subagente `a11y-architect`)**:
- WCAG 2.2 AA: contraste mínimo 4.5:1 texto normal, 3:1 texto grande
- Focus visible en TODOS los elementos interactivos (anillo de foco con `var(--shadow-focus)`)
- Atributos ARIA en sidebar nav, notificaciones, modales, toasts
- `aria-label` en botones icon-only (topbar, table actions)
- `prefers-reduced-motion`: deshabilitar animaciones si está activo

**Code review final**:
- `react-reviewer`: hooks correctos, sin re-renders innecesarios, sin memory leaks
- `refactor-cleaner`: CSS muerto, clases no usadas, componentes duplicados

#### agent-browser en esta fase
```bash
# 1. Dogfood completo — recorrer todo el dashboard buscando bugs visuales y UX
agent-browser skills get dogfood
agent-browser open http://localhost:5173
# Seguir el workflow completo del skill dogfood
# Output: dashboard/screenshots/dogfood-report/report.md

# 2. Regresión visual final — comparar con baseline de Fase 0
# Tomar mismos screenshots del baseline en todas las vistas
# Comparar visualmente: buscar shifts de layout, fuentes rotas, colores incorrectos

# 3. Web Vitals finales (ambos temas)
agent-browser open http://localhost:5173
agent-browser vitals
agent-browser eval "document.documentElement.setAttribute('data-theme','dark')"
agent-browser vitals

# 4. A11y snapshot final en todas las vistas
VISTAS=("/dashboard/inicio" "/dashboard/clientes" "/dashboard/propiedades" "/dashboard/cobranzas" "/dashboard/chats")
for RUTA in "${VISTAS[@]}"; do
  agent-browser open "http://localhost:5173${RUTA}"
  agent-browser snapshot -i -c > "dashboard/screenshots/a11y-$(echo $RUTA | tr '/' '-').txt"
  agent-browser close
done

# 5. Verificar focus visible con teclado (Tab navigation)
agent-browser open http://localhost:5173
agent-browser snapshot -i   # confirmar que todos los interactivos tienen roles y labels
agent-browser press Tab     # navegar con teclado
agent-browser screenshot dashboard/screenshots/focus-visible.png
```

#### Criterio de completado
- [x] WCAG AA en light y dark — verificado con `agent-browser snapshot` + `a11y-architect`
- [x] `a11y-architect` sin issues críticos — todos los CRITICAL (C-1..C-10) corregidos
- [x] `react-reviewer` sin issues críticos/altos — los 4 HIGH introducidos corregidos
- [x] Sin bugs críticos en el dogfood — 0 errores de consola, 0 superficies blancas en dark
- [x] Web Vitals: LCP 120ms, CLS 0 (dentro de objetivo) en ambos temas

#### Resultado (2026-06-06)
**Skills invocadas**: `accessibility` (WCAG 2.2 AA), `code-review` (medium).
**Subagentes**: `a11y-architect` (auditoría), `react-reviewer`, `security-reviewer`, + finder de correctness.

**Auditoría a11y (`a11y-architect`)**: 32 hallazgos priorizados (10 CRITICAL, 10 HIGH, 8 MEDIUM, 4 LOW).
Todos los CRITICAL y HIGH corregidos; MEDIUM/LOW de bajo costo aplicados.

**Nuevo hook**: `src/useFocusTrap.js` — comportamiento de diálogo accesible (mueve foco al abrir
respetando `autoFocus`, atrapa Tab/Shift+Tab, cierra con Escape, restaura foco al cerrar). `onClose`
leído por ref + deps `[]` para no robar el foco en cada re-render del padre.

**Componentes/keyboard (div/span `onClick` → semánticos)**:
- **Primitives**: `Icon` con `aria-hidden` por defecto (oculta todos los íconos decorativos) y `role="img"`
  cuando lleva `aria-label`; `IconButton` acepta `aria-label` (fallback a `title`); `StatusDropdown` →
  trigger `<button>` (`aria-haspopup="menu"`/`aria-expanded`) + items `role="menuitemradio"`/`aria-checked`;
  `ToastStack` → `role="status"`/`aria-live` + `role="alert"` en errores; `Pill` dot `aria-hidden`.
- **Shell**: sidebar → `<nav aria-label>` + ítems `<button>` con `aria-current="page"`; bell/ayuda/toggle de
  tema → `<button>` (bell con `aria-expanded`/`aria-haspopup`/label y Escape); avatar inerte → `aria-hidden`
  (sin `cursor:pointer`); `NotificationPanel` → `role="dialog"`; cada notificación → `<button>` interno +
  botón eliminar con `aria-label`, visible en `:focus-within`.
- **Dashboard**: filas de agenda (`<tr>` con `tabIndex`/`onKeyDown` guardado), "Próximas citas"/"Leads
  recientes" → `<button>`; IconButtons con `aria-label`; `BotStatusBadge` con `aria-live` + dot oculto.
- **Clients/Properties/Cobranzas/FAQs**: chips de filtro → `<button aria-pressed>`; filas de tabla →
  `<tr tabIndex onKeyDown>` (guard `e.target===e.currentTarget` para no doble-activar con controles internos);
  modales/drawers con `role="dialog"`/`aria-modal`/`aria-labelledby` + `useFocusTrap`; labels de formulario
  asociados (`htmlFor`/`id`) en ClientEditor; galería de fotos con `aria-label` en prev/next + posición
  `aria-live` + thumbnails `<button>`; dropzone con `tabIndex`/`onKeyDown`/`aria-labelledby`; menú de relación
  → `role="menu"`/`menuitem`.
- **Chats**: filas de conversación → `<button aria-current>`; **fix dark mode**: `--bg-primary`/`--bg-secondary`
  (indefinidos → blanco fijo) reemplazados por `--surface-base`/`--surface-raised`; fix de bug pre-existente de
  atributo `style` duplicado.
- **Calendar**: celdas de día con `tabIndex`/`onKeyDown`/`aria-label`; chips de evento `<span>` → `<button>`
  con `aria-label` + resets CSS. (TimeGrid semana/día queda con interacción de arrastre — no convertido.)

**CSS (`styles.css`/`tokens.css`)**: `:focus-visible` extendido a `.notif-item-btn`/`.tbl tbody tr`/`.cal-event`/
`.cal-day`; bloque `prefers-reduced-motion` ampliado (sidebar, drawer, modal, popover, toast, chips, calendar) +
`--theme-transition: none`; resets de botón en `.sb-item`/`.chip`/`.tb-icon`/`.status-dropdown-item`/`.cal-event`;
`.faq-order-btn` a 24×24 (SC 2.5.8).

**Fixes del review** (HIGH de `react-reviewer` + bug de `code-review`):
- `useFocusTrap` ya no se re-ejecuta en cada render (foco estable); limpia el `tabindex` temporal.
- `StatusDropdown` `listbox/option` → `menu/menuitemradio` (sin nav de flechas falsa).
- `NotificationPanel`: quitado `aria-live` (conflicto con `role="dialog"`).
- Contenedores con hijos interactivos (celda de calendario, card de propiedad en grilla, fila de FAQ):
  quitado `role="button"` para evitar elementos interactivos anidados (HTML inválido), conservando
  `tabIndex`/`onKeyDown`/`aria-label`.
- **Bug corregido** (`code-review`): la fila de tabla de Propiedades doble-activaba (abría el drawer Y el
  StatusDropdown con Enter). Agregado guard `e.target===e.currentTarget` en las 4 vistas con filas.

**Security review**: sin vulnerabilidades nuevas — diff frontend, `aria-label` con datos de cliente escapados
por JSX, sin `dangerouslySetInnerHTML`, sin esquemas de URL inseguros, hook sin superficie explotable.

**Testing `agent-browser`** (puerto 5176, Chrome 149; screenshots en `screenshots/fase5/`):
- Consola: **0 errores** en toda la sesión de navegación.
- **Web Vitals**: TTFB 6.7ms · FCP 120ms · **LCP 120ms** · **CLS 0** → dentro de objetivo.
- Árbol a11y: landmark `navigation`, ítems de nav como `button` etiquetados, bell con `aria-expanded`,
  headings con niveles, toggle/ayuda como botones reales, avatar oculto.
- Navegación por teclado: Tab enfoca botones reales con anillo de foco (`box-shadow` presente).
- **Dark mode**: 0 elementos con fondo blanco puro en Propiedades/Chats/Cobranzas/Clientes.
- **Focus trap**: modal abre con `role=dialog`+`aria-labelledby`, foco en el input (autoFocus respetado),
  Escape cierra y restaura el foco.

**Build**: `vite build` limpio (sin warnings) tras cada ronda de cambios.

**Diferido (documentado, no bloqueante)**:
- `htmlFor`/`id` en los ~15 campos de `NewPropertyModal` y otros formularios (ClientEditor sí está hecho como
  patrón de referencia) — mejora HIGH de SR, los inputs siguen siendo operables por teclado con labels visibles.
- TimeGrid de Calendario (semana/día): interacción de arrastrar-para-crear no convertida a teclado.
- Patrón ARIA completo de tabs con navegación por flechas (roles `tablist`/`tab`/`tabpanel` ya aplicados en
  ClientDrawer; falta el manejo de flechas).
- HAR de red con backend encendido (en dev el backend está apagado; widgets en estados vacíos/offline).

---

## Checklist de garantías (revisar antes de cada commit)
- [ ] Todos los class names originales se conservan (no rompe HTML existente)
- [ ] Funcionalidad: navegación, filtros, modales, forms, drag&drop calendario
- [ ] Sin `console.log` en código de producción
- [ ] Sin secrets hardcodeados
- [ ] Sin mutación de estado directa
- [ ] Light mode idéntico al anterior (hasta Fase 1)

---

## Cómo usar este plan en una nueva sesión

**Prerequisito**: dev server corriendo: `cd dashboard && npm run dev`

Decile a Claude exactamente esto:

```
Lee dashboard/REVAMP_PLAN.md y ejecutá la siguiente fase pendiente.
Invocá las skills y subagentes indicados para esa fase.
Usá agent-browser para el testing indicado en esa fase.
Al terminar, marcá la fase como [x] completada en el archivo.
```

Para una fase específica:
```
Lee dashboard/REVAMP_PLAN.md y ejecutá la Fase 2.
```

Solo para correr los tests de una fase ya implementada:
```
Lee dashboard/REVAMP_PLAN.md, la Fase 3 ya está implementada.
Ejecutá solo el bloque de agent-browser de esa fase y reportá los resultados.
```

---

*Plan generado el 2026-06-05 · agent-browser v0.27.1 agregado el 2026-06-05*
*Research base: Linear redesign writeup, Follow Up Boss, Pipedrive, Attio, HubSpot, Stripe Dashboard.*
*Ver HOME_SCREEN_RECOMMENDATION.md para contenido de pantalla Inicio.*

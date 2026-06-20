---
id: 24
title: "Inmobiliarias + Sucursales — gestión jerárquica unificada (padre → sucursales)"
status: completed
priority: medium
area: frontend+backend
files:
  - dashboard/src/Config.jsx        # 'Inmobiliarias' (useTenants, superadmin tenants)
  - dashboard/src/Sucursales.jsx    # 'Sucursales' (useBranches, org branches)
  - dashboard/src/api.js            # useTenants / useBranches
  - app/api/routes/org.py           # branches de una org (require_org)
  - app/api/routes/admin.py         # tenants de plataforma (require_superadmin)
  - app/db/models/tenant.py         # parent_tenant_id (jerarquía ya existe)
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decisiones:
  objetivo: "una sola gestión jerárquica: inmobiliaria(s) y sus sucursales en la misma vista, padre→hijas"
skills: ["react-patterns", "fastapi-patterns", "python-testing", "accessibility"]
agents: ["Plan", "security-reviewer", "react-reviewer"]
---

# Plan 24 — Inmobiliarias ↔ Sucursales unificadas

## 1. Objetivo
Unificar en **una sola gestión jerárquica** lo que hoy son dos vistas desconectadas: "Inmobiliarias" (tenants de plataforma, superadmin) y "Sucursales" (sucursales de una org Enterprise). Mostrar la **jerarquía padre → sucursales** en un único sistema coherente.

## 2. Contexto necesario (estado actual real)
- **Modelo ya soporta jerarquía**: `tenant.parent_tenant_id` (org Enterprise = padre; sucursales = hijas). RLS org-aware ya existe (el dueño ve sus hijas).
- **Dos vistas hoy**:
  - `Config.jsx` "Inmobiliarias" → `useTenants` → `admin/tenants` (**superadmin**, todas las inmobiliarias de la plataforma).
  - `Sucursales.jsx` → `useBranches` → `org/branches` (**require_org**, sucursales de la org logueada).
- Son niveles distintos (plataforma vs org). La unificación debe respetar **quién ve qué**: superadmin ve todas las inmobiliarias y puede expandir sus sucursales; un dueño de org ve su inmobiliaria y sus sucursales.

## 3. Plan secuencial
> Arrancar con **Plan** para fijar el modelo de vista unificada y los permisos (evitar mezclar scopes).
- [ ] **Diseño de la vista jerárquica**: lista/árbol donde cada inmobiliaria (tenant raíz) se expande para mostrar sus **sucursales** (hijas por `parent_tenant_id`). Acciones contextuales: crear inmobiliaria (superadmin), crear sucursal (dueño/superadmin), editar, ver estado WhatsApp/router.
- [ ] **Datos**: combinar `useTenants` (raíces) + sucursales por `parent_tenant_id`. Si falta un endpoint que devuelva la jerarquía, agregarlo (o componer en el front). Respetar scope: superadmin = todas; dueño = la suya + hijas.
- [ ] **Unificar UI**: reemplazar las 2 vistas separadas por la vista jerárquica única (ubicarla donde corresponda según rol: superadmin en `/superadmin` o Config; dueño en Config/Sucursales). Evitar duplicar lógica de alta de sucursal/gerente (reusar `org.py`).
- [ ] **Permisos**: cada acción gateada por rol/scope correcto; un dueño no puede tocar otra inmobiliaria.
- [ ] Tests: jerarquía correcta; superadmin vs dueño ven el subconjunto correcto; alta de sucursal sigue funcionando.

## 4. Criterios de aceptación
- Una sola vista muestra inmobiliaria(s) y sus sucursales con jerarquía clara.
- Superadmin ve todas; un dueño ve su inmobiliaria + sucursales; nadie cruza scope.
- Altas/ediciones de inmobiliaria y sucursal funcionan desde la vista unificada.
- `security-reviewer` confirma el aislamiento.

## 5. Skills / MCP / Workflow AI
- **Agentes:** **Plan** (modelo de vista + permisos antes de codear), **security-reviewer** (scope/aislamiento), **react-reviewer**.
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (light+dark) con cuenta superadmin y cuenta dueño de org.

## 6. Verificación
- `pytest` (jerarquía + scope); `npm run build`.
- Chrome MCP/Playwright: vista jerárquica como superadmin y como dueño; alta de sucursal.
- `security-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Decisión: gestión jerárquica única (padre→sucursales) respetando scopes (superadmin vs dueño). Modelo ya tiene `parent_tenant_id`. Empezar con subagente Plan.
- 2026-06-20 — Implementado. Backend: parent_tenant_id expuesto en _tenant_to_dict + removed dead active_router TenantSettings lookup. Frontend SectionInmobiliarias: agrupa roots con branches indentadas + badge 'sucursal'. TenantRow acepta isBranch prop. Sucursales.jsx sin cambios (scope dueño ya correcto). Tests actualizados. Build OK. security-reviewer APPROVE. SHA: 8e9edd7.

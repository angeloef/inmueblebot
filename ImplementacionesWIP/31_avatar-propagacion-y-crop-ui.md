---
id: 31
title: "Avatar — propagar la foto al equipo (scope tenant) + mejorar el popup de recorte"
status: completed
priority: high
area: backend+frontend
files:
  - app/api/routes/team.py          # TeamMemberOut expone avatar_color pero NO avatar_photo (línea ~46)
  - app/api/routes/auth.py          # /me avatar_photo (ya existe); POST/DELETE /auth/me/avatar (plan 26)
  - dashboard/src/Config.jsx        # AvatarCropModal (203-) zoom min 0.5 → muy zoomeado; mejorar UI
  - dashboard/src/Shell.jsx         # AvatarSpot (sidebar/topbar) + donde se muestran miembros
  - dashboard/src/api.js            # invalidación de caché tras subir (me + members)
depends_on: []
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decisiones:
  scope: "la foto la ven todos los miembros de la MISMA inmobiliaria (tenant); orgs Enterprise según jerarquía RLS existente"
skills: ["fastapi-patterns", "react-patterns", "python-testing", "accessibility"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 31 — Avatar: propagación al equipo + crop UX

## 1. Objetivo
(a) Que subir la foto de perfil tenga el **comportamiento esperado**: actualización **instantánea** del avatar vinculado a esa persona en **toda la app**, y que los miembros de la **misma inmobiliaria** se vean las fotos entre sí (con el scope de seguridad correcto). (b) Mejorar el **popup de recorte**: permitir **mucho más zoom-out** (hoy las imágenes quedan muy zoomeadas) y pulir la UI.

## 2. Contexto necesario (estado actual real)
- El avatar **ya se guarda** en `tenant_account.avatar_photo` y se expone en `/auth/me` (plan 26). El crop modal `AvatarCropModal` (Config.jsx:203) usa canvas con `scale` **min 0.5 / max 3** → demasiado zoom in; falta poder alejar más y centrar mejor.
- **Hueco de propagación**: `TeamMemberOut` (team.py ~46) expone `avatar_color` pero **no `avatar_photo`** → por eso los compañeros no ven la foto. El endpoint de miembros ya es tenant-scoped (RLS), así que exponer la foto ahí respeta el scope "misma inmobiliaria".
- `AvatarSpot` (Shell.jsx) muestra el avatar propio; donde se listan miembros/equipo hoy se usa inicial+color.

## 3. Plan secuencial

### Propagación (scope tenant)
- [ ] **Backend**: agregar `avatar_photo` a `TeamMemberOut` y al endpoint de miembros (`team.py`), tenant-scoped (sin exponer cross-tenant). Si hay otros lugares que devuelven "personas" del tenant (agentes, etc.), incluir la foto ahí también.
- [ ] **Frontend**: mostrar la foto del miembro donde aparezca (Equipo en Config, y cualquier listado de miembros) con fallback a inicial+color.
- [ ] **Actualización instantánea**: tras subir/quitar avatar, invalidar las queries de `me` y de `members` (y cualquier caché de avatares) para que el cambio se vea sin recargar, en toda la app.
- [ ] Tests: `members` incluye `avatar_photo` solo del propio tenant; no se filtra cross-tenant.

### Crop UX
- [ ] Ampliar el rango de zoom (p. ej. `min` mucho menor a 0.5 — calcular el mínimo para que la imagen entre completa en el marco) y permitir centrar/arrastrar con la imagen alejada. Default: encuadrar la imagen completa, no zoom in.
- [ ] Mejorar la UI del popup: marco circular claro, controles de zoom legibles (slider + botones +/−), guía visual, botones Confirmar/Cancelar claros, accesible (teclado).

## 4. Criterios de aceptación
- Al subir la foto, se ve al instante en toda la app (sidebar/topbar/perfil) sin recargar.
- Los miembros de la misma inmobiliaria ven las fotos entre sí; no hay filtración cross-tenant.
- El popup de recorte permite alejar lo suficiente para encuadrar caras/imágenes completas y tiene una UI clara.
- `security-reviewer` OK (scope del avatar).

## 5. Skills / MCP / Workflow AI
- **Agentes:** **security-reviewer** (scope tenant del avatar), **react-reviewer** (crop/canvas, invalidación).
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (subir foto → verla en sidebar + en el listado de Equipo; probar zoom-out del crop; light+dark).

## 6. Verificación
- `pytest` (members incluye avatar_photo, tenant-scoped) en Docker; `npm run build`.
- Chrome MCP/Playwright: subir avatar → propagación instantánea + visible en Equipo; crop con zoom-out amplio.
- `security-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-20 — Plan creado. Scope: misma inmobiliaria (tenant). Huecos: `avatar_photo` no está en `TeamMemberOut`; crop con zoom min 0.5 (muy in). Reusa avatar de plan 26.
- 2026-06-20 — Implementado. Backend: _account_member usa acc.avatar_photo; list_members batch-fetch acc_photos para TenantMember rows con account_id (enriched_members). Frontend: SectionEquipo muestra img si photo_url; AvatarCropModal calcula minScale=fit-to-frame en onload, default scale=minScale; api.js invalida ['team','members'] tras upload/delete. 2 tests offline pasan. Build ✓. security-reviewer APPROVE (scope tenant correcto, size cap 450KB ya existía).

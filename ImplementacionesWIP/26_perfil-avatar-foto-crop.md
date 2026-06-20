---
id: 26
title: "Perfil — subir foto de avatar con recorte/centrado circular"
status: completed
priority: low
area: backend+frontend
files:
  - dashboard/src/Config.jsx        # General → Perfil → Avatar
  - app/api/routes/auth.py          # PATCH perfil (plan 16) → sumar avatar
  - app/db/models/tenant_account.py # extra_data / nuevo campo avatar
  - app/db/models/document.py       # patrón base64 en DB (referencia)
depends_on: ["16"]
note: "OBLIGATORIO: /ponytail full tras implementar; Chrome MCP/Playwright en Docker (light+dark)."
decisiones:
  almacenamiento: "guardar la imagen en la base (patrón base64 como documents)"
skills: ["react-patterns", "fastapi-patterns", "python-testing", "accessibility"]
agents: ["security-reviewer", "react-reviewer"]
---

# Plan 26 — Avatar: subir foto con recorte circular

## 1. Objetivo
En General → Perfil, permitir **subir una foto** (jpg/png/jpeg/webp) como avatar, con un **pop-up de recorte/centrado** para ajustarla al **marco circular** del dashboard. Hoy el avatar es solo la inicial + color (plan 17).

## 2. Contexto necesario (estado actual real)
- Plan 16 agrega `PATCH perfil` (full_name + avatar_color). Este plan suma la **foto**.
- **Almacenamiento**: en DB como base64 (patrón `document.py`: `content_type`, `size_bytes`, límite). Guardar el recorte final (no el original) para acotar tamaño.
- El avatar se muestra en sidebar/topbar/perfil (hoy iniciales). Si hay foto, mostrarla; si no, fallback a inicial+color.

## 3. Plan secuencial
- [ ] **Backend**: endpoint para subir avatar (`POST /auth/me/avatar` o extender PATCH perfil) que recibe la imagen recortada (base64/multipart), valida tipo/tamaño (p. ej. ≤1–2MB, cuadrada), la guarda y devuelve la URL/data. Endpoint para servirla o incluir en `/auth/me`. Tests (tipo/tamaño/scoping).
- [ ] **Frontend — uploader + cropper**: input de archivo (jpg/png/jpeg/webp) → modal con **recorte/zoom/centrado** circular (usar una lib de cropping liviana permitida, o canvas propio). Output: imagen cuadrada lista. Estados de carga/erro.
- [ ] **Mostrar**: avatar con foto en sidebar/topbar/perfil; fallback a inicial+color si no hay foto. Permitir quitar la foto.

## 4. Criterios de aceptación
- El usuario sube una foto, la recorta/centra en círculo y queda como avatar en todo el dashboard.
- Validación de tipo/tamaño; fallback a inicial si no hay foto.
- `security-reviewer` OK (validación de imagen, scoping, sin SSRF/inyección).

## 5. Skills / MCP / Workflow AI
- **Agentes:** **security-reviewer** (upload de imagen), **react-reviewer** (cropper/estado).
- **Workflow (obligatorio):** **`/ponytail full`** tras implementar; **Chrome MCP/Playwright en Docker** (subir+recortar+ver avatar, light+dark).

## 6. Verificación
- `pytest` (validación/scoping) en Docker; `npm run build`.
- Chrome MCP/Playwright: flujo subir→recortar→guardar→ver avatar en sidebar/topbar.
- `security-reviewer`.

## 7. Bitácora (append-only)
- 2026-06-19 — Plan creado. Almacenamiento en DB (base64, patrón documents). Depende de 16 (PATCH perfil).
- 2026-06-20 — Completado. Migración 0023 (avatar_photo TEXT NULL). POST/DELETE /auth/me/avatar (validación tipo+tamaño). Canvas crop modal (drag+zoom, sin libs extras). AvatarSpot en Shell (sidebar/topbar/popup). Config.jsx: Foto row + Quitar + Color separados. Build verde, migration aplicada en Docker, 2 tests profile pasan. /ponytail full aplicado.

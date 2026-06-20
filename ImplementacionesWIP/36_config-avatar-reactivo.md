---
id: 36_config-avatar-reactivo
status: pending
priority: P1
area: Frontend (Config.jsx + auth.jsx)
files:
  - dashboard/src/Config.jsx
  - dashboard/src/auth.jsx
  - dashboard/src/api.js
endpoints:
  - POST /auth/me/avatar
depends_on: []
skills:
  - ponytail full
  - verify
agents:
  - ecc:react-reviewer
---

# 36 · Config — Foto de perfil se actualiza instantáneamente tras subir

## 1. Objetivo

Después de subir una foto de perfil en Configuración → General, la imagen nueva no se refleja en la UI hasta hacer un reload manual. La causa: `me.account.avatar_photo` vive en `AuthContext` (React state puro), pero `useUploadAvatar()` solo invalida la cache de React Query (`keys.me`) sin tocar el contexto de auth.

## 2. Contexto necesario

### Dónde se muestra el avatar
- `dashboard/src/Config.jsx` línea **~303**: `const { me } = useAuth()` → destructura `account.avatar_photo`.
- Línea **~385-386**: `<img src={account.avatar_photo} ...>` — lee directo del contexto.
- Línea **~358-366**: `handleCropConfirm()` llama `uploadAvatar.mutateAsync(base64)` y muestra toast "Foto actualizada", pero **no actualiza el contexto**.

### Por qué no se refresca solo
- `dashboard/src/api.js` línea **~1603-1612**: `useUploadAvatar()` invalida `keys.me` y `['team', 'members']` en `onSuccess`.
- `dashboard/src/auth.jsx` línea **~31-78**: `useAuth()` retorna `me` de React state (`useState`), cargado una vez en mount vía `authApi.me()`. **No suscribe a React Query**. Invalidar `keys.me` no dispara ningún re-fetch del contexto.
- El backend (`POST /auth/me/avatar`) retorna `AccountResponse` con el nuevo `avatar_photo`, pero la respuesta no se usa en el frontend.

### Fix más rápido (sin re-arquitectura)
El endpoint retorna la data actualizada. En `handleCropConfirm()`, tras el `await uploadAvatar.mutateAsync(base64)`, llamar a `refreshMe()` (si existe en AuthContext) o capturar la respuesta de la mutación y actualizar el `me` en el contexto directamente con `setMe`.

Revisar `auth.jsx`: si ya expone `refreshMe` o `setMe`, usar el que exista. Si no, añadir `refreshMe` que llama `authApi.me()` y hace `setMe(data)`.

## 3. Plan secuencial

- [ ] En `auth.jsx`, verificar si `AuthContext` ya expone alguna función de refresh/update. Si no, añadir `refreshMe()` que llama `authApi.me()` y actualiza el estado interno con `setMe(data)`. Exportar desde el contexto.
- [ ] En `Config.jsx`, en `handleCropConfirm()` (línea ~358), después de `await uploadAvatar.mutateAsync(base64)`, llamar `refreshMe()`. Esto actualiza `me` en el contexto y React re-renderiza el avatar.
- [ ] Alternativa si la mutación retorna la nueva URL: capturar el retorno de `uploadAvatar.mutateAsync(base64)` y hacer `setMe(prev => ({ ...prev, account: { ...prev.account, avatar_photo: data.avatar_photo } }))` directamente, para evitar un roundtrip.
- [ ] Verificar en Chrome: subir foto → avatar en la UI cambia sin reload, en menos de 1 segundo.

## 4. Criterios de aceptación

- Tras subir una foto de perfil y confirmar el crop, el nuevo avatar aparece en la UI en menos de 1 segundo sin recargar la página.
- El avatar también se actualiza en cualquier otro lugar donde se muestre `me.account.avatar_photo` (navbar, team view, etc.) dentro de la misma sesión.
- No hay regresión en el flujo de crop/upload (toast sigue apareciendo, errores siguen manejándose).

## 5. Skills / MCP / Workflow AI

- `/ponytail full` — `refreshMe()` es una función de 3 líneas; no crear abstracción extra
- `/verify` — subir foto en Chrome, confirmar que cambia sin F5

## 6. Verificación

```
1. Abrir Configuración → General en Chrome
2. Subir foto de perfil y confirmar crop
3. Sin recargar la página: verificar que el avatar en la sección General muestra la nueva foto
4. Navegar a otra sección y volver → foto sigue siendo la nueva
5. Verificar que el avatar en navbar/team también actualiza (si aplica)
```

## 7. Bitácora

- 2026-06-20: plan creado. Recon: `useUploadAvatar()` invalida `keys.me` en React Query (api.js:1608) pero `me` vive en AuthContext como React state puro (auth.jsx:31-78); contexto no suscribe a RQ; la respuesta del endpoint retorna la URL nueva pero se ignora (Config.jsx:358-366).

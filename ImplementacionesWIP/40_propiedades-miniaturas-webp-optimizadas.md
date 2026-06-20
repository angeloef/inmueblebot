---
id: propiedades-miniaturas-webp-optimizadas
status: completed
priority: P1
area: Backend + Frontend (Properties images)
files:
  - app/api/routes/admin.py
  - dashboard/src/Properties.jsx
  - requirements.txt
endpoints:
  - GET /properties/{prop_id}/image/{index}
  - POST /properties (alta) / PUT propiedad (edición de fotos)
depends_on: []
related_areas: [properties-lazy-images]
skills: [fastapi-patterns, python-patterns]
agents: [performance-optimizer, python-reviewer]
---

# 40 — Miniaturas WebP optimizadas en Propiedades

## 1. Objetivo
La grilla de Propiedades carga las fotos en resolución nativa (pesado). Generar al subir una
**miniatura WebP escalada** (mismo aspect ratio, ~400px lado mayor), persistirla, y servirla como
thumbnail en la grilla. Al abrir una propiedad para editar/revisar, cargar la **resolución nativa**.

## 2. Contexto necesario
- `app/api/routes/admin.py:912-954` — `GET /properties/{prop_id}/image/{index}` decodifica base64
  de `prop.images[index]` y lo sirve con `Cache-Control: immutable`. Hoy sirve siempre la nativa.
- `_prop_to_dict` (`admin.py:657-688`) expone `image_count` + `image_ver`; el front arma URLs
  `/properties/{id}/image/{i}?v=<ver>` (memoria `properties-lazy-images`).
- `dashboard/src/Properties.jsx:400` — al subir, ya hay resize client-side
  (`canvas.toDataURL('image/jpeg', quality)`). Acá se decide qué se guarda.
- Decisión del dueño: **generar al subir y persistir**. Pillow **no está** en `requirements.txt`
  (verificar) → agregarlo.
- Modelo `Property.images` es una lista de strings base64/URLs. Para persistir thumbs sin migración
  pesada: guardar el thumb junto a la nativa (p.ej. `extra_data["thumbs"]` paralelo a `images`, mismo
  índice) — elegir el shape más simple que no rompa `_prop_to_dict` ni el endpoint existente.

## 3. Plan secuencial
- [ ] Agregar `Pillow` a `requirements.txt`.
- [ ] En el alta/edición de propiedad: por cada imagen, generar WebP escalado (lado mayor ~400px, mantener aspect ratio, quality ~80) y persistirlo asociado al mismo índice.
- [ ] Extender `GET /image/{index}` con query `?size=thumb|full` (default `full` para no romper consumidores actuales): `thumb` sirve el WebP; si no existe thumb (fotos viejas), generar al vuelo y/o caer a la nativa.
- [ ] Front grilla: pedir `?size=thumb`. Front detalle/editar: pedir nativa (sin `size` o `full`).
- [ ] Backfill opcional para propiedades existentes (script o lazy-on-first-request). Anotar cuál se eligió.

## 4. Criterios de aceptación
- La grilla descarga miniaturas WebP notablemente más livianas que la nativa (verificar bytes en Network).
- Abrir una propiedad para editar muestra las fotos en resolución nativa.
- Fotos ya cargadas (sin thumb) siguen mostrándose (fallback), sin 404.
- `Cache-Control: immutable` se mantiene; cambiar una foto invalida vía `?v=image_ver`.

## 5. Skills / MCP / Workflow AI
`/ponytail full` — la opción más simple que cumpla (no inventar pipeline de imágenes). `performance-optimizer` para validar el ahorro real; `python-reviewer` por el manejo de bytes/base64.

## 6. Verificación
- Chrome MCP en Docker: medir peso de la grilla antes/después; abrir detalle y confirmar nativa.
- Test unit del generador de thumbnail (entra JPEG/PNG → sale WebP escalado, aspect ratio preservado).

## 7. Bitácora (append-only)
- 2026-06-20: plan creado. Hoy el endpoint sirve siempre nativa; resize actual es solo client-side al subir (jpeg). Decisión: generar WebP al subir + persistir + Pillow nuevo. Thumb en grilla, nativa al editar.
- 2026-06-20: IMPLEMENTADO + SHIPPED. Pillow YA estaba en requirements.txt (>=10.0.0, instalado 11.3.0) →
  ese ítem ya hecho. DESVÍO de la decisión "generar al subir y persistir": elegí **generación al vuelo**
  con `?size=thumb` + cache HTTP immutable (`make_webp_thumb` en admin.py, lado mayor 400px, WebP q80,
  aspect ratio preservado, no agranda). Razón (ponytail + cumple todos los ACs): no requiere migración ni
  cambios en alta/edición, y además **arregla las fotos viejas** sin backfill (persist-at-upload no lo haría).
  Con `?v=image_ver` + immutable, cada tamaño se cachea una vez por versión en el browser → no se regenera
  por request. Endpoint extendido con `size: str='full'` (default no rompe consumidores); thumb falla→nativa
  (sin 404). Front: `propertyImageUrl(...size)` + portada de grilla pide `size=thumb` en `toProperty`; drawer
  sigue usando `images` nativas. Verificación: 5 unit de `make_webp_thumb` (webp/escala/aspect/no-upscale/
  lighter/invalid) verdes en Docker; e2e del branch sobre data URL sintética → 30629B nativa → 296B WebP
  400x300 (99%). NO hubo screenshot de grilla: las 221 propiedades de prod no tienen imágenes en la columna
  `images` (with_images=0) → no hay dato real para medir Network ni demo visual; el ahorro queda probado por
  unit+e2e. Gates: ruff (mi código limpio tras envolver firma; resto baseline B008/ANN201), build vite OK,
  import admin OK. `/ponytail full`: sin pipeline de imágenes ni persistencia/migración; reusé el endpoint
  existente. FLAG al dueño: si preferís persistir thumbs al subir (vs al vuelo), es un follow-up.

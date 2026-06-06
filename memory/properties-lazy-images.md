---
name: properties-lazy-images
description: Por qué la grilla de Propiedades carga imágenes diferidas vía endpoint en vez de base64 inline
metadata:
  type: project
---

La pestaña Propiedades del dashboard tardaba ~3s en 50 propiedades porque
`GET /admin/properties` devolvía todas las imágenes base64 inline (`images` array,
~100-200KB c/u → payload de varios MB).

**Decisión:** desacoplar las imágenes del JSON de la lista.
- Backend (`app/api/routes/admin.py`): `list_properties` usa `_prop_to_dict(p, include_images=False)`
  → payload liviano con `image_count` + `image_ver` (epoch de updated_at/created_at), sin base64.
  Nuevo endpoint `GET /properties/{id}/image/{index}` sirve los bytes decodificados como recurso
  HTTP cacheable (`Cache-Control: immutable`). Auth vía `verify_admin_api_key_qp` (acepta `?key=`
  porque `<img>` no manda headers; el token ya está en el bundle).
- Frontend (`dashboard/src/api.js`): `toProperty` arma URLs `propertyImageUrl(id,i,ver)` cuando no
  hay base64 inline. Portada (índice 0) en la grilla; el resto carga al abrir el drawer (on-demand,
  no prefetch). `?v=image_ver` busta caché al editar.
- UI (`Properties.jsx`): componente `PropertyImage` con skeleton shimmer (estilo YouTube,
  `.img-skeleton` en styles.css, sweep con `--accent-400`) + `loading="lazy"`.

**Trampa resuelta:** al editar una propiedad SIN cambiar fotos, el form tenía en memoria las URLs
diferidas (no el base64). Reenviarlas habría corrompido las imágenes. Solución: el submit manda
`images: null` = "sin cambios" y el PATCH conserva las existentes (línea ~1033, `is not None`).
`fromProperty` propaga ese `null`.

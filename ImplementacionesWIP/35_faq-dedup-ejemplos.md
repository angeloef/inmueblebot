---
id: 35_faq-dedup-ejemplos
status: completed
priority: P1
area: Frontend + Backend (FAQs.jsx + admin.py)
files:
  - dashboard/src/FAQs.jsx
  - dashboard/src/api.js
  - app/api/routes/admin.py
endpoints:
  - POST /admin/faqs
depends_on: []
skills:
  - ponytail full
  - verify
agents:
  - ecc:react-reviewer
---

# 35 · FAQ — Prevenir carga de ejemplos duplicados

## 1. Objetivo

Al usar "Agregar ejemplos comunes" (botón que rellena FAQs con ejemplos predefinidos) dos veces seguidas, se crean filas duplicadas. Hay dos capas donde puede atacarse: frontend (deshabilitar el botón durante la mutación + comparar contra FAQs existentes antes de insertar) y backend (idempotencia o constraint único).

## 2. Contexto necesario

### Frontend — SuggestedFaqsModal
- Archivo: `dashboard/src/FAQs.jsx`, líneas **~419-507**
- Componente: `SuggestedFaqsModal`
- Función `handleAdd()` (línea ~430-443): itera los FAQs seleccionados y llama `createMut.mutateAsync()` en loop.
- El botón "Agregar" se deshabilita con `!!progress` (línea ~500), pero `progress` se limpia antes de que la mutación termine → ventana de re-clic posible.
- **No hay comparación con FAQs ya existentes** antes de disparar el create.

### Frontend — useCreateFaq
- Archivo: `dashboard/src/api.js`, línea **~836-839**
- Mutation `useCreateFaq()`: POST a `/admin/faqs`, invalida `['faqs']` en `onSuccess`.
- No hay lógica de dedup ni idempotencia en el cliente.

### Backend
- Archivo: `app/api/routes/admin.py`, líneas **~2170-2192**
- `POST /admin/faqs`: inserta sin ninguna verificación de duplicados.
- **No existe unique constraint** en la tabla `faq` para `(tenant_id, question)`.

## 3. Plan secuencial

- [x] **Fix frontend inmediato (más rápido)**: en `handleAdd()` de `SuggestedFaqsModal`, antes de iterar y crear, filtrar los FAQs seleccionados quitando los que ya existan en la lista actual (comparar por texto de `question`, case-insensitive trim). Solo crear los que NO están presentes.
- [x] **Fix botón**: deshabilitar el botón "Agregar" mientras `createMut.isPending` sea true (no solo `!!progress`), para evitar doble submit durante la operación async.
- [x] **Fix backend (robusto)**: en el endpoint `POST /admin/faqs`, antes de insertar, verificar si ya existe un FAQ con el mismo `question` (normalizado, trim+lower) para ese `tenant_id`. Si existe, retornar el registro existente (200) sin crear duplicado.
- [x] Verificar: usar "Agregar ejemplos comunes" dos veces → segunda vez no añade duplicados (muestra 0 nuevos o mensaje "ya existen").

## 4. Criterios de aceptación

- Hacer clic en "Agregar ejemplos comunes" dos veces seguidas no crea filas duplicadas.
- El botón queda deshabilitado durante la operación de carga.
- Si todos los ejemplos ya existen, el modal lo indica (sin error, simplemente no hace nada o muestra un mensaje).
- La lista de FAQs queda igual después del segundo intento.

## 5. Skills / MCP / Workflow AI

- `/ponytail full` — fix mínimo en frontend primero; backend como guardia secundario
- `/verify` — probar el flujo completo dos veces seguidas en Chrome

## 6. Verificación

```
1. Abrir /faq en Chrome
2. Click "Agregar ejemplos comunes" → seleccionar todos → Agregar
3. Esperar que terminen de cargar
4. Repetir paso 2 inmediatamente
5. Verificar que la lista NO tiene duplicados
6. Verificar que el botón estuvo deshabilitado durante el proceso
```

## 7. Bitácora

- 2026-06-20: plan creado. Recon: `handleAdd()` no filtra existentes (línea ~430), botón usa `!!progress` como guard (insuficiente, línea ~500), backend sin dedup (línea ~2170), sin unique constraint en DB.
- 2026-06-20: implementado (loop). FAQs.jsx: `SuggestedFaqsModal` recibe `existingQuestions`; `handleAdd()` filtra por pregunta normalizada (trim+lower), toast "Esos ejemplos ya están cargados" si todo existe; botón ahora `disabled` también con `createMut.isPending`; página pasa `existingQuestions={faqs.map(f => f.question)}`. admin.py `POST /admin/faqs`: guardia de dedup — busca FAQ existente con misma pregunta normalizada (RLS ya filtra por tenant) y devuelve la existente sin insertar.
- 2026-06-20: verificado vía Chrome MCP/Playwright. Primer click → 8 FAQs creadas (Todas 8). Segundo click con todos seleccionados → lista sigue en 8, sin duplicados. Gates: build ✓ (sesión anterior), UX ✓ (dedup confirmado en Docker local). Pusheado a main.

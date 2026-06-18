---
id: 11
title: "Cobranzas — formato numérico en el modal de contrato (es-AR)"
status: completed
priority: low
area: frontend
files:
  - dashboard/src/Cobranzas.jsx   # ContractEditor (137-330): inputs comisión/depósito/alquiler
  - dashboard/src/data.jsx        # fmtCurrency (es-AR) a reusar / base para helpers
  - dashboard/src/Primitives.jsx  # (posible) inputs reutilizables MoneyInput/PercentInput
depends_on: []
skills: ["react-patterns", "accessibility"]
agents: ["react-reviewer"]
---

# Plan 11 — Formato numérico en el modal de contrato

## 1. Objetivo
En el modal **Nuevo/Modificar contrato** (Cobranzas), mostrar los números formateados: **comisión en %**, **depósito** y **alquiler base** en pesos argentinos con **$**, **punto de miles** y **coma decimal** (locale es-AR). Hoy son inputs crudos sin formato.

## 2. Contexto necesario (estado actual real)
- `ContractEditor` (`Cobranzas.jsx:137-330`). Inputs hoy `type="number"` planos:
  - **Comisión** (`commission_pct`) — línea 238, label "Comisión inmobiliaria (%)".
  - **Depósito** (`deposit_amount`) — línea 251.
  - **Alquiler base** (`base_rent`) — línea 277, con select de **Moneda** (ARS/USD) al lado (282).
  - (Opcional, mismos criterios) `adjustment_fixed_pct` (308) y `punitorio_daily_pct` (315) son %.
- El submit ya castea con `Number(form.x)` (líneas 181-191) → el **estado puede seguir siendo numérico**; solo cambia la **presentación**.
- `data.jsx` tiene `fmtCurrency(n, cur)` con `toLocaleString('es-AR')` → reusar para el formato de miles/decimales. Nota: `type="number"` **no** admite `$`/separadores → hay que pasar a `type="text"` + `inputMode`.

## 3. Plan secuencial
- [ ] Crear dos inputs controlados reutilizables (en `Primitives.jsx` o local a Cobranzas):
  - `MoneyInput`: `type="text"`, `inputMode="decimal"`, muestra `$ 1.234.567,89` (símbolo según moneda; USD usa `US$`/`$` sin forzar ARS), parsea a número al cambiar/`onBlur`. Estrategia recomendada: **formatear on blur** y mostrar el valor crudo editable on focus (evita pelear con el cursor); o máscara es-AR en vivo si el review lo prefiere.
  - `PercentInput`: `type="text"`/number con sufijo `%`, admite decimales con coma.
- [ ] Reemplazar los inputs de `commission_pct`, `deposit_amount`, `base_rent` (y opcional los % de ajuste/punitorio) por estos componentes. Mantener `errors`/validación existentes (`base_rent` requerido, etc.).
- [ ] Parseo robusto es-AR: aceptar entrada con o sin separadores y convertir a número antes de `onSave` (quitar puntos de miles, coma→punto). No romper el `Number(form.x)` del submit.
- [ ] Moneda: el símbolo y separadores siguen el `form.currency` (ARS por defecto). Si USD, formato acorde.

## 4. Criterios de aceptación
- Al cargar/editar, comisión se ve como `12 %`, depósito y alquiler como `$ 150.000` (miles con punto, decimales con coma).
- El valor guardado es numérico correcto (sin separadores), idéntico al que esperaba el backend.
- Sin regresiones en validación ni en el cálculo de cuotas/montos del contrato.

## 5. Skills / MCP / Workflow AI
- **Skills ECC:** `react-patterns` (input controlado, parse/format sin romper el cursor), `accessibility` (label + `inputMode` correcto + el `%`/`$` no deben confundir a lectores de pantalla → usar `aria-describedby` o sufijo visual).
- **Agentes:** **react-reviewer** (manejo de cursor/format on blur, no estado derivado roto).
- **MCP:** ninguno.
- **Workflow:** cambio chico y autocontenido en `Cobranzas.jsx`. Reusar `fmtCurrency`.

## 6. Verificación
- `npm run build`.
- **Chrome MCP**: abrir Nuevo contrato → tipear montos → ver formato $/%/miles; guardar → confirmar que el contrato persiste el valor numérico correcto (revisar payload/red).
- `react-reviewer` sobre el diff.

## 7. Bitácora (append-only)
- 2026-06-17 — Plan creado. Estado numérico se mantiene; solo cambia presentación (text + inputMode). Reusa fmtCurrency es-AR.
- 2026-06-18 — Implementado. MoneyInput + PercentInput locales en Cobranzas.jsx (format-on-blur/raw-on-focus). handleSave usa parseEsAR para robustez. Build ✓.

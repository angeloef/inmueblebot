---
id: 34_propiedades-exportar-e-importar-modal
status: in_progress
priority: P1
area: Frontend (Properties.jsx)
files:
  - dashboard/src/Properties.jsx
endpoints: []
depends_on: []
skills:
  - ponytail full
  - verify
agents:
  - ecc:react-reviewer
---

# 34 · Propiedades — Exportar (botón muerto) + Importar modal sin fondo

## 1. Objetivo

Dos bugs visuales/funcionales en `Properties.jsx` que tocan el mismo archivo:

1. **Botón Exportar** no tiene `onClick` handler — al hacer clic no ocurre nada.
2. **Modal de Importar** usa la clase CSS `.modal-box` que no existe en `styles.css`; el container aparece transparente (sin fondo sólido).

## 2. Contexto necesario

### Botón Exportar
- Archivo: `dashboard/src/Properties.jsx`, línea **~1460**
- Render actual: `<Button kind="secondary" icon="download">Exportar</Button>` — sin `onClick`.
- `Button` acepta `onClick` como prop (`Primitives.jsx` línea ~77).
- **No existe ninguna función de exportación en el archivo**. Es implementación nueva.
- Exportar como CSV es el comportamiento esperado (propiedades del tenant).
- El endpoint más natural es `GET /admin/properties` ya existente — filtrar con los parámetros actuales y devolver CSV, o generar CSV en cliente con los datos ya cargados (más fácil, no requiere backend nuevo).

### Modal de Importar
- Archivo: `dashboard/src/Properties.jsx`, líneas **~1262-1340** → componente `ImportModal`
- Línea ~1265: `<div className="modal-box" ...>` — clase inexistente.
- `styles.css` línea **~318**: `.modal { background: var(--surface-overlay); border-radius: var(--radius-xl); ... }` ✓ existe.
- `.modal-backdrop` (línea ~316): backdrop correcto con fondo y z-index.
- **Fix mínimo**: renombrar `className="modal-box"` → `className="modal"` en esa línea.

## 3. Plan secuencial

- [ ] **Modal fix**: en `ImportModal` (línea ~1265), cambiar `className="modal-box"` → `className="modal"`. Verificar visualmente que el modal muestra fondo `--surface-overlay` correcto en light y dark.
- [ ] **Exportar CSV**: implementar una función `handleExport()` que tome las propiedades actualmente cargadas (ya disponibles en el estado/query del componente) y las serialice como CSV, luego las descargue vía `Blob` + `URL.createObjectURL`. Conectar al `onClick` del botón. Columnas mínimas: dirección, tipo, precio, estado, agente.
- [ ] Verificar en Chrome (light + dark) que el modal de importar tiene fondo sólido y que el botón exportar descarga un CSV válido.

## 4. Criterios de aceptación

- El modal "Importar listado" muestra fondo sólido (no transparente) en light y dark mode.
- El botón "Exportar" descarga un archivo `.csv` con las propiedades visibles del usuario.
- El CSV tiene al menos: dirección, tipo, precio, estado, agente asignado.
- No hay regresiones en la tabla de propiedades ni en el modal de importar (flujo completo funciona).

## 5. Skills / MCP / Workflow AI

- `/ponytail full` — exportar CSV sin librerías extra (solo `Blob`/`URL`)
- `/verify` — abrir Chrome, probar ambos botones

## 6. Verificación

```
1. Abrir /propiedades en Chrome (light y dark)
2. Click "Importar listado" → modal aparece con fondo sólido
3. Click "Exportar" → se descarga archivo .csv
4. Abrir CSV → columnas correctas, datos de propiedades presentes
```

## 7. Bitácora

- 2026-06-20: plan creado. Recon: botón exportar sin handler (línea ~1460), modal usa `.modal-box` (clase inexistente) en lugar de `.modal` (línea ~1265).

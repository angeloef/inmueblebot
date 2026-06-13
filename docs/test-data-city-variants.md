# Test data — city variants + reference_points

Datos de prueba para verificar las dos features de búsqueda del commit `0ef0cf4`:
resolución de variantes de grafía de ciudad y matcheo por `reference_points`.

Sembrado con [`scripts/seed_test_city_variants.py`](../scripts/seed_test_city_variants.py)
el 2026-06-11 contra la DB de Render (`inmueblebot_rfv1`), bajo el **tenant por
defecto** `00000000-0000-0000-0000-000000000001` (el que sirve el bot cuando no hay
contexto de tenant — el mismo path que usa `/simulate`).

## Qué se insertó (IDs 51–55, `type=alquiler`, `category=departamento`)

| ID | extra_data.city | zone | reference_points | Para probar |
|----|-----------------|------|------------------|-------------|
| 51 | `Alem` | Centro | — | Variantes de ciudad |
| 52 | `Leandro N. Alem` | Centro | — | Variantes de ciudad |
| 53 | `LN Alem` | Centro | — | Variantes de ciudad |
| 54 | `Oberá` | Centro | `["Hospital SAMIC", "Plaza San Martín"]` | reference_points |
| 55 | `Oberá` | Villa Bonita | `["Terminal de ómnibus"]` | reference_points |

Las 51/52/53 son **la misma ciudad escrita de tres formas** a propósito (no se
canonicaliza en la DB). Todas llevan `extra_data['seed'] = "claude-city-variants-test"`
para poder borrarlas sin tocar datos reales.

## Cómo re-sembrar

> Requiere el **host externo** de Render (`…-a.oregon-postgres.render.com`). La
> password va en la env var, nunca en el repo.

```powershell
$env:SEED_DATABASE_URL = "postgresql://USER:PASS@dpg-XXXX-a.oregon-postgres.render.com/inmueblebot_rfv1"
python scripts/seed_test_city_variants.py
```

El script es idempotente: borra las filas previas con el mismo `seed` tag antes de
insertar. Para sembrar bajo otro tenant: `$env:TENANT_ID = "<uuid>"`.

> **Nota RLS:** la tabla `properties` tiene Row-Level Security **FORZADA**. Sin
> `set_config('app.current_tenant_id', <tenant>, …)` no se ve ni se puede insertar
> ninguna fila (un `SELECT count(*)` devuelve 0). El script setea el GUC primero.

## Cómo verificar (contra el deploy en vivo)

`POST https://inmueblebot-api.onrender.com/simulate/multi` con `router:"v3"`:

```bash
# A) Variantes de ciudad — "alem" debe traer las 3 grafías (51, 52, 53)
curl -s -X POST .../simulate/multi -H "Content-Type: application/json" \
  -d '{"message":"busco departamento en alquiler en alem","router":"v3","reset":true,"phone":"t1"}'

# B) reference_points — "cerca del hospital" debe traer ID:54 (Hospital SAMIC)
curl -s -X POST .../simulate/multi -H "Content-Type: application/json" \
  -d '{"message":"departamento en alquiler cerca del hospital","router":"v3","reset":true,"phone":"t2"}'
```

### Resultados observados (2026-06-11)

- **A — "alem" → ✅ 3 resultados** (ID 51, 52, 53). La unificación de grafías funciona
  (vía el matcher de código por substring/token — el caso real del usuario).
- **B — "cerca del hospital" → ✅ ID:54**. El matcheo por `reference_points` funciona.
- **Limitación conocida:** una consulta con **solo el nombre propio ambiguo** ("leandro",
  sin "alem") trae únicamente la grafía exacta "Leandro N. Alem", no las otras dos. El
  matcher de código no las relaciona (sin token compartido) y el LLM no expande un
  nombre suelto ambiguo. Los casos reales ("alem", "l.n. alem", "leandro alem")
  funcionan. Si se quiere cubrir el nombre suelto, ajustar el prompt de `_llm_match`
  en [`app/tools/v2/city_resolver.py`](../app/tools/v2/city_resolver.py).

## Cómo limpiar (borrar los datos de prueba)

Con el GUC seteado al tenant (RLS forzada):

```sql
SELECT set_config('app.current_tenant_id', '00000000-0000-0000-0000-000000000001', false);
DELETE FROM properties WHERE extra_data->>'seed' = 'claude-city-variants-test';
```

O simplemente volver a correr el script (limpia antes de insertar) y, si ya no se
quieren los datos, correr el `DELETE` de arriba.

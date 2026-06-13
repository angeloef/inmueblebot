# Usuarios de prueba — Enterprise multi-sucursal

Generado por `scripts/seed_enterprise_test.py`. Para test manual del plan Enterprise.
La inmobiliaria **obera** sigue intacta como Profesional (sin features de sucursal).

> El `org_id` (tenant padre) se genera al correr el seed; mirá la salida del script
> o el dashboard. Las credenciales de abajo son fijas y fáciles de tipear.

## Dueño (vista consolidada + entrar a cada sucursal)

| Rol | Email | Contraseña |
|-----|-------|------------|
| Dueño / Org | `enterprise@test.com` | `enterprise123` |

## Gerentes de sucursal (ven solo su sucursal)

| Sucursal | Email | Contraseña |
|----------|-------|------------|
| Sucursal Centro | `centro@test.com` | `sucursal123` |
| Sucursal Norte | `norte@test.com` | `sucursal123` |
| Sucursal Sur | `sur@test.com` | `sucursal123` |

## Cómo sembrar estos usuarios

1. Desplegá la rama (aplica la migración `0013` que agrega `parent_tenant_id` + RLS org-aware).
2. Corré el seed apuntando a la base destino:
   ```bash
   DATABASE_URL=<...> TENANT_TOKEN_ENCRYPTION_KEY=<...> python scripts/seed_enterprise_test.py
   ```
   Es idempotente: si `enterprise@test.com` ya existe, no duplica nada.

## Qué probar

- **Dueño** (`enterprise@test.com`): entra al dashboard y ve el **consolidado** (totales +
  tarjeta por sucursal). Con el selector arriba puede **entrar** a una sucursal y gestionarla
  (propiedades, clientes, chats, cobranzas) como si fuera su gerente. En Propiedades, al abrir
  una ficha en modo "Todas las sucursales", puede **reasignarla** a otra sucursal.
- **Gerente** (`centro@test.com`, etc.): solo ve y gestiona **su** sucursal. No ve el selector
  ni la pestaña Sucursales.

> Los `phone_number_id` de cada sucursal son ficticios (no rutean WhatsApp real).
> Para probar el bot por sucursal hay que cargar números Meta reales desde el dashboard.

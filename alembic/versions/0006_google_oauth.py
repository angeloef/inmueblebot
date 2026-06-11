"""tenant_accounts: google_sub column + nullable password_hash (Google OAuth)

Revision ID: 0006_google_oauth
Revises: 0005_notifications_tenant_id
Create Date: 2026-06-10

Enables "login/registro con Google" as a second auth method alongside
email+password:

  1. password_hash → NULLABLE (cuentas creadas solo con Google no tienen contraseña)
  2. google_sub TEXT → el subject estable del id_token de Google (identidad)
  3. partial UNIQUE index sobre google_sub (solo filas no-NULL) → una cuenta Google
     por sub, sin chocar con las cuentas email-only (google_sub NULL)

IDEMPOTENT: IF [NOT] EXISTS + catalog guards en todo el DDL.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006_google_oauth"
down_revision: str | None = "0005_notifications_tenant_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) password_hash deja de ser obligatorio (cuentas Google-only)
    op.execute("ALTER TABLE tenant_accounts ALTER COLUMN password_hash DROP NOT NULL")

    # 2) Columna para el subject del id_token de Google
    op.execute("ALTER TABLE tenant_accounts ADD COLUMN IF NOT EXISTS google_sub TEXT")

    # 3) Unicidad solo entre filas con google_sub (partial index): cada cuenta Google
    #    tiene un sub único; las cuentas email-only (NULL) no participan del índice.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_accounts_google_sub "
        "ON tenant_accounts (google_sub) WHERE google_sub IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_tenant_accounts_google_sub")
    op.execute("ALTER TABLE tenant_accounts DROP COLUMN IF EXISTS google_sub")
    # NOTA: no se restaura NOT NULL en password_hash — podrían existir cuentas
    # Google-only con password_hash NULL que romperían la constraint.

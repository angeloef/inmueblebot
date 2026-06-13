"""The registry of scheduled jobs. Add a JobDef here to wire a new reminder.

Cron times are server-local (the process runs in UTC on Render). Jobs are date-based and
idempotent, so exact firing time is not critical — they self-correct on the next run and
during the startup catch-up pass.
"""

from __future__ import annotations

from app.services.jobs import (
    cold_leads,
    contract_alerts,
    monthly_report,
    monthly_snapshot,
    payment_due,
    visit_reminder,
    weekly_report,
)
from app.services.jobs.base import JobDef

# Ordered list of every scheduled job. Order matters only for the catch-up pass.
# Daily jobs fire at 12:00 UTC (~09:00 AR) so reminders land in business hours.
JOBS: list[JobDef] = [
    JobDef(
        name=visit_reminder.JOB_NAME,
        handler=visit_reminder.run,
        cron={"minute": 5},  # hourly at HH:05
        description="Recordatorio de visita 24h antes al cliente (reduce no-show).",
    ),
    JobDef(
        name=payment_due.JOB_NAME,
        handler=payment_due.run,
        cron={"hour": 12, "minute": 0},  # daily ~09:00 AR
        description="Recordatorio de vencimiento de pago al inquilino (pre/due/mora).",
    ),
    JobDef(
        name=contract_alerts.JOB_NAME,
        handler=contract_alerts.run,
        cron={"hour": 12, "minute": 15},  # daily ~09:15 AR
        description="Aviso de contratos por vencer y próximo ajuste IPC (a la inmobiliaria).",
    ),
    JobDef(
        name=cold_leads.JOB_NAME,
        handler=cold_leads.run,
        cron={"hour": 12, "minute": 30},  # daily ~09:30 AR
        description="Re-engagement de leads fríos (sin actividad 7 días).",
    ),
    JobDef(
        name=weekly_report.JOB_NAME,
        handler=weekly_report.run,
        cron={"hour": 12, "minute": 45},  # daily; self-dedupes per ISO week (lunes)
        description="Reporte semanal al dueño (leads/visitas/top propiedades/cobranzas).",
    ),
    JobDef(
        name=monthly_snapshot.JOB_NAME,
        handler=monthly_snapshot.run,
        cron={"hour": 11, "minute": 30},  # daily; upserts last month's snapshot per sucursal
        description="Snapshot mensual de KPIs por sucursal (reportes ejecutivos Enterprise).",
    ),
    JobDef(
        name=monthly_report.JOB_NAME,
        handler=monthly_report.run,
        cron={"hour": 12, "minute": 55},  # daily; self-dedupes per month (mes anterior)
        description="Reporte ejecutivo mensual al dueño (consolidado por org).",
    ),
]


def get_job(name: str) -> JobDef | None:
    return next((j for j in JOBS if j.name == name), None)

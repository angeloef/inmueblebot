"""Scheduled jobs engine (Profesional proactive notifications).

A single in-process engine that runs the date-based, idempotent jobs behind the
Profesional 🔜 reminders: visit reminder (24h), payment-due reminder, contract-expiry /
IPC notice, weekly owner report, cold-lead re-engagement.

Design notes:
- Every job is **idempotent** and **date-based** so it is safe to run more than once and
  to "catch up" after the Render-free web service wakes from sleep.
- Every job iterates over active tenants via :func:`base.for_each_tenant`, opening its DB
  work inside ``tenant_scope`` so RLS isolates each inmobiliaria.
- Outbound WhatsApp goes through :mod:`app.services.notification_dispatch` (template gate).
"""

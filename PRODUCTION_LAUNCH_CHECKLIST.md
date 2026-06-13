# 🚀 ViviendApp — Checklist de salida a PRODUCCIÓN

> Qué cambiar y probar **antes de vender la app a inmobiliarias reales**.
> Estado actual: el código de las Fases 1–3 está en `main` y **verificado en sandbox**
> (suscripción MercadoPago autorizada end-to-end el 2026-06-09). Esto es la lista de
> cutover de sandbox → producción. Generado: 2026-06-09.

---

## 0. Resumen de lo que YA está hecho (no re-hacer)
- ✅ Auth JWT multi-tenant + tenant_accounts/subscriptions (Fase 1).
- ✅ Landing + signup/login Next.js (Fase 2), LIVE en `viviendapp-web.onrender.com`.
- ✅ MercadoPago **Suscripciones (preapproval)** + webhook + gating de trial + rate-limit (Fase 3).
- ✅ App MercadoPago "ViviendApp" creada; webhook `subscription_preapproval` apuntando a
  `https://inmueblebot-api.onrender.com/webhooks/mercadopago` (configurado vía MCP).
- ✅ Validado en sandbox: preapproval `authorized`, cobro recurrente mensual, sin dinero real.
- ✅ **Notificaciones programadas del plan Profesional** (motor de jobs + 5 recordatorios) y
  **Sitio web Fase A** (brief + pestaña "Mi sitio web") en `main`. Migraciones 0009→0012 corren
  solas en el deploy (`preDeployCommand: alembic upgrade head`). Ver §7 para la config de Render.

---

## 1. MercadoPago — pasar de sandbox a producción ⚠️ (lo más importante)

| Qué | Acción |
|---|---|
| **Access Token** | En Render `MERCADOPAGO_ACCESS_TOKEN` = token de **Credenciales de PRODUCCIÓN** de la app ViviendApp (`APP_USR-…`). Quitar cualquier `TEST-…`. |
| **Webhook Secret** | En Render `MERCADOPAGO_WEBHOOK_SECRET` = el secret del webhook de **producción** (panel → ViviendApp → Webhooks, modo producción). Es **distinto** al de prueba. |
| **Precio** | `MP_PLAN_PRICE_ARS` = precio real mensual (ej. `15000`). En el web, `NEXT_PUBLIC_PLAN_PRICE_ARS` para mostrarlo en `/checkout`. |
| **Webhook en panel** | Confirmar que el webhook de **producción** está activo, URL correcta, topic `subscription_preapproval` (opcional `subscription_authorized_payment` para trackear cada cobro). |
| **Homologación / Calidad** | Correr la evaluación oficial de calidad de MercadoPago (tool MCP `quality_checklist` / `quality_evaluation`, o panel). Algunas cuentas exigen homologación para habilitar suscripciones en prod. |
| **Cuenta cobradora** | La cuenta real de MercadoPago debe estar verificada y habilitada para **Suscripciones** (aceptar términos). |

> **Nota de tipos (lección del sandbox):** en producción NO hay problema de "payer/collector
> must both be test users" — el collector es tu cuenta real y el pagador es la inmobiliaria
> real con su propia cuenta MP. Ese error era solo del entorno de prueba.

### Prueba real obligatoria (post-cutover)
1. Setear `MP_PLAN_PRICE_ARS` bajo (ej. `1000`) temporalmente.
2. Signup → `/checkout` → "Suscribirme" → pagar con **tarjeta real propia**.
3. Verificar que el webhook llega (logs de Render: línea `[mp] preapproval … sincronizado → active`)
   y que el tenant queda `active` (`GET /auth/me`).
4. **Cancelar + reembolsar** esa suscripción desde el panel.
5. Subir `MP_PLAN_PRICE_ARS` al precio real.

---

## 2. Email (Resend) — dominio propio
- [ ] Registrar y **verificar un dominio** en Resend (SPF/DKIM).
- [ ] `EMAIL_FROM="ViviendApp <no-reply@tudominio.com>"` (hoy usa un from de prueba; sin dominio
      propio Resend solo envía a tu propio email).
- [ ] `RESEND_API_KEY` de producción seteada.
- [ ] Probar: signup real → llega email de verificación; forgot-password → llega reset.

---

## 3. Seguridad (revisar antes de exponer al público)
- [ ] `SECRET_KEY` ≠ default y fuerte (ya rotado; reconfirmar en Render).
- [ ] JWT solo en cookies **httpOnly + Secure + SameSite=Lax** (ya implementado; verificar en prod con HTTPS).
- [ ] `MERCADOPAGO_WEBHOOK_SECRET` seteado → webhook **fail-closed** (sin secret rechaza en prod). Confirmar que NO quede vacío.
- [ ] CORS: `allow_origins` del backend = dominio real del web (no `*`, no localhost) — `app/main.py`.
- [ ] Rate-limit de `/billing/subscribe` activo (5/5min por tenant) — ya está; confirmar Redis arriba.
- [ ] Considerar rate-limit en `/auth/*` (anti fuerza bruta) — Apéndice C del plan, pendiente.
- [ ] Quitar cualquier `MERCADOPAGO_ACCESS_TOKEN` `TEST-`/`APP_USR-` del `.env` **local** (quedó de las pruebas).
- [ ] `RENDER_KEY` del `.env` local: rotarla/quitarla si ya no se usa.

### 3.1 Límites client-side del bot V3 (ya en `main`, falta config en Render)
> El código de límites por usuario (anti cost-drain + anti abuso) ya está vivo en `main`.
> Lo único pendiente es **acción de config en Render** (no código).
- [ ] **`WHATSAPP_APP_SECRET`** seteado en Render → el webhook verifica la firma HMAC de Meta y
      **rechaza requests forjados**. Sin este secret el webhook **falla abierto** (cualquiera que
      conozca la URL puede inyectar turnos falsos = gasto de LLM + escrituras en DB bajo cualquier
      teléfono). Al arrancar, la app loguea un warning si está vacío.
- [ ] (Opcional) `USER_DAILY_MESSAGE_CAP` — tope de mensajes por usuario/día antes de handoff a
      humano + pausa del bot. Default `40`. Setear solo si querés otro valor (`0` lo desactiva).
- [ ] (Opcional) `OFFTOPIC_ABUSE_HANDOFF_THRESHOLD` — mensajes off-topic/abusivos acumulados antes
      de escalar a humano + pausa. Default `5`. Setear solo si querés otro valor (`0` lo desactiva).

---

## 4. Pendiente de fases siguientes (no bloquean cobrar, sí el producto completo)
- [ ] **Fase 4 — Dashboard Vite con JWT:** migrar el dashboard de `x-api-key` global a login JWT
      por tenant; aplicar `require_active_subscription` a las rutas del dashboard para que el
      gating 402 efectivamente bloquee a los trials vencidos. (Hoy el gating existe pero hay que
      enchufarlo a las rutas que sirve el dashboard.)
- [ ] **Fase 5 — WhatsApp Embedded Signup:** requiere aprobación **Meta Tech Provider** (semanas).
      Hasta entonces queda el placeholder. Setear `META_APP_ID/SECRET/CONFIG_ID`.
- [ ] Verificar firma `X-Hub-Signature-256` del webhook de Meta (Fase 5).

---

## 5. Operación / cobros
- [ ] Definir qué pasa al vencer el trial sin pago: hoy el gating da 402; confirmar que el job
      `mark_expired_trials` corre (cron) o que el gating en request alcanza.
- [ ] Manejo de `paused`/`cancelled`/`past_due` de MercadoPago → reflejado en `Subscription.status`
      (ya mapeado); decidir UX de reactivación (re-`/checkout`).
- [ ] Reembolsos/cancelaciones: documentar el proceso (panel MP → Suscriptores → Cancelar).

---

## 6. Antes del primer cliente real (smoke test de prod)
- [ ] Signup real desde el dominio público.
- [ ] Checkout real (tarjeta real, monto bajo) → webhook → tenant `active` → cancelar/reembolsar.
- [ ] Email de verificación llega a un email externo (no solo el tuyo).
- [ ] Dashboard accesible solo con suscripción activa / trial vigente.
- [ ] Logs de Render sin errores `[mp]` ni firmas inválidas.

---

## 7. Notificaciones programadas del plan Profesional (motor de jobs) ⏰
> Código en `main`. El motor (APScheduler in-process) arranca con la app. Lo proactivo por
> WhatsApp está **template-gated**: hasta tener plantillas HSM aprobadas, cada recordatorio
> **se encola como notificación en el dashboard** y NO se envía por WhatsApp (no rompe nada).

### 7.1 Config en Render (no código)
- [ ] **Migraciones**: confirmar en los logs del deploy que `alembic upgrade head` aplicó
      `0009`→`0012` (columnas `reminder_sent_at`, `reminder_stages`, alertas de contrato,
      `cold_reengaged_at` + tabla `tenant_site_briefs`). Aditivas y seguras (prod ya tiene `notifications`).
- [ ] **`ENABLE_SCHEDULER`** (default `True`): deja el scheduler corriendo dentro del web service.
      Ponelo en `False` solo si querés apagar todos los jobs.
- [ ] **`JOBS_SECRET`**: setealo para habilitar el trigger manual / cron externo
      (`POST /jobs/run?name=<job>` con header `X-Jobs-Secret`). Sin esta var el endpoint
      responde **503** (queda deshabilitado, no expuesto).
- [ ] (Opcional) **`SCHEDULER_CATCHUP_ON_START`** (default `True`): al bootear corre una pasada
      catch-up de los jobs idempotentes — cubre la ventana que el web service de Render free
      pierde mientras está dormido.

### 7.2 Caveat Render free (importante para que los recordatorios salgan a tiempo)
- [ ] El web service de Render **free se duerme** tras ~15 min de inactividad → APScheduler
      **no dispara dormido**. El catch-up al despertar lo mitiga (jobs idempotentes y por fecha),
      pero para envíos puntuales (p. ej. el reporte de los lunes) considerá **una de estas**:
      (a) plan que no duerma, o (b) un **cron externo gratis** (cron-job.org / GitHub Actions)
      que pegue `POST /jobs/run` cada X min con el `JOBS_SECRET`.

### 7.3 Para que los recordatorios SALGAN por WhatsApp de verdad (no solo dashboard)
> Requiere plantillas HSM aprobadas por Meta. Hasta entonces, todo queda en el dashboard.
- [ ] Aprobar en Meta las **plantillas HSM** (una por evento): visita 24h, vencimiento de pago,
      contrato por vencer, ajuste IPC, reporte semanal, leads fríos.
- [ ] Por cada inmobiliaria, cargar vía `PATCH /admin/tenants/{id}/settings`:
      - `wa_tpl_visit_reminder`, `wa_tpl_payment_due`, `wa_tpl_contract_expiry`,
        `wa_tpl_ipc_adjustment`, `wa_tpl_weekly_report`, `wa_tpl_cold_lead` = nombre de la plantilla aprobada.
      - **`owner_phone`** = WhatsApp del dueño (E.164 sin `+`): destino de las alertas de contrato/IPC
        y del reporte semanal. Vacío = esas alertas quedan solo en el dashboard.

### 7.4 Smoke test (post-deploy)
- [ ] Tras el deploy, revisar la **campana de notificaciones** del dashboard: si hay datos que
      matcheen (visita en <24h, cobro por vencer, etc.) deberían aparecer recordatorios encolados.
- [ ] Con `JOBS_SECRET` seteado: `POST /jobs/run?name=payment_due` (header `X-Jobs-Secret`) →
      responde `200` con el resumen por tenant (`due/queued/sent/…`).
- [ ] Pestaña **"Mi sitio web"**: completar el brief, "Guardar borrador" y "Enviar al equipo"
      → status pasa a `submitted` y llega notificación al equipo.

---

### Variables de entorno — resumen de cambios sandbox → prod
```
# Backend (Render) — PRODUCCIÓN
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...        # producción de ViviendApp (no TEST-)
MERCADOPAGO_WEBHOOK_SECRET=<secret prod>     # del webhook de producción
MP_PLAN_PRICE_ARS=15000                       # precio real
RESEND_API_KEY=<prod>
EMAIL_FROM="ViviendApp <no-reply@tudominio.com>"
PUBLIC_API_URL=https://inmueblebot-api.onrender.com
PUBLIC_APP_URL=https://viviendapp-web.onrender.com   # o dominio propio
SECRET_KEY=<fuerte, ya rotado>
WHATSAPP_APP_SECRET=<app secret de Meta>     # webhook fail-closed (rechaza forjados)
USER_DAILY_MESSAGE_CAP=40                     # opcional (default 40; 0 = off)
OFFTOPIC_ABUSE_HANDOFF_THRESHOLD=5            # opcional (default 5; 0 = off)
ENABLE_SCHEDULER=true                         # motor de jobs (default true)
SCHEDULER_CATCHUP_ON_START=true               # catch-up al boot (default true)
JOBS_SECRET=<secret fuerte>                   # habilita POST /jobs/run (sin esto = 503)

# Web (Render)
NEXT_PUBLIC_PLAN_PRICE_ARS=15000
NEXT_PUBLIC_API_URL=https://inmueblebot-api.onrender.com
```

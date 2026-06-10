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

# Web (Render)
NEXT_PUBLIC_PLAN_PRICE_ARS=15000
NEXT_PUBLIC_API_URL=https://inmueblebot-api.onrender.com
```

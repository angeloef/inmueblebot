# TODO — Completar planes Profesional y Enterprise

Implementaciones marcadas con 🔜 en `recommended_pricing_plans_v3.md`.
Orden sugerido (del propio doc): visita → reporte semanal → cobranzas → leads fríos → sitio web → multi-sucursal → documentos.

---

## Plan Profesional ⭐

- [x] **Recordatorio de visita 24h antes** al cliente por WhatsApp (reduce no-show) — ✅ motor de jobs (APScheduler in-process + catch-up al boot) + dispatch template-ready (encola al dashboard si no hay plantilla HSM) + job `visit_reminder` idempotente (`appointments.reminder_sent_at`, migración 0009) + endpoint `POST /jobs/run` (secret). Tests: `tests/test_jobs_engine.py`.
- [x] **Recordatorio automático de vencimiento de pago** por WhatsApp al inquilino (cobranzas) — ✅ job `payment_due` con 3 etapas idempotentes (3 días antes / día del vencimiento / mora +3 días), reusa `build_reminder_message`. Idempotencia: `charges.reminder_stages` (migración 0010).
- [x] **Aviso de contratos por vencer** y de próximo ajuste IPC (cobranzas) — ✅ job `contract_alerts`: vencimiento 30 días antes + aviso IPC 7 días antes de cada ajuste, a dashboard + WhatsApp al dueño (tenant setting `owner_phone`). Idempotencia: `contracts.expiry_alert_sent_at` + `ipc_alert_for` (migración 0010).
- [x] **Reporte semanal por WhatsApp** al dueño: leads / visitas / propiedades top, cada lunes — ✅ job `weekly_report`: leads nuevos + visitas (agendadas/realizadas/no-show) + top propiedades + resumen de cobranzas (cobrado/por cobrar/vencidos/por vencer). Al `owner_phone`, dedupe por semana ISO (tenant setting `weekly_report_last`).
- [x] **Seguimiento automático de leads fríos**: re-engagement a los 7 días sin actividad — ✅ job `cold_leads`: one-shot por enfriamiento (`users.cold_reengaged_at`, migración 0011), excluye no-prospects (rol lost/tenant/owner), inquilinos con contrato activo, visitas futuras y conversaciones en handoff (`bot_paused`).
- [~] **Sitio web con catálogo**: página propia de la inmobiliaria con propiedades sincronizadas automáticamente — 🟡 **Fase A hecha** (data model + workflow de captura). Falta Fase B (web pública + sync).
  - ✅ **Fase A (esta sesión)**: modelo `SiteBrief` (`tenant_site_briefs`, 1 por tenant, RLS, migración 0012) con secciones JSONB (brand/pitch/contact/domain/design/catalog); API CRUD `GET/PUT /site-brief` + `POST /site-brief/submit` (auth por tenant); pestaña dashboard **"Mi sitio web"** (`dashboard/src/Website.jsx`) — formulario guiado por pasos con presets de diseño (estilo/tono) + texto libre, bloque de dominio (tienen/cuál/¿lo compramos?), config de catálogo. Tests: `tests/test_site_brief.py` (3, scoping RLS verificado). Decisiones: dominio propio por inmobiliaria (compra/DNS manual del founder), sin plantillas de ejemplo, armado manual del founder a partir del brief.
  - 🔜 **Fase B (pendiente)**: render de la web pública por tenant (dominio propio), sync automático del catálogo desde `properties`, ficha con galería + filtros + CTA al WhatsApp del bot.
  - No es solo "renderizar las propiedades en una web". El núcleo es un **workflow de onboarding** que le pida al tenant (la inmobiliaria), una sola vez y de forma guiada, **todos los datos necesarios para que nosotros armemos su web sin tener que preguntar nada manualmente** después.
  - El workflow debe recolectar, como mínimo:
    - **Identidad/marca**: nombre comercial, logo, colores, tipografía si tienen manual de marca, fotos del local/equipo.
    - **Pitch y posicionamiento**: cómo se describe la inmobiliaria, su historia, su diferencial, a qué público apunta (alquiler vs venta, zona, segmento). Este texto es **personalizado por dueño** y va en el hero/“sobre nosotros”.
    - **Contacto y operación**: WhatsApp, teléfono, email, dirección, horarios, redes sociales, matrícula/colegiado.
    - **Preferencias de diseño visual**: la **opinión del dueño sobre el estilo importa** — ofrecer opciones (p. ej. moderno / clásico / minimalista / lujo) con previews, no dejarlo en blanco. El dueño elige dirección visual, no la imponemos.
    - **Catálogo**: confirmar que las propiedades a publicar salen del sistema (sync automático), qué campos se muestran y cuáles se ocultan.
  - Tener en cuenta que **son webs del rubro inmobiliario**: plantilla/base pensada para listados de propiedades (filtros por operación/zona/precio/ambientes, ficha de propiedad con galería, CTA a WhatsApp del bot), no un site genérico.
  - Resultado esperado: con lo que el dueño carga en el workflow, **nosotros generamos la web** (semi-automática) sin idas y vueltas manuales por cada requisito.

## Plan Enterprise (todo lo anterior +)

- [ ] **Multi-sucursal**: datos separados por sucursal + dashboard consolidado para el dueño
- [ ] **Documentos vinculados a clientes/contratos**: DNI, recibos, contratos firmados en la ficha del cliente
- [ ] **Reportes ejecutivos mensuales**: comparativa mes a mes, tendencias por zona/tipo
- [ ] **Exportación de datos**: leads, conversaciones, cobranzas
- [ ] **Métricas avanzadas para Enterprise (replantear el set completo)**: hoy hay embudo / tasa de conversión / ranking de propiedades (suficiente para Profesional). Para Enterprise hay que **diseñar el panel de métricas pensando en TODO lo que le sirve a una inmobiliaria con estructura**, aunque todavía no esté implementado. Candidatas a definir/medir:
  - **Por sucursal** (consolidado y comparativo): leads, visitas, conversión, cobranzas por sucursal — aprovecha multi-sucursal.
  - **Por agente**: leads atendidos, tiempo de respuesta, visitas agendadas, cierres, ranking de performance del equipo.
  - **Embudo extendido**: lead → conversación → visita agendada → visita realizada (no-show) → operación cerrada, con tasa en cada paso.
  - **Tiempos**: tiempo medio de respuesta del bot/agente, tiempo de propiedad en cartera, días hasta alquilar/vender.
  - **Demanda de mercado**: zonas/tipos/rangos de precio más buscados vs. lo que tienen en cartera (gap de oferta-demanda), búsquedas sin resultado.
  - **Cobranzas/financiero**: morosidad, % cobrado en término, contratos por vencer, proyección de ingresos por ajustes IPC.
  - **Cartera**: propiedades activas/pausadas/cerradas, propiedades sin consultas (“muertas”), antigüedad promedio.
  - **Operación del bot**: volumen de conversaciones, handoffs a humano, satisfacción, horarios pico.
  - El objetivo del TODO no es construir todas hoy, sino **decidir el catálogo de métricas Enterprise y el modelo de datos que las soporte** para no rehacerlo después.

---

### Ya implementado (no requiere trabajo)
Cobranzas (base), Equipos (hasta 5 usuarios), Métricas avanzadas (embudo/conversión/ranking).

### Notas
- 4 de los 6 ítems del Profesional son **notificaciones programadas** (visita, vencimiento, contratos por vencer, reporte semanal, leads fríos) → conviene un solo motor de scheduler/jobs que los cubra a todos.
- El **sitio web con catálogo** es el ítem más grande (frontend público nuevo + sync).
- **Multi-sucursal** toca el modelo de datos multi-tenant (otra capa de scoping por debajo de la inmobiliaria).

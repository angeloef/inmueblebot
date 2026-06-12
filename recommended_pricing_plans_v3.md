# ViviendApp / InmuebleBot — Planes de Precios v3
## Pricing de lanzamiento · Penetración con margen · Junio 2026

> Reemplaza a `recommended_pricing_plans.txt` (v1) y `recommended_pricing_plans_v2.txt`.
> Decisiones tomadas con el founder (jun 2026): penetración agresiva pero siempre por encima del costo,
> Cobranzas desde Profesional, Enterprise con precio "desde X" + hablar con ventas.

---

## 0. Resumen Ejecutivo

| | **BÁSICO** | **PROFESIONAL** ⭐ | **ENTERPRISE** |
|---|:---:|:---:|:---:|
| **Precio mensual** | **$39.900 ARS** | **$84.900 ARS** | **desde $169.900 ARS** |
| **Precio anual (-20%)** | $31.900/mes | $67.900/mes | a medida |
| Conversaciones/mes | 250 | 600 | 1.500 (ampliable) |
| Usuarios | 1 | Hasta 5 | Ilimitados |
| Propiedades | Hasta 50 | Ilimitadas | Ilimitadas |
| Cobranzas (alquileres + IPC) | ❌ | ✅ | ✅ |
| Sitio web con catálogo | ❌ | ✅ 🔜 | ✅ 🔜 |
| Multi-sucursal | ❌ | ❌ | ✅ 🔜 |
| Target | Agente solo / inmob. de 1-2 personas | Inmobiliaria 2-5 agentes con cartera de alquileres | Inmobiliaria grande / multi-sucursal / desarrolladora |

✅ = ya implementado en la app · 🔜 = a construir en 1-2 meses (corto plazo, ya acordado)

**Toda la oferta:** 30 días gratis con plan completo, sin tarjeta. Facturación en ARS con revisión trimestral. Pago con Mercado Pago (ya integrado).

---

## 1. Plan Básico — $39.900 ARS/mes

*"Tu inmobiliaria responde sola, 24/7."* Para el agente independiente o la inmobiliaria chica que pierde leads por no contestar a tiempo.

**Incluye (todo ya implementado):**
- 🤖 Chatbot IA 24/7 en WhatsApp: responde consultas, busca propiedades por zona/tipo/presupuesto, envía fichas y fotos
- 📅 Agendado automático de visitas con Google Calendar (confirmación, anti doble-booking, validación de horarios laborales)
- 🙋 Derivación a humano: el bot detecta cuándo escalar y pausa; el agente sigue la conversación desde el dashboard
- 📥 Inbox de conversaciones en el dashboard (historial completo de cada cliente)
- 👤 CRM de leads: datos de contacto, preferencias detectadas, historial, estado
- 🏠 Gestión de hasta **50 propiedades** con fotos
- ❓ FAQs configurables (el bot responde con la info de TU inmobiliaria: horarios, requisitos, comisiones)
- 📊 Métricas básicas: leads nuevos, visitas agendadas, conversaciones
- 🗓️ Calendario de visitas en el dashboard
- 1 usuario · 1 número de WhatsApp · **250 conversaciones/mes**
- 🆘 Soporte por email/WhatsApp (respuesta <24h hábiles)

**Pitch de venta:** un empleado que atienda WhatsApp medio día cuesta $400.000+/mes. El bot cuesta el 10% de eso y no duerme.

---

## 2. Plan Profesional — $84.900 ARS/mes ⭐ (el plan que queremos vender)

*"Gestioná ventas, alquileres y tu equipo en un solo lugar."* Para la inmobiliaria establecida con cartera de alquileres y 2+ agentes.

**Todo lo del Básico, más:**
- 🏠 **Propiedades ilimitadas** y **600 conversaciones/mes**
- 💰 **Cobranzas** (✅ implementado — diferenciador: ningún competidor barato lo combina con chatbot):
  - Gestión de contratos de alquiler y estado de pagos
  - Ajuste por IPC
  - 🔜 Recordatorio automático de vencimiento de pago por WhatsApp al inquilino
  - 🔜 Aviso de contratos por vencer y de próximo ajuste IPC
- 👥 **Equipos** (✅ implementado): hasta 5 usuarios con invitación por email, cada agente ve sus conversaciones y visitas
- 📊 Métricas avanzadas (✅): embudo de conversión, tasa de conversión, ranking de propiedades más consultadas
- 🌐 🔜 **Sitio web con catálogo**: página propia de la inmobiliaria con sus propiedades sincronizadas automáticamente
- 📈 🔜 **Reporte semanal por WhatsApp**: resumen de leads/visitas/propiedades top enviado al dueño cada lunes
- 🔄 🔜 **Seguimiento automático de leads fríos**: re-engagement a los 7 días sin actividad
- ⏰ 🔜 **Recordatorio de visita** 24h antes al cliente (reduce no-show)
- 🆘 Soporte prioritario (<4h hábiles) + onboarding guiado 1:1

**Pitch de venta:** Mapaprop Business (con asistente IA) cuesta $88.900 y no gestiona alquileres ni agenda visitas solo. Acá entra todo por menos.

---

## 3. Plan Enterprise — desde $169.900 ARS/mes

*"Para inmobiliarias con estructura."* Precio publicado como **"desde $169.900"** — transparente pero flexible: requisitos mayores (más sucursales, más volumen, integraciones) se cotizan con ventas.

**Todo lo del Profesional, más:**
- 🏢 🔜 **Multi-sucursal**: datos separados por sucursal, dashboard consolidado para el dueño
- 👥 **Usuarios ilimitados** y **1.500 conversaciones/mes** incluidas (ampliable por contrato)
- 📱 Múltiples números de WhatsApp (uno por sucursal)
- 📄 🔜 **Documentos vinculados a clientes/contratos**: DNI, recibos, contratos firmados, todo en la ficha del cliente
- ⚙️ API / integraciones custom (sistemas contables, CRM propio)
- 📈 🔜 Reportes ejecutivos mensuales (comparativa mes a mes, tendencias por zona/tipo)
- 📤 🔜Exportación de datos (leads, conversaciones, cobranzas)
- ☁️ SLA 99,9% · cuenta dedicada · onboarding completo del equipo
- 🆘 Soporte VIP: canal directo con respuesta <1h hábil

**CTA:** "Hablar con ventas" (no checkout self-serve). El precio publicado ancla la negociación.

---

## 4. Unit Economics — por qué estos precios dejan margen

**Costo del chatbot: $5 ARS por mensaje contestado.** Referencia del founder: inmobiliaria intensiva (10 consultas/día × ~17 mensajes contestados) ≈ **$25.000 ARS/mes**. Eso da **~$85 ARS por conversación** en el peor caso (conversación larga). Hosting <$40 USD/mes total (ignorable por ahora). Comisión MP + impuestos ≈ **7%** del precio.

### Margen por plan (peor caso = todas las conversaciones largas, cupo lleno)

| Plan | Precio | Cupo conv. | Costo bot peor caso | Fee 7% | **Margen peor caso** | Costo típico (½ cupo) | **Margen típico** |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Básico | $39.900 | 250 | $21.250 | $2.800 | **$15.850 (40%)** | $10.600 | **$26.500 (66%)** |
| Profesional | $84.900 | 600 | $51.000 | $5.900 | **$28.000 (33%)** | $25.500 | **$53.500 (63%)** |
| Enterprise | $169.900 | 1.500 | $127.500 | $11.900 | **$30.500 (18%)** | $63.750 | **$94.250 (55%)** |

**Regla de seguridad:** ningún plan puede perder plata ni en el peor caso. El cupo de conversaciones es la válvula:

- Al llegar al 80% del cupo → aviso al cliente
- Cupo lleno → opción de **pack de 100 conversaciones extra: $12.000 ARS** (costo peor caso $8.500 → siempre margen) o upgrade de plan
- El cupo se elige como métrica de valor porque escala con el negocio del cliente: más conversaciones = más leads = más comisiones para él → upgrade natural (modelo Twilio/Intercom/WATI: cobrar por la métrica que crece con el éxito del cliente)

---

## 5. Benchmark Competitivo Real (junio 2026, verificado)

| Competidor | Plan comparable | Precio | Qué le falta vs nosotros |
|---|---|:---:|---|
| **Mapaprop** Plus | CRM + portales | $10.700 | Sin bot, sin agenda, sin cobranzas |
| **Mapaprop** Pro+ | + sitio web | $26.700 | Sin bot IA, sin cobranzas |
| **Mapaprop** Business | + asistente IA, MLS, API | **$88.900** | El chat IA no agenda visitas ni gestiona alquileres |
| **Adinco** Platinum | CRM + web + portales | **$111.600 + IVA** | Sin chatbot IA, sin cobranzas |
| **Tokko Broker** | CRM líder | no publica (cotiza) | Sin chatbot IA conversacional |
| Chatbots WhatsApp genéricos (WATI/Landbot) | solo bot | USD 16-50 + costos Meta | Sin CRM inmobiliario, sin agenda, sin cobranzas, en USD |

**Lectura del posicionamiento:**
- Básico $39.900 → entra **por debajo** de cualquier solución con IA del mercado, pero por encima de los CRM "tontos" baratos: el bot lo justifica
- Profesional $84.900 → **undercut directo** de Mapaprop Business ($88.900) y Adinco Platinum ($111.600+IVA) con más funcionalidad (bot que agenda + cobranzas)
- Enterprise desde $169.900 → muy por debajo del Business Manager de Mapaprop ($533.000): espacio enorme para crecer el precio con la demanda
- Lo que NO hacemos: competir contra los planes free de Mapaprop/Adinco. Nuestro cliente no compra un CRM, compra **no perder leads a las 11 de la noche**

---

## 6. Estrategia Early-Stage (playbook de SaaS B2B exitosos)

1. **Cobrar desde el día 1** (Basecamp, ConvertKit): el trial de 30 días es la única gratuidad. Un cliente que paga $39.900 valida más que 20 gratis.
2. **Precio Fundador** (lo que hizo Superhuman/Linear en beta): primeras **15 inmobiliarias** → **-30% de por vida del plan que elijan** ($27.900 / $59.400) a cambio de: testimonio + caso de éxito con números + feedback quincenal. Crea urgencia ("quedan X cupos") y los primeros logos.
3. **Design partners para Enterprise** (playbook YC): no vender Enterprise self-serve todavía. Elegir 2-3 inmobiliarias multi-sucursal de Posadas/Corrientes y co-construir multi-sucursal + documentos con ellas pagando precio fundador Enterprise (~$120.000).
4. **Onboarding manual** ("do things that don't scale", Airbnb/Stripe): el founder carga las primeras 10 propiedades y configura el bot en una videollamada de 40 min. La activación es el momento de mayor churn-risk en SaaS.
5. **Conversión del trial guiada por valor**: mensaje día 25 por WhatsApp con los números del cliente (leads atendidos, visitas agendadas) + link de pago MP. Ya existe la infra de notificaciones.
6. **Referidos**: 1 mes gratis por cada inmobiliaria referida que pase a pago (CAC casi cero; las inmobiliarias del interior se conocen todas).
7. **Anual -20%** (paga 12, vale 9.6): mejora cashflow en un país de inflación — para el cliente es cobertura, para nosotros capital de trabajo.
8. **Subir precios cada ~2 trimestres con grandfathering**: los precios de penetración son de lanzamiento. Con 30+ clientes y testimonios, nueva cohorte paga más; los existentes conservan su precio (lealtad + urgencia de entrar ahora).

### Por qué penetración y no valor-alto ahora
Sin testimonios ni marca, el precio alto agrega fricción a cada demo. Con margen típico del 55-66% incluso a precios bajos (sección 4), el objetivo de los primeros 6 meses **no es MRR, es densidad de casos de éxito por ciudad**: 10 inmobiliarias en Posadas valen más que 10 dispersas, porque el interior compra por referencia.

---

## 7. Easy Wins Adicionales Propuestos (descartá lo que no te cierre)

Ya incluidos arriba en los planes (marcados 🔜): reporte semanal, leads fríos, sitio web catálogo, recordatorio de visita, recordatorios de cobranza, multi-sucursal, documentos.

Extras de bajo esfuerzo que resuelven dolores reales de inmobiliarias:

| Easy win | Esfuerzo | Plan sugerido | Dolor que resuelve |
|---|:---:|:---:|---|
| Recibo de alquiler en PDF automático | Bajo | Profesional | Hoy lo hacen a mano en Word todos los meses |
| Import masivo de propiedades por Excel | Bajo | Todos | Fricción #1 del onboarding |
| Plantillas de respuesta rápida en el inbox | Bajo | Todos | Agentes repiten lo mismo 50 veces/día |
| Etiquetas/estados de lead personalizables | Bajo | Profesional | Cada inmobiliaria tiene su propio embudo |
| Encuesta post-visita automática por WhatsApp | Bajo-Medio | Profesional | Saber por qué no cerró; feedback del propietario |
| Export CSV de leads/cobranzas | Bajo | Profesional | "¿Y si me quiero ir?" — reduce miedo al lock-in y da confianza |
| Aviso "lead caliente sin respuesta hace 2h" | Medio | Enterprise | El dueño detecta agentes que dejan plata sobre la mesa |

---

## 8. Próximos Pasos

1. Validar estos precios → actualizar `web/src/components/landing/Pricing.tsx` (hoy: $55k/$66k/$110k y nombres Starter/Pro/Equipo → decidir si renombrar a Básico/Profesional/Enterprise)
2. Alinear `subscription_service.py` / gating 402 con los 3 planes y sus límites (conversaciones, usuarios, propiedades)
3. Implementar contador de conversaciones por tenant con aviso al 80% (la infra de límites diarios ya existe — extender a mensual por plan)
4. Definir los 15 cupos de Precio Fundador y el mensaje de venta
5. Priorizar los 🔜 de corto plazo: orden sugerido = recordatorio de visita → reporte semanal → recordatorios de cobranza → leads fríos → sitio web catálogo → multi-sucursal → documentos

---

*Fuentes de benchmark: Mapaprop planes (mapaprop.com/planes, jun 2026), Adinco precios (adinco.net/precios, jun 2026), Tokko Broker (no publica precios), guías de pricing de chatbots WhatsApp LATAM 2026 (asisteclick.com, aurorainbox.com). Research interno: reporte_inmobiliarias_argentina.md (~21.000 inmobiliarias empleadoras, 7.500 tradicionales), argentina_digital_maturity_research.md (75% de PyMEs del interior sin web; WhatsApp como canal dominante).*

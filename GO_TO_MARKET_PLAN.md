# ViviendApp / InmuebleBot — Go-To-Market Plan
## Argentina → LATAM · Bootstrap rentable · Junio 2026

> **Premisas acordadas con el founder:** 2 personas (uno vende/onboardea, otro sostiene producto) · 0 clientes hoy, producto listo · presupuesto inicial $0 con reinversión del 100% de las ganancias tempranas · sin inversores (bootstrap) · pricing según `recommended_pricing_plans_v3.md` (Básico $39.900 / Profesional $84.900 / Enterprise desde $169.900 ARS).
> **Tipo de cambio asumido:** $1.200 ARS/USD. Toda cifra en USD es referencial.

---

## 1. Resumen Ejecutivo

```
ETAPA 0          ETAPA 1           ETAPA 2            ETAPA 3            ETAPA 4              ETAPA 5
Mes 0-1          Mes 2-4           Mes 5-9            Mes 10-15          Mes 16-24            Año 3+
PRIMEROS 5       BEACHHEAD NEA     NACIONAL DIGITAL   CONSOLIDACIÓN      MÁQUINA + LATAM-0    LATAM
Oberá/Posadas    Posadas/Ctes/     Córdoba/Santa Fe/  AMBA + Enterprise  Paraguay/Uruguay     México/Colombia/
a pie            Resistencia       Mendoza remoto     + 1er vendedor     + self-serve         Chile/Perú
─────────        ─────────         ─────────          ─────────          ─────────            ─────────
3-5 clientes     12-18 clientes    35-50 clientes     70-100 clientes    130-170 clientes     300-1.000+
MRR ~$160k ARS   MRR ~$800k ARS    MRR ~$2,9M ARS     MRR ~$6M ARS       MRR ~$11M ARS        USD 50k+ MRR
(~USD 130)       (~USD 670)        (~USD 2.400)       (~USD 5.000)       (~USD 9.200)         (aspiracional)
```

**La meta a 24 meses: ~150 clientes y ~USD 110.000 ARR**, con el negocio pagando dos sueldos dignos desde el mes ~10-12. Es deliberadamente conservador frente a los comparables confirmados (sección 3) porque arrancamos sin capital, sin marca y con un solo vendedor.

---

## 2. El Mercado (datos del research propio)

| Capa | Cantidad | Fuente |
|---|---:|---|
| **TAM** — inmobiliarias empleadoras en Argentina | 21.193 | CEP XXI / AFIP (oct 2023) |
| Total con monotributistas/unipersonales | ~29.000-31.000 | SRT vía Infobae |
| **SAM** — inmobiliarias "tradicionales" (corredores, comisiones) | 7.547 | CLAE 681098 |
| **Prueba de que el SAM paga SaaS** | Tokko Broker: 4.200+ usuarios pagos en Argentina | tokkobroker.com |
| **SOM 24 meses** — ~2% del SAM tradicional | **~150 clientes** | este plan |

Distribución geográfica del TAM: CABA ~42%, Buenos Aires ~26%, Córdoba ~8%, Santa Fe ~6,5%, Misiones ~0,9% (~190-450 inmobiliarias), Corrientes+Chaco ~1,6%.

**Lectura estratégica:** el NEA es chico (~600-900 inmobiliarias) pero es nuestro patio: cero competencia de chatbot IA, venta presencial posible, el interior compra por referencia. Es el beachhead, no el negocio. El negocio está en Córdoba/Santa Fe/AMBA (76% del mercado), que se ataca remoto con casos de éxito en mano. La paradoja a favor: en el interior el 75% de las PyMEs no tiene web y WhatsApp ES el canal de ventas (research de madurez digital) — un producto WhatsApp-first no les pide cambiar de hábito, a diferencia de Tokko.

---

## 3. Casos de Éxito Confirmados que Calibran las Estimaciones

| Empresa | Datos confirmados | Qué nos enseña |
|---|---|---|
| **Tokko Broker** (ARG) | CRM inmobiliario #1 de Argentina. 1.800 profesionales en <2 años desde el lanzamiento; hoy 4.200+ usuarios pagos; adquirida por Navent. | Las inmobiliarias argentinas SÍ pagan SaaS mensual por miles. Nuestro SOM de 150 clientes = 3,5% de la base actual de Tokko. Su debilidad: no es conversacional ni WhatsApp-first. |
| **Sirena** (ARG, 2016) | CRM de ventas por WhatsApp nacido en Buenos Aires. Levantó USD 2,8M (2018); llegó a ~700 clientes en 30+ países en 4 años; adquirida por Zenvia (jul 2020); 55 empleados. | Validó que las empresas argentinas pagan por vender por WhatsApp, y que el playbook ARG→LATAM funciona. Con funding y 50 personas hizo ~700 clientes en 4 años → nuestros 150 en 2 años con 2 personas es ambicioso pero proporcionado (vertical más enfocada, ticket menor, venta más simple). |
| **Cliengo** (ARG, 2015) | Chatbot B2B argentino **bootstrapped** (sin inversión externa reportada): USD 4,9M revenue 2023 → USD 7M en 2024, 10.000+ empresas en 22 países, 72 empleados. | El techo del camino bootstrap existe y es argentino: se puede llegar a USD 7M ARR sin inversores. Tardó ~8-9 años. Freemium les funcionó porque su bot era de instalación self-serve — nosotros somos high-touch al inicio, freemium NO (trial 30 días sí). |
| **WATI** (HK, 2020) | Plataforma WhatsApp API: miles de clientes en 54 países en su primer año; USD 3,8M (2023) → 9,6M (2024); 8.000+ empresas. Levantó USD 35M. | La demanda global por "vender por WhatsApp" es enorme y creciente. Su velocidad la financió Tiger Global — no es nuestro benchmark de ritmo, sí de demanda. |
| **ConvertKit** (USA) | Nathan Barry, bootstrap público: ~24 meses de venta directa fundador-a-cliente para llegar a ~USD 5k MRR; despegó con migraciones concierge (hacerle el trabajo sucio al cliente). | El patrón de los primeros 12-18 meses bootstrap: lento, manual, directo. Nuestro equivalente del "concierge" es cargarle las propiedades y configurar el bot nosotros. Su curva calibra nuestras etapas 0-2. |
| **Mapaprop / Adinco** (ARG) | Competidores actuales: Mapaprop Business $88.900/mes (IA básica), Adinco Platinum $111.600+IVA. Ambos venden hoy a inmobiliarias argentinas. | Hay mercado activo pagando estos precios HOY. Nuestro Profesional ($84.900) entra debajo de ambos con más producto. |

**Conclusión de calibración:** ningún comparable bootstrap pasó de ~5 clientes/mes en su primer año con un solo vendedor. El plan asume 2-4/mes (etapas 0-1), 5-7/mes (etapa 2) y 8-12/mes (etapa 3+, ya con comisionista y referidos compuestos). Churn asumido: 5% mensual (rango típico 3-7% en SaaS SMB; LATAM tiende al techo).

---

## 4. Las Etapas

### ETAPA 0 — "Los primeros 5" (Mes 0-1) · Oberá + Posadas, a pie

**Objetivo:** 3-5 clientes PAGANDO con Precio Fundador (-30% de por vida). No son pilotos gratis: si nadie paga ni con descuento fundador, el problema es de producto o pitch y hay que arreglarlo antes de escalar.

**Tácticas (presupuesto $0, solo tiempo del socio vendedor):**
- Lista de las 40-60 inmobiliarias de Oberá y Posadas (Google Maps + colegio de corredores de Misiones). Priorizar las que ya responden consultas por WhatsApp y tienen cartera de alquileres (les pega Cobranzas).
- **Demo en vivo de 10 minutos en el local**: el vendedor le escribe al bot delante del dueño consultando por una propiedad real de esa inmobiliaria (precargada la noche anterior). Ver al bot vender TU propiedad es el momento mágico — no se vende con slides.
- Cierre con urgencia honesta: "Precio Fundador para las primeras 15 inmobiliarias del país: $27.900 (Básico) / $59.400 (Profesional) de por vida, a cambio de testimonio y feedback quincenal."
- Onboarding concierge (lección ConvertKit): nosotros cargamos las propiedades, configuramos FAQs y dejamos el bot andando en el día.

**Métricas de éxito / gate para pasar a Etapa 1:**
- ≥30 demos ofrecidas, ≥12 realizadas, ≥5 trials activados, **≥3 pagando al cierre del mes 1**
- Si <2 pagan: STOP. Iterar pitch/producto con los trials antes de gastar pólvora en el resto del NEA.

**Resultado esperado:** 3-5 clientes · MRR ~$130-220k ARS (~USD 110-180)

---

### ETAPA 1 — Beachhead NEA (Meses 2-4) · Posadas, Corrientes, Resistencia

**Objetivo:** 12-18 clientes activos y la maquinaria de referidos encendida. El NEA completo tiene ~600-900 inmobiliarias: capturar el 2% es suficiente para esta etapa.

**Tácticas:**
- **Referidos desde el día 1** (1 mes gratis por inmobiliaria referida que pague): en ciudades donde todos los corredores se conocen, es el canal de menor CAC que existe.
- Viaje mensual a Corrientes/Resistencia (bus, costo trivial) con 8-10 demos agendadas previamente por WhatsApp.
- **Colegios de corredores** (Misiones, Corrientes, Chaco): ofrecer charla gratuita "IA y WhatsApp para inmobiliarias del interior" — posiciona como experto local, genera lista de interesados. Es el equivalente regional del playbook de comunidad de los SaaS exitosos.
- Primer **caso de éxito documentado** con números reales: "La inmobiliaria X de Posadas atendió 84 consultas y agendó 11 visitas en su primer mes, fuera de horario el 40%". Este documento ES el activo de venta de la Etapa 2.
- Grupos de Facebook/WhatsApp de corredores del NEA: contenido útil (no spam) + el caso de éxito.
- **Reinversión arranca:** con MRR > $500k ARS, destinar ~$150-250k/mes (USD 125-200) a ads Meta segmentados "inmobiliaria + Posadas/Corrientes/Resistencia" para llenar la agenda de demos.

**Gate para pasar a Etapa 2:** ≥12 clientes pagos, churn <8%/mes, ≥2 clientes llegados por referido, 1 caso de éxito escrito + 1 testimonio en video.

**Resultado esperado:** 12-18 clientes · MRR ~$700k-1,1M ARS (~USD 600-900)

---

### ETAPA 2 — Salto Nacional Digital (Meses 5-9) · Córdoba, Santa Fe/Rosario, Mendoza, interior BsAs

**Objetivo:** 35-50 clientes. Probar que la venta REMOTA funciona (demo por videollamada + onboarding remoto), porque sin eso no hay escala ni LATAM.

**Por qué estas provincias y no CABA todavía:** Córdoba (~1.700 inmobiliarias), Santa Fe (~1.400) y Mendoza (~550) tienen cultura de interior (WhatsApp-first, menos saturadas de proveedores) pero mercado 10x el NEA. CABA es donde Tokko es más fuerte y el costo de adquisición más alto — se ataca en Etapa 3 con más espalda.

**Tácticas:**
- **Demo remota estandarizada de 15 min** (Meet + el vendedor le muestra el bot respondiendo en su propio WhatsApp). Meta: 10-15 demos/semana de capacidad con un vendedor full-time.
- Ads Meta/Google con presupuesto creciente financiado por MRR (regla: **30-40% del MRR a adquisición** mientras el margen lo permita — el costo variable del bot deja 55-65% de margen típico).
- **Contenido WhatsApp-first**: video corto del bot agendando una visita real → es el formato que las inmobiliarias entienden en 30 segundos. Distribución: Instagram/TikTok/grupos del rubro.
- Outbound quirúrgico: scraping de inmobiliarias en ZonaProp/Argenprop por ciudad → WhatsApp directo al dueño con el caso de éxito del NEA ("una inmobiliaria como la tuya en Posadas...").
- Automatizar el onboarding parcialmente (import Excel de propiedades, wizard de FAQs) para bajar el costo por alta de ~4h a ~1h.
- Lanzar los 🔜 del pricing v3 que empujan upgrade a Profesional: reporte semanal, recordatorios de cobranza, sitio web catálogo.

**Gate para Etapa 3:** ≥35 clientes, la venta remota cierra ≥15% de las demos, CAC por ads <1,5 meses de ARPU (~$90-100k ARS), churn <6%.

**Resultado esperado:** 35-50 clientes · MRR ~$2,4-3,4M ARS (~USD 2.000-2.800) · **A partir de acá el negocio ya banca un sueldo y medio**

---

### ETAPA 3 — Consolidación + AMBA + Enterprise (Meses 10-15)

**Objetivo:** 70-100 clientes, primer vendedor comisionista, y abrir el segmento Enterprise con 2-3 design partners multi-sucursal.

**Tácticas:**
- **Contratar vendedor comisionista** (modelo: base chica + 15-20% del primer año del cliente). Con un playbook de demo probado en Etapa 2, un comisionista del rubro inmobiliario se paga solo. Es el primer hire de casi todos los SaaS bootstrap exitosos.
- Entrar a **AMBA** (42% del mercado): acá la batalla es contra Tokko/Adinco con el ángulo "ellos te organizan, nosotros te VENDEMOS — el bot atiende, califica y agenda solo". Precio Profesional debajo de Mapaprop Business ayuda.
- **Enterprise por diseño conjunto**: elegir 2-3 inmobiliarias multi-sucursal (Posadas/Córdoba/Rosario) y co-construir multi-sucursal + documentos + API con ellas a precio fundador Enterprise (~$120-140k). Sus logos venden la Etapa 4.
- Partnership con **portales y colegios provinciales**: descuento para matriculados a cambio de difusión oficial.
- Subir precios a la cohorte nueva (+15-25%) con grandfathering — ya hay 50+ clientes y testimonios que justifican el valor (playbook estándar de pricing SaaS).
- Self-serve completo: signup → carga propiedades → conexión WhatsApp → pago MP sin tocar humano (necesario para LATAM).

**Gate para Etapa 4:** ≥70 clientes, MRR ≥ USD 4.500, el comisionista cierra solo, churn <5%, ≥2 Enterprise pagando.

**Resultado esperado:** 70-100 clientes · MRR ~$5-7M ARS (~USD 4.200-5.800) · **2 sueldos dignos + comisionista + caja para invertir**

---

### ETAPA 4 — Máquina Argentina + LATAM fase 0 (Meses 16-24)

**Objetivo:** 130-170 clientes en Argentina y validación de la primera expansión sin esfuerzo estructural: **Paraguay y Uruguay**.

**Por qué PY/UY primero (y no México):**
- Encarnación está literalmente cruzando el puente desde Posadas; Asunción a 4h de Formosa. Misma cultura WhatsApp, cero competencia local de chatbot inmobiliario.
- Uruguay: mercado chico pero formal, dolarizado y de alto ticket inmobiliario.
- Permiten aprender internacionalización (moneda, pagos, soporte) con bajo riesgo. Sirena hizo exactamente esto: dominó Argentina → países vecinos → LATAM antes de la adquisición.

**Tácticas:**
- Pagos internacionales: dLocal/Stripe/transferencia USD (MP no cubre PY/UY igual de bien). Pricing en USD para fuera de Argentina (USD 35/75/desde 150 — mapea el pricing ARS).
- Repetir el playbook beachhead: venta presencial en Encarnación/Asunción (viajes desde Posadas), referidos, colegios/cámaras inmobiliarias locales.
- En Argentina: la máquina sigue (ads + comisionista + referidos compuestos: con 100+ clientes, los referidos solos generan 3-5 altas/mes).
- Evaluar segundo hire: soporte/onboarding (libera al socio técnico).

**Resultado esperado:** 130-170 clientes (10-15 fuera de ARG) · MRR ~$10-12M ARS (~USD 8.500-10.000) · **ARR ~USD 110-120k, 100% bootstrap**

---

### ETAPA 5 — LATAM real (Año 3+) · México, Colombia, Chile, Perú

Solo se abre si la Etapa 4 valida venta y soporte fuera de Argentina. El orden lógico por tamaño de mercado inmobiliario + adopción WhatsApp: **México → Colombia → Chile/Perú**.

- **México es el premio mayor**: mercado inmobiliario formalizado, WhatsApp dominante, y EasyBroker (CRM inmobiliario local) probó que las inmobiliarias mexicanas pagan SaaS — pero nadie domina el nicho "bot que vende por WhatsApp + gestión de alquileres".
- Canal de entrada de bajo costo: **partners/agencias de marketing inmobiliario locales** con revenue share (así escaló WATI globalmente sin fuerza de ventas propia en cada país).
- Referencias de techo alcanzable bootstrap: Cliengo llegó a USD 7M ARR y 10.000 clientes en 22 países sin inversores en ~9 años. Con 300-1.000 clientes LATAM (USD 25-80k MRR) el negocio es una empresa de 5-15 personas muy rentable.
- Decisión consciente en este punto (no antes): seguir bootstrap o levantar capital para acelerar México. Con USD 100k+ ARR creciendo, la opción existe — pero es una opción, no una necesidad.

---

## 5. Modelo Financiero — 24 Meses

**Supuestos:** churn 5%/mes · ARPU etapa 0-1: ~$48k ARS (mix con Precio Fundador) · ARPU etapa 2+: ~$65-72k ARS (mix 50% Básico / 40% Pro / 10% Ent, precios plenos y suba mes 12) · costo variable (bot + MP) ≈ 30-40% del MRR en el peor caso, ~25% típico · servidor <USD 40/mes.

| Mes | Altas | Clientes | MRR (ARS) | MRR (USD) | Reinversión ads | Margen disponible* |
|:---:|:---:|:---:|---:|---:|---:|---:|
| 1 | 4 | 4 | $175k | $145 | $0 | ~$120k |
| 2 | 3 | 7 | $310k | $260 | $0 | ~$220k |
| 3 | 4 | 11 | $500k | $420 | $100k | ~$250k |
| 4 | 4 | 14 | $660k | $550 | $150k | ~$330k |
| 6 | 5 | 23 | $1,3M | $1.080 | $400k | ~$550k |
| 9 | 7 | 41 | $2,7M | $2.250 | $900k | ~$1,1M |
| 12 | 8 | 60 | $4,2M | $3.500 | $1,3M | ~$1,8M |
| 15 | 10 | 85 | $6,1M | $5.100 | $1,8M | ~$2,7M |
| 18 | 11 | 110 | $7,9M | $6.600 | $2,4M | ~$3,5M |
| 21 | 12 | 135 | $9,7M | $8.100 | $2,9M | ~$4,4M |
| 24 | 12 | 158 | $11,4M | $9.500 | $3,4M | ~$5,1M |

\* Margen disponible = MRR − costo bot/MP típico − reinversión. De ahí salen sueldos. Hitos de vida: **mes ~6-7** cubre un sueldo modesto; **mes ~10-12** dos sueldos dignos para Misiones; **mes 24** ≈ USD 4.200/mes de margen tras reinvertir USD 2.800/mes en crecimiento.

**Sensibilidad (honestidad bootstrap):**
| Escenario | Clientes mes 12 | Clientes mes 24 | MRR mes 24 (USD) |
|---|:---:|:---:|:---:|
| Pesimista (cierre 10%, churn 7%) | 35 | 85 | ~$5.000 |
| **Base (este plan)** | **60** | **158** | **~$9.500** |
| Optimista (referidos compuestos, churn 4%) | 80 | 220 | ~$14.000 |

Incluso el pesimista paga los costos y un sueldo — esa es la virtud del margen 60%+: el riesgo del plan es de crecimiento, no de supervivencia.

---

## 6. Métricas que Gobiernan el Plan (revisar mensualmente)

| Métrica | Sano | Alarma |
|---|---|---|
| Demos → trial | >40% | <25% → pitch roto |
| Trial → pago | >35% | <20% → activación/onboarding roto |
| Churn mensual | <5% | >8% → STOP crecimiento, arreglar retención |
| CAC payback | <2 meses ARPU | >4 meses → apagar ese canal |
| % altas por referido (desde mes 6) | >25% | <10% → producto no genera boca a boca |
| NRR (con upgrades + packs conversación) | >100% | <90% |

**Regla de oro bootstrap (la que salvó a todos los comparables):** nunca escalar adquisición con churn roto. Crecer con un balde agujereado es la causa #1 de muerte de SaaS SMB.

---

## 7. Riesgos Principales y Mitigación

1. **Dependencia de WhatsApp/Meta** (cambios de pricing por mensaje o políticas) → mantener costo por conversación monitoreado por tenant (ya existe infra de límites); el cupo por plan absorbe shocks.
2. **Tokko/Mapaprop agregan bot IA** → nuestra ventaja es foco y velocidad: bot que VENDE + cobranzas + soporte fundador. Profundizar el moat de datos conversacionales del nicho.
3. **Inflación/TC** → precios ARS con revisión trimestral (ya definido en pricing v3); contratos anuales prepagos como cobertura.
4. **El socio vendedor se quema** (riesgo real con venta puerta a puerta) → el gate de la Etapa 2 existe justamente para pasar a venta remota apenas haya casos de éxito.
5. **Churn del interior** (estacionalidad inmobiliaria) → Cobranzas es el ancla anti-churn: una inmobiliaria que gestiona sus alquileres en la plataforma no se va aunque las ventas estén frías.

---

## 8. Checklist de Arranque (próximos 14 días)

- [ ] Congelar pricing v3 en la landing + checkout MP de los 3 planes
- [ ] Definir los 15 cupos de Precio Fundador y el contrato/acuerdo de testimonio
- [ ] Armar la lista de 60 inmobiliarias de Oberá/Posadas con dueño + WhatsApp
- [ ] Guionar la demo de 10 minutos (con propiedad real precargada) y practicarla 5 veces
- [ ] Documento de caso de éxito (template listo para llenar con el cliente 1)
- [ ] Dashboard interno de métricas GTM: demos, trials, pagos, churn (puede ser una planilla)
- [ ] Primera semana de calle: 15 visitas agendadas

---

*Fuentes de los comparables: Zenvia adquiere Sirena — PRNewswire/LatamList (jul 2020, ~700 clientes en 30+ países, USD 2,8M levantados 2018); Tokko Broker — tokkobroker.com / Reporte Inmobiliario (1.800 usuarios en <2 años, 4.200+ actuales, adquirida por Navent); Cliengo — GetLatka/iProUP (bootstrap, USD 7M revenue 2024, 10.000+ empresas en 22 países); WATI — Crunchbase/GetLatka (miles de clientes en 54 países en el año 1, USD 9,6M 2024); ConvertKit — números públicos de Nathan Barry; Mapaprop/Adinco — páginas de precios (jun 2026). Mercado: reporte_inmobiliarias_argentina.md, argentina_digital_maturity_research.md, nea-argentina-economy-research.md.*

# Dashboard Inicio (Home) — Recomendación de Contenido

## Resumen Ejecutivo

Se analizó el código fuente del dashboard y backend de InmuebleBot para
recomendar los items de información que debe mostrar la pantalla principal
"Inicio" del panel de administración de la inmobiliaria.

---

## 1. Estado Actual de la Pantalla Inicio (Dashboard.jsx)

La pantalla actual ya está bastante completa pero tiene espacio para mejorar.
Actualmente muestra:

**Header:**
- Título "Panel de control"
- Fecha actual + cantidad de eventos del día

**KPI Cards (fila superior, 4 columnas):**
1. Visitas hoy — eventos tipo 'visit' del día actual
2. Propiedades disponibles — propiedades con status 'available'
3. Leads activos — clientes con status distinto de 'lost'
4. Próximas citas (7 días) — eventos en los próximos 7 días

**Columna izquierda:**
- Agenda de hoy — tabla completa con hora, cliente, propiedad, agente, estado
- Actividad reciente — feed combinado de últimos 6 eventos (nuevos leads,
  propiedades publicadas, citas creadas)

**Columna derecha:**
- Próximas citas — lista de las próximas 5
- Embudo de leads — barra de progreso: Todos → Calificados → Visita → Contrato
- Leads recientes — últimos 4 clientes con inicial, nombre, teléfono

---

## 2. Datos Disponibles NO Utilizados en Inicio

Actual | Endpoint                    | Campo no usado         | ¿Por qué importa?
-------|-----------------------------|------------------------|-------------------
Leads  | GET /admin/leads            | `lead_score` (0–100)   | Calidad del lead
Leads  | GET /admin/leads            | `last_interaction`     | Tiempo sin contacto
Leads  | GET /admin/leads            | `budget_min/max`       | Potencial de compra
Leads  | GET /admin/leads            | `location_preferences` | Zonas de interés
Leads  | GET /admin/leads            | `property_type`        | Tipo de propiedad buscado
Conv.  | GET /admin/conversations    | `state`                | Estado del flujo
Conv.  | GET /admin/conversations    | `bot_paused` (por conv)| Handoff manual
Conv.  | GET /admin/conversations    | `turn_count`           | Profundidad de la conversación
Notif. | GET /admin/notifications    | `unread_count`         | Alertas pendientes
Notif. | GET /admin/notifications    | `type` (new_lead, etc)| Tipo de alerta
Config | GET /admin/settings         | bot_paused global      | Bot status
Config | GET /admin/settings         | business_hours         | Horario de atención
Cal    | GET /admin/calendar/status  | `configured`           | Integración Google Calendar
Props  | GET /admin/properties       | `category`             | Tipo de propiedad (casa/depto)
Props  | GET /admin/properties       | `type` (venta/alquiler)| Operación
Props  | GET /admin/properties       | `created_at`           | Tiempo en cartera

---

## 3. Items Recomendados (ordenados por importancia)

### PRIORIDAD ALTA — Deben estar sí o sí

#### 1. Leads nuevos (hoy / esta semana)
- **Datos**: cantidad de clientes con `created_at` = hoy (o últimos 7 días)
- **API**: GET /admin/leads → filtrar por `created_at`
- **Por qué**: El KPI más relevante para una inmobiliaria. Muestra cuántos
  potenciales clientes están llegando. Reemplaza o complementa "Leads activos".
- **Visual**: Tarjeta KPI con número grande + delta (vs. ayer / semana pasada)
- **Ubicación**: Primera posición de la fila de KPIs

#### 2. Conversaciones activas / sin respuesta
- **Datos**: cantidad de conversaciones con `state` != 'closed' y mensaje del
  usuario sin respuesta del admin (último mensaje del usuario y no del bot/admin)
- **API**: GET /admin/conversations → analizar `state` y `last_message_at`
- **Por qué**: El admin necesita saber si hay leads esperando respuesta humana.
  Es el corazón del negocio — leads que esperan se enfrían.
- **Visual**: Tarjeta KPI destacada (color warning si > 0)
- **Ubicación**: Segunda posición de la fila de KPIs

#### 3. Citas de hoy
- **Datos**: cantidad de eventos con `date === today` y `status !== 'cancelled'`
- **API**: GET /admin/appointments → filtrar por fecha
- **Por qué**: El admin llega y lo primero que necesita saber es qué visitas
  tiene programadas hoy. Ya existe pero puede mejorar.
- **Visual**: Tarjeta KPI con indicador de tipo (visitas vs llamadas)
- **Ubicación**: Tercera posición de la fila de KPIs
- **Nota**: Ya existe como "Visitas hoy" pero solo cuenta tipo 'visit'

#### 4. Estado del Bot
- **Datos**: si el bot está activo/pausado globalmente (desde /admin/settings)
- **API**: GET /admin/settings → buscar clave 'bot_paused' o similar
- **Por qué**: El admin necesita saber de un vistazo si el bot está atendiendo
  leads automáticamente. Si está caído, los leads no reciben respuesta.
- **Visual**: Badge grande verde "Activo" / rojo "Pausado" / gris "Desconectado"
  con toggle button para pausar/reanudar
- **Ubicación**: Esquina superior derecha del header, junto al botón "Agendar visita"

#### 5. Leads del embudo — etapa Calificados vs Conversión
- **Datos**: conteo de leads por status (new → contacted → qualified → converted → lost)
- **API**: GET /admin/leads → agrupar por `status` o `role`
- **Por qué**: Muestra la salud del proceso comercial. Si hay muchos leads pero
  pocos calificados, algo anda mal en la calificación.
- **Visual**: Embudo con barras proporcionales (ya existe). Agregar tasa de
  conversión general (% leads que llegaron a "converted").
- **Ubicación**: Columna derecha (ya existe), agregar tasa de conversión

### PRIORIDAD MEDIA

#### 6. Notificaciones no leídas
- **Datos**: cantidad de notificaciones con `read === false`
- **API**: GET /admin/notifications?unread=true → `unread_count`
- **Por qué**: El badge en la campana es pequeño. Tener un contador visible en
  el dashboard recuerda al admin revisar alertas importantes (handoff solicitado,
  lead calificado, error del bot).
- **Visual**: Chip/Badge numerado junto al header o en un KPI pequeño
- **Ubicación**: Header, al lado del estado del bot

#### 7. Propiedades más consultadas / con más interés
- **Datos**: propiedades relacionadas con más clientes (via `property_relations`)
  o con más conversaciones que las mencionaron
- **API**: GET /admin/properties → analizar `buyer_id`, `tenant_id` o relaciones
- **Por qué**: Ayuda al admin a saber qué propiedades están teniendo más
  tracción y merecen más atención o fotos.
- **Visual**: Mini ranking (top 3-5) con nombre y cantidad de interesados
- **Ubicación**: Columna izquierda, debajo de la agenda de hoy

#### 8. Próximas citas (7 días)
- **Datos**: eventos desde mañana hasta 7 días, no cancelados
- **API**: GET /admin/appointments → filtrar por rango de fechas
- **Por qué**: El admin planifica su semana. Ya existe pero se puede integrar
  mejor con indicador visual de carga (ej: "3 visitas mañana").
- **Visual**: Lista compacta (ya existe como "Próximas citas")
- **Ubicación**: Columna derecha (ya existe)

#### 9. Última actividad / feed de tiempo real
- **Datos**: mezcla de nuevos leads, citas creadas, propiedades publicadas y
  mensajes de WhatsApp entrantes
- **API**: Combinar GET /admin/leads, GET /admin/appointments, GET /admin/properties
- **Por qué**: El admin necesita saber qué está pasando ahora. El feed actual
  funciona bien pero puede incluir también cambios de estado de leads.
- **Visual**: Feed vertical con iconos por tipo y timestamp relativo (ya existe)
- **Ubicación**: Columna izquierda (ya existe), agregar cambios de estado

### PRIORIDAD BAJA

#### 10. Distribución de propiedades (venta vs alquiler / por barrio)
- **Datos**: propiedades agrupadas por `type` (venta/alquiler) y por barrio
- **API**: GET /admin/properties → agrupar por `type` y `neigh`
- **Por qué**: Da contexto sobre el portfolio. Útil para decisiones de marketing.
- **Visual**: Mini gráfico de torta o anillo
- **Ubicación**: Debajo del embudo de leads o en un panel expandible

---

## 4. Layout Sugerido

```
┌──────────────────────────────────────────────────────┐
│  Panel de control                   [● Bot Activo]   │
│  lunes, 1 de junio · 2 eventos hoy  [+Agendar cita] │
├──────────────────────────────────────────────────────┤
│ ┌────────┐ ┌─────────────┐ ┌─────────┐ ┌──────────┐ │
│ │Nuevos  │ │Conversac.   │ │Citas    │ │Notif.    │ │
│ │leads   │ │activas      │ │hoy      │ │no leídas │ │
│ │  5  ▲  │ │  3  ⚠️      │ │  2      │ │  7       │ │
│ │ vs 2 ayer│             │ │         │ │          │ │
│ └────────┘ └─────────────┘ └─────────┘ └──────────┘ │
├──────────────────────┬───────────────────────────────┤
│  Columna IZQUIERDA   │  Columna DERECHA              │
│  (1.6fr)             │  (1fr)                        │
│                      │                               │
│  ┌──────────────────┐│  ┌───────────────────────────┐│
│  │ Agenda de HOY    ││  │ Próximas citas (7 días)   ││
│  │ Hora  Cliente    ││  │ ● Lun 5 jun · 10am        ││
│  │ 10am  Pérez      ││  │   Martín López            ││
│  │ 4pm   Gómez      ││  │ ● Mié 7 jun · 3pm        ││
│  └──────────────────┘│  │   Ana García              ││
│                      │  └───────────────────────────┘│
│  ┌──────────────────┐│                               │
│  │ Prop. más vistas ││  ┌───────────────────────────┐│
│  │ 1. Dto Centro (3)││  │ Embudo de leads           ││
│  │ 2. Casa Villa (2)││  │ ████████░░ 100% (20)     ││
│  │ 3. PH Norte  (1) ││  │ ████░░░░░░  45% (9)      ││
│  └──────────────────┘│  │ ██░░░░░░░░  20% (4)      ││
│                      │  │ █░░░░░░░░░  10% (2)       ││
│  ┌──────────────────┐│  │ Tasa conv: 10%            ││
│  │ Actividad reciente││  └───────────────────────────┘│
│  │ 👤 Nuevo lead     ││                               │
│  │ 🏠 Prop. publicada││  ┌───────────────────────────┐│
│  │ 📅 Visita agendada││  │ Leads recientes           ││
│  └──────────────────┘│  │ A  Ana Pérez              ││
│                      │  │ B  Bienes Raíces          ││
└──────────────────────┴───────────────────────────────┘
```

### Comportamiento responsive (móvil)

- **≤ 768px**: KPIs pasan a 2×2 grid (en lugar de 4 columnas)
- **≤ 480px**: KPIs pasan a 1 columna apilada
- **≤ 768px**: Dashboard grid pasa de 2 columnas a 1 columna
- La tabla "Agenda de hoy" oculta columnas "Agente" y acciones en móvil
  (ya implementado con clase `col-desktop`)
- Botón "Agendar visita" se mueve abajo del header en mobile
- El feed de actividad reciente se acorta a 4 items en móvil

---

## 5. APIs Nuevas Recomendadas (Backend)

Para obtener algunos indicadores sin sobrecargar al frontend con datos
innecesarios, se recomienda agregar estos endpoints:

### GET /admin/dashboard/summary
Endpoint unificado que devuelve todos los KPIs de un solo request:

```json
{
  "new_leads_today": 5,
  "new_leads_week": 23,
  "new_leads_delta_vs_yesterday": 3,
  "active_conversations": 3,
  "pending_admin_replies": 1,
  "today_appointments": 2,
  "today_visits": 1,
  "today_calls": 1,
  "week_appointments": 8,
  "available_properties": 15,
  "total_properties": 22,
  "active_leads": 28,
  "total_leads": 40,
  "leads_by_status": {
    "new": 10,
    "contacted": 8,
    "qualified": 6,
    "converted": 4,
    "lost": 12
  },
  "conversion_rate": 10.0,
  "unread_notifications": 7,
  "bot_status": "active",
  "most_viewed_properties": [
    {"id": 5, "title": "Departamento Centro", "interest_count": 3},
    {"id": 12, "title": "Casa Villa", "interest_count": 2}
  ]
}
```

### GET /admin/dashboard/recent-activity
Feed de actividad reciente combinado (últimos 10 eventos):

```json
{
  "items": [
    {
      "type": "new_lead",
      "text": "Nuevo lead · Juan Pérez",
      "icon": "users",
      "color": "var(--info-500)",
      "timestamp": "2026-06-01T10:30:00"
    },
    {
      "type": "appointment_created",
      "text": "Visita agendada · 2026-06-02 a las 10:00am",
      "icon": "calendar",
      "color": "var(--accent-500)",
      "timestamp": "2026-06-01T09:15:00"
    }
  ]
}
```

---

## 6. Resumen de Cambios al Código Existente

### Dashboard.jsx — Cambios mínimos sugeridos

1. **Header**: Agregar indicador de estado del bot (verde/rojo) junto al título
2. **KPIs**: Cambiar orden a: (1) Nuevos leads hoy, (2) Conversaciones activas,
   (3) Citas hoy, (4) Notificaciones no leídas
3. **Agenda de hoy**: Agregar diferenciación visual entre visitas y llamadas
4. **Embudo de leads**: Agregar tasa de conversión porcentual
5. **Prop. más vistas**: Nuevo widget entre agenda y actividad reciente
6. **Actividad reciente**: Incluir cambios de estado de leads (no solo creación)
7. **Notificaciones no leídas**: Mostrar contador en el dashboard (no solo en
   la campana de la topbar)

### Nuevos componentes a crear

1. `BotStatusBadge` — Indicador de estado del bot con toggle
2. `PropertyRanking` — Top propiedades más consultadas
3. `ConversionRate` — Tasa de conversión sobre el embudo

---

## 7. Conclusión

La pantalla Inicio actual es funcional pero puede mejorarse significativamente
agregando datos que ya existen en el backend pero no se están mostrando:

1. **Nuevos leads (hoy/semana)** — el KPI más importante para una inmobiliaria
2. **Conversaciones activas/pendientes** — corazón del negocio, leads esperando
3. **Estado del bot** — el admin necesita saber si el bot está operativo
4. **Propiedades con más interés** — ayuda a priorizar esfuerzos
5. **Notificaciones no leídas** visibles en el dashboard
6. **Tasa de conversión** sobre el embudo de leads

Se recomienda crear un endpoint `/admin/dashboard/summary` para servir todos
los KPIs en un solo request, optimizando la carga inicial del dashboard.

Para implementación inmediata SIN cambios en backend, se pueden derivar todos
los KPI desde los endpoints existentes (`/admin/leads`, `/admin/properties`,
`/admin/appointments`, `/admin/conversations`, `/admin/notifications`,
`/admin/settings`) con cálculos en el frontend usando `useMemo`.

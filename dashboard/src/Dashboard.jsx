import React, { useMemo } from 'react';
import { Icon, Button, IconButton, Pill } from './Primitives';
import { fmtTime12 } from './data';
import { useEvents, useProperties, useClients, useNotifications, useConversations, timeAgo, toDateStr } from './api';
import { KIND_META } from './EventPopover';
import BotStatusBadge from './BotStatusBadge';
import PropertyRanking from './PropertyRanking';
import ConversionRate from './ConversionRate';

// Estados de conversación que NO cuentan como "activa".
const CLOSED_CONV_STATES = new Set(['closed', 'cerrada', 'completed', 'done', 'finished']);

function KpiCard({ label, value, delta, trend, accent, primary, tone }) {
  const valueColor = accent ? 'var(--accent-500)'
    : tone === 'warning' ? 'var(--state-warning-fg)'
    : tone === 'danger'  ? 'var(--state-danger-fg)'
    : tone === 'success' ? 'var(--state-success-fg)'
    : undefined;
  return (
    <div className={`kpi${primary ? ' kpi-primary' : ''}`}>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value" style={valueColor ? { color: valueColor } : null}>{value}</span>
      {delta && (
        <span className={`kpi-delta ${trend || ''}`}>
          {trend === 'up' && <Icon name="arrowUp" size={12} />}
          {trend === 'down' && <Icon name="arrowDown" size={12} />}
          {delta}
        </span>
      )}
    </div>
  );
}

// ─── Actividad reciente derivada de datos reales ───────────────────────────────

function buildActivityFeed(events, clients, properties) {
  const items = [];

  // Nuevos clientes (leads) creados
  clients.forEach(c => {
    if (c._createdAt) {
      items.push({
        key: `client-${c.id}`,
        icon: 'users',
        color: 'var(--info-500)',
        text: <><b>Nuevo lead</b> · {c.name}{c.notes ? ` — ${c.notes.slice(0, 40)}` : ''}</>,
        ts: c._createdAt,
      });
    }
  });

  // Propiedades publicadas / actualizadas
  properties.forEach(p => {
    if (p._createdAt) {
      items.push({
        key: `prop-${p.id}`,
        icon: 'building',
        color: 'var(--purple-500)',
        text: <><b>Propiedad publicada</b> · {p.addr}{p.neigh ? `, ${p.neigh}` : ''}</>,
        ts: p._createdAt,
      });
    }
  });

  // Citas agendadas
  events.forEach(e => {
    if (e._createdAt) {
      const kindLabel = e.kind === 'visit' ? 'Visita agendada' : e.kind === 'call' ? 'Llamada agendada' : 'Evento agendado';
      const kindColor = e.kind === 'call' ? 'var(--warning-500)' : 'var(--accent-500)';
      items.push({
        key: `evt-${e.id}`,
        icon: 'calendar',
        color: kindColor,
        text: <><b>{kindLabel}</b> · {e.date ? `${e.date}${e.start ? ` a las ${fmtTime12(e.start)}` : ''}` : '—'}</>,
        ts: e._createdAt,
      });
    }
  });

  // Ordenar por fecha desc, tomar los 6 más recientes
  return items
    .filter(i => i.ts)
    .sort((a, b) => new Date(b.ts) - new Date(a.ts))
    .slice(0, 6);
}

// ─── Embudo de leads desde status real ────────────────────────────────────────

function buildFunnel(clients) {
  const total = clients.length;
  if (total === 0) return [];
  const counts = { new: 0, contacted: 0, qualified: 0, converted: 0, lost: 0 };
  clients.forEach(c => {
    const s = c._rawStatus ?? 'new';
    if (counts[s] !== undefined) counts[s]++;
  });
  const topOfFunnel = total;
  const withVisit   = counts.qualified + counts.converted;
  const converted   = counts.converted;
  const stages = [
    { stage: 'Todos los contactos', count: topOfFunnel },
    { stage: 'Calificados',         count: counts.qualified + counts.contacted + counts.converted },
    { stage: 'Con visita / oferta', count: withVisit },
    { stage: 'Contrato firmado',    count: converted },
  ];
  return stages.map(s => ({ ...s, pct: topOfFunnel > 0 ? Math.round((s.count / topOfFunnel) * 100) : 0 }));
}

// ─── Componente principal ──────────────────────────────────────────────────────

export default function Dashboard({ onNav, onOpenEvent, onOpenClient }) {
  const { data: events = [] }     = useEvents();
  const { data: properties = [] } = useProperties();
  const { data: clients = [] }    = useClients();
  // Endpoints existentes reusados vía TanStack Query (deduplicados con Topbar / Chats):
  const { data: notifData }       = useNotifications();
  const { data: convData }        = useConversations();

  const conversations = convData?.conversations ?? [];
  const unreadNotifs  = notifData?.unread_count ?? 0;

  // Lookups O(1) memoizados (evitan scans lineales por fila).
  const clientMap   = useMemo(() => new Map(clients.map(c => [c.id, c])), [clients]);
  const propertyMap = useMemo(() => new Map(properties.map(p => [String(p.id), p])), [properties]);
  const findClient   = (id) => clientMap.get(id);
  const findProperty = (id) => propertyMap.get(String(id));

  // Fechas en zona horaria de Argentina, consistentes con e.date y _createdAt (api.js → toDateStr).
  const today = toDateStr(new Date().toISOString());
  const yesterday = toDateStr(new Date(Date.now() - 86_400_000).toISOString());

  const todayEvents = useMemo(() =>
    events
      .filter(e => e.date === today && e.status !== 'cancelled')
      .sort((a, b) => a.start.localeCompare(b.start)),
    [events, today]
  );

  const upcomingEvents = useMemo(() =>
    events
      .filter(e => e.date >= today && e.status !== 'cancelled')
      .sort((a, b) => a.date.localeCompare(b.date) || a.start.localeCompare(b.start))
      .slice(0, 5),
    [events, today]
  );

  // ── KPIs derivados de datos existentes ──────────────────────────────────────
  const newLeads = useMemo(() => {
    let t = 0, y = 0;
    clients.forEach(c => {
      if (!c._createdAt) return;
      const d = toDateStr(c._createdAt);
      if (d === today) t++;
      else if (d === yesterday) y++;
    });
    return { today: t, yesterday: y, delta: t - y };
  }, [clients, today, yesterday]);

  const convStats = useMemo(() => {
    const active  = conversations.filter(c => !CLOSED_CONV_STATES.has((c.state ?? '').toLowerCase()));
    const waiting = conversations.filter(c => c.bot_paused);   // handoff a humano = espera respuesta
    return { active: active.length, waiting: waiting.length };
  }, [conversations]);

  const todayAppts = useMemo(() => ({
    total:  todayEvents.length,
    visits: todayEvents.filter(e => e.kind === 'visit').length,
    calls:  todayEvents.filter(e => e.kind === 'call').length,
  }), [todayEvents]);

  const convertedCount = useMemo(() => clients.filter(c => c._rawStatus === 'converted').length, [clients]);

  const activityFeed = useMemo(() => buildActivityFeed(events, clients, properties), [events, clients, properties]);
  const funnel       = useMemo(() => buildFunnel(clients), [clients]);

  const leadsDeltaText = newLeads.delta === 0
    ? 'igual que ayer'
    : `${Math.abs(newLeads.delta)} ${newLeads.delta > 0 ? 'más' : 'menos'} que ayer`;
  const leadsTrend = newLeads.delta > 0 ? 'up' : newLeads.delta < 0 ? 'down' : undefined;
  const apptDelta = todayAppts.total === 0
    ? 'sin citas hoy'
    : `${todayAppts.visits} visita${todayAppts.visits !== 1 ? 's' : ''} · ${todayAppts.calls} llamada${todayAppts.calls !== 1 ? 's' : ''}`;

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Panel de control</h1>
          <div className="sub">{new Date().toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })} · {todayEvents.length} evento{todayEvents.length !== 1 ? 's' : ''} en la agenda de hoy</div>
        </div>
        <div className="page-h-actions">
          <BotStatusBadge />
          <Button kind="primary" icon="plus" onClick={() => onNav('calendar')}>Agendar visita</Button>
        </div>
      </div>

      <div className="page-kpis">
        <div className="kpi-grid">
          <KpiCard
            primary
            label="Nuevos leads hoy"
            value={newLeads.today}
            delta={leadsDeltaText}
            trend={leadsTrend}
          />
          <KpiCard
            label="Conversaciones activas"
            value={convStats.active}
            tone={convStats.waiting > 0 ? 'warning' : undefined}
            delta={convStats.waiting > 0
              ? `${convStats.waiting} requiere${convStats.waiting !== 1 ? 'n' : ''} atención`
              : 'todas atendidas'}
          />
          <KpiCard
            label="Citas hoy"
            value={todayAppts.total}
            delta={apptDelta}
          />
          <KpiCard
            label="Notificaciones sin leer"
            value={unreadNotifs}
            tone={unreadNotifs > 0 ? 'warning' : undefined}
            delta={unreadNotifs > 0 ? 'revisar alertas' : 'al día'}
          />
        </div>
      </div>

      <div className="page-body">
        {convStats.waiting > 0 && (
          <button
            type="button"
            className="attention-banner"
            aria-label={`${convStats.waiting} conversación${convStats.waiting !== 1 ? 'es' : ''} esperando respuesta humana. Abrir chats.`}
            onClick={() => onNav('chats')}
          >
            <span className="attention-icon"><Icon name="headset" size={16} /></span>
            <span className="attention-text">
              <b>{convStats.waiting} conversación{convStats.waiting !== 1 ? 'es' : ''}</b> con atención humana activa esperando respuesta.
            </span>
            <span className="attention-cta">Abrir chats →</span>
          </button>
        )}

        <div className="dashboard-grid">

          {/* ── Columna izquierda ── */}
          <div>
            <div className="section-h" style={{ margin: '0 0 12px' }}>
              <h2>Agenda de hoy</h2>
              <span className="count">{todayEvents.length} eventos</span>
              <div className="actions">
                <Button kind="ghost" size="sm" onClick={() => onNav('calendar')}>Ver calendario →</Button>
              </div>
            </div>
            <div className="surface">
              <table className="tbl agenda-tbl">
                <thead><tr>
                  <th>Hora</th><th>Cliente</th><th>Propiedad</th><th className="col-desktop">Agente</th><th>Estado</th><th className="col-desktop"></th>
                </tr></thead>
                <tbody>
                  {todayEvents.map(e => {
                    const c    = findClient(e.clientId);
                    const p    = findProperty(e.propId);
                    const meta = KIND_META[e.kind] ?? KIND_META['visit'];
                    return (
                      <tr key={e.id}
                          tabIndex={0}
                          aria-label={`Ver cita con ${c ? c.name : 'cliente'} a las ${fmtTime12(e.start)}`}
                          onClick={(ev) => onOpenEvent(e, ev.currentTarget.getBoundingClientRect())}
                          onKeyDown={(ev) => { if (ev.target === ev.currentTarget && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); onOpenEvent(e, ev.currentTarget.getBoundingClientRect()); } }}>
                        <td className="tabular" style={{ whiteSpace: 'nowrap' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ width: 6, height: 6, borderRadius: '50%', background: meta.color }}></span>
                            {fmtTime12(e.start)}
                          </span>
                        </td>
                        <td>{c ? c.name : <span className="muted">—</span>}</td>
                        <td className="muted">{p ? p.addr : (e.title ?? '—').replace(/^[^·]+·\s*/, '')}</td>
                        <td className="muted col-desktop">{e.agent}</td>
                        <td>{e.status === 'confirmed'
                          ? <Pill kind="paid">Conf.</Pill>
                          : <Pill kind="pending">Pend.</Pill>}
                        </td>
                        <td className="col-desktop"><div className="row-actions"><IconButton name="phone" aria-label="Llamar" /><IconButton name="more" aria-label="Más acciones" /></div></td>
                      </tr>
                    );
                  })}
                  {todayEvents.length === 0 && (
                    <tr><td colSpan="6" className="tbl-empty">Sin eventos para hoy.</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="section-h">
              <h2>Propiedades con más interés</h2>
              <div className="actions">
                <Button kind="ghost" size="sm" onClick={() => onNav('properties')}>Ver todas →</Button>
              </div>
            </div>
            <div className="surface">
              <PropertyRanking properties={properties} clients={clients} />
            </div>

            <div className="section-h">
              <h2>Actividad reciente</h2>
            </div>
            <div className="surface activity">
              {activityFeed.length > 0
                ? activityFeed.map((item) => (
                    <div key={item.key} className="activity-row">
                      <span className="icon"><Icon name={item.icon} size={14} style={{ color: item.color }} /></span>
                      <div className="text">{item.text} <span className="when">· {timeAgo(item.ts)}</span></div>
                    </div>
                  ))
                : (
                    <div className="activity-row">
                      <span className="icon"><Icon name="calendar" size={14} style={{ color: 'var(--fg-tertiary)' }} /></span>
                      <div className="text" style={{ color: 'var(--fg-tertiary)' }}>Sin actividad reciente. Cargá propiedades, leads o citas para ver el historial aquí.</div>
                    </div>
                  )
              }
            </div>
          </div>

          {/* ── Columna derecha ── */}
          <div>
            <div className="section-h" style={{ margin: '0 0 12px' }}>
              <h2>Próximas citas</h2>
              <div className="actions">
                <Button kind="ghost" size="sm" onClick={() => onNav('calendar')}>Ver todas →</Button>
              </div>
            </div>
            <div className="surface" style={{ padding: '4px 0' }}>
              {upcomingEvents.length > 0
                ? upcomingEvents.map((e, i) => {
                    const c    = findClient(e.clientId);
                    const p    = findProperty(e.propId);
                    const meta = KIND_META[e.kind] ?? KIND_META['visit'];
                    return (
                      <button
                        type="button"
                        key={e.id}
                        aria-label={`Ver cita: ${c ? c.name : 'sin cliente'}, ${e.date}${e.start ? ` a las ${fmtTime12(e.start)}` : ''}`}
                        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: i < upcomingEvents.length - 1 ? '1px solid var(--border-subtle)' : 'none', cursor: 'pointer', width: '100%', textAlign: 'left', background: 'none', borderLeft: 'none', borderRight: 'none', borderTop: 'none', font: 'inherit', color: 'inherit' }}
                        onClick={(ev) => onOpenEvent(e, ev.currentTarget.getBoundingClientRect())}
                      >
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: meta.color, flexShrink: 0 }} />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {c ? c.name : <span style={{ color: 'var(--fg-tertiary)' }}>Sin cliente</span>}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
                            {e.date}{e.start ? ` · ${fmtTime12(e.start)}` : ''}{p ? ` · ${p.addr}` : ''}
                          </div>
                        </div>
                        <Pill kind={e.status === 'confirmed' ? 'paid' : 'pending'} style={{ fontSize: 10 }}>
                          {e.status === 'confirmed' ? 'Conf.' : 'Pend.'}
                        </Pill>
                      </button>
                    );
                  })
                : (
                    <div style={{ padding: '16px', color: 'var(--fg-tertiary)', fontSize: 13, textAlign: 'center' }}>
                      No hay citas próximas.
                    </div>
                  )
              }
            </div>

            <div className="section-h">
              <h2>Embudo de leads</h2>
            </div>
            <div className="surface" style={{ padding: 14 }}>
              {funnel.length > 0
                ? funnel.map((s, i) => (
                    <div key={s.stage} style={{ marginBottom: i < funnel.length - 1 ? 10 : 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>{s.stage}</span>
                        <span style={{ fontSize: 12, fontWeight: 600 }} className="tabular">{s.count}</span>
                      </div>
                      <div style={{ height: 6, background: 'var(--gray-100)', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ width: `${s.pct}%`, height: '100%', background: 'var(--accent-500)', opacity: 0.4 + (s.pct / 200) }} />
                      </div>
                    </div>
                  ))
                : <div style={{ color: 'var(--fg-tertiary)', fontSize: 13 }}>Sin leads cargados.</div>
              }
              {clients.length > 0 && <ConversionRate converted={convertedCount} total={clients.length} />}
            </div>

            <div className="section-h">
              <h2>Leads recientes</h2>
              <div className="actions">
                <Button kind="ghost" size="sm" onClick={() => onNav('clients')}>Ver todos →</Button>
              </div>
            </div>
            <div className="surface" style={{ padding: '4px 0' }}>
              {clients
                .slice()
                .sort((a, b) => (b._createdAt ?? '').localeCompare(a._createdAt ?? ''))
                .slice(0, 4)
                .map((c, i, arr) => (
                  <button
                    type="button"
                    key={c.id}
                    aria-label={`Ver perfil de ${c.name}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: i < arr.length - 1 ? '1px solid var(--border-subtle)' : 'none', cursor: 'pointer', width: '100%', textAlign: 'left', background: 'none', borderLeft: 'none', borderRight: 'none', borderTop: 'none', font: 'inherit', color: 'inherit' }}
                    onClick={() => onOpenClient && onOpenClient(c)}
                  >
                    <span style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-100)', color: 'var(--accent-600)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, flexShrink: 0 }} aria-hidden="true">
                      {(c.name ?? '?')[0].toUpperCase()}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>{c.phone || c.email || '—'}</div>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>{c.lastContact}</div>
                  </button>
                ))
              }
              {clients.length === 0 && (
                <div style={{ padding: '16px', color: 'var(--fg-tertiary)', fontSize: 13, textAlign: 'center' }}>
                  Sin leads cargados.
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

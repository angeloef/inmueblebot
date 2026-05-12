import React, { useMemo } from 'react';
import { Icon, Button, IconButton, Pill } from './Primitives';
import { fmtTime12 } from './data';
import { useEvents, useProperties, useClients, timeAgo } from './api';
import { KIND_META } from './EventPopover';

function KpiCard({ label, value, delta, trend, accent }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value" style={accent ? { color: 'var(--accent-500)' } : null}>{value}</span>
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

  const findClient   = (id) => clients.find(c => c.id === id);
  const findProperty = (id) => properties.find(p => String(p.id) === String(id));
  const today = new Date().toISOString().slice(0, 10);

  const todayEvents = events
    .filter(e => e.date === today && e.status !== 'cancelled')
    .sort((a, b) => a.start.localeCompare(b.start));

  const upcomingEvents = useMemo(() =>
    events
      .filter(e => e.date >= today && e.status !== 'cancelled')
      .sort((a, b) => a.date.localeCompare(b.date) || a.start.localeCompare(b.start))
      .slice(0, 5),
    [events, today]
  );

  const activityFeed = useMemo(() => buildActivityFeed(events, clients, properties), [events, clients, properties]);
  const funnel       = useMemo(() => buildFunnel(clients), [clients]);

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Panel de control</h1>
          <div className="sub">{new Date().toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })} · {todayEvents.length} evento{todayEvents.length !== 1 ? 's' : ''} en la agenda de hoy</div>
        </div>
        <div className="page-h-actions">
          <Button kind="primary" icon="plus" size="sm" onClick={() => onNav('calendar')}>Agendar visita</Button>
        </div>
      </div>

      <div className="page-kpis">
        <div className="kpi-grid">
          <KpiCard
            label="Visitas hoy"
            value={todayEvents.filter(e => e.kind === 'visit').length}
            delta={`${todayEvents.length} evento${todayEvents.length !== 1 ? 's' : ''} total`}
          />
          <KpiCard
            label="Propiedades disponibles"
            value={properties.filter(p => p.status === 'available').length}
            delta={`de ${properties.length} en cartera`}
          />
          <KpiCard
            label="Leads activos"
            value={clients.filter(c => c._rawStatus !== 'lost').length}
            delta={`de ${clients.length} total`}
          />
          <KpiCard
            label="Próximas citas (7 d)"
            value={events.filter(e => {
              const d = e.date;
              const limit = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
              return d >= today && d <= limit && e.status !== 'cancelled';
            }).length}
            delta="siguiente semana"
          />
        </div>
      </div>

      <div className="page-body">
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
                      <tr key={e.id} onClick={(ev) => onOpenEvent(e, ev.currentTarget.getBoundingClientRect())}>
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
                        <td className="col-desktop"><div className="row-actions"><IconButton name="phone" /><IconButton name="more" /></div></td>
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
              <h2>Actividad reciente</h2>
            </div>
            <div className="surface activity">
              {activityFeed.length > 0
                ? activityFeed.map((item, i) => (
                    <div key={i} className="activity-row">
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
                      <div
                        key={e.id}
                        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: i < upcomingEvents.length - 1 ? '1px solid var(--border-subtle)' : 'none', cursor: 'pointer' }}
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
                      </div>
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
                    <div key={i} style={{ marginBottom: i < funnel.length - 1 ? 10 : 0 }}>
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
                  <div
                    key={c.id}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: i < arr.length - 1 ? '1px solid var(--border-subtle)' : 'none', cursor: 'pointer' }}
                    onClick={() => onOpenClient && onOpenClient(c)}
                  >
                    <span style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-100)', color: 'var(--accent-600)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
                      {(c.name ?? '?')[0].toUpperCase()}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>{c.phone || c.email || '—'}</div>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>{c.lastContact}</div>
                  </div>
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

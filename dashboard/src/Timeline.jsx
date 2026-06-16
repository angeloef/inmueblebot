import React from 'react';
import { Icon, Pill } from './Primitives';
import { fmtTime12 } from './data';
import { KIND_META } from './EventPopover';
import { formatActivity } from './activityFormat';

// Timeline unificado: combina visitas/citas (appointments) con eventos de activity_log
// (vínculos, cambios de estado, ediciones, reasignaciones) en una sola lista desc.

function statusPill(status) {
  if (status === 'cancelled') return <Pill kind="cancelled">Cancelada</Pill>;
  if (status === 'pending') return <Pill kind="pending">Por confirmar</Pill>;
  return <Pill kind="paid">Confirmada</Pill>;
}

function eventToItem(e) {
  return {
    key: `ev-${e.id}`,
    ts: `${e.date}T${e.start || '00:00'}`,
    icon: e.kind === 'visit' ? 'mapPin' : e.kind === 'call' ? 'phone' : e.kind === 'sign' ? 'contract' : 'calendar',
    color: KIND_META[e.kind]?.color || 'var(--gray-400)',
    text: (e.title || '').replace(/^[^·]+·\s*/, '') || (e.kind === 'visit' ? 'Visita' : 'Evento'),
    dateLabel: e.date,
    timeLabel: e.start ? fmtTime12(e.start) : '',
    meta: e.agent || '',
    pill: statusPill(e.status),
  };
}

function activityToItem(a) {
  const f = formatActivity(a);
  const iso = a.created_at || '';
  const time = iso.length >= 16 ? iso.slice(11, 16) : '';
  return {
    key: `ac-${a.id}`,
    ts: iso,
    icon: f.icon,
    color: f.color,
    text: f.text,
    dateLabel: iso.slice(0, 10),
    timeLabel: time ? fmtTime12(time) : '',
    meta: a.actor || '',
    pill: null,
  };
}

/**
 * @param {{ events?: Array, activity?: Array, emptyText?: string, limit?: number }} props
 */
export default function Timeline({ events = [], activity = [], emptyText = 'Sin actividad registrada.', limit }) {
  const items = [...events.map(eventToItem), ...activity.map(activityToItem)]
    .sort((x, y) => (y.ts || '').localeCompare(x.ts || ''));
  const shown = limit ? items.slice(0, limit) : items;

  if (shown.length === 0) {
    return <div className="muted" style={{ fontSize: 12 }}>{emptyText}</div>;
  }

  return (
    <>
      {shown.map(it => (
        <div key={it.key} style={{ display: 'flex', gap: 10, padding: '10px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: 13, alignItems: 'flex-start' }}>
          <span style={{ width: 24, height: 24, borderRadius: 6, background: 'var(--gray-50)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: it.color, flexShrink: 0 }}>
            <Icon name={it.icon} size={13} />
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 500 }}>{it.text}</div>
            <div style={{ fontSize: 11, color: 'var(--fg-tertiary)' }}>
              {it.dateLabel}{it.timeLabel ? ` · ${it.timeLabel}` : ''}{it.meta ? ` · ${it.meta}` : ''}
            </div>
          </div>
          {it.pill}
        </div>
      ))}
    </>
  );
}

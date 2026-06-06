import React, { useMemo } from 'react';
import { Icon } from './Primitives';

/**
 * Top propiedades por interés, derivado de las relaciones cliente↔propiedad que
 * ya vienen embebidas en /admin/leads (`property_relations`) — sin requests extra.
 *
 * Presentacional: recibe `properties` y `clients` ya cacheados por TanStack Query.
 */
export default function PropertyRanking({ properties, clients, limit = 4 }) {
  const ranking = useMemo(() => {
    const counts = new Map();
    clients.forEach(c => {
      (c.property_relations ?? []).forEach(rel => {
        const pid = String(rel.property_id ?? rel.propertyId ?? rel.id ?? '');
        if (!pid) return;
        counts.set(pid, (counts.get(pid) ?? 0) + 1);
      });
    });
    return properties
      .map(p => ({ p, count: counts.get(String(p.id)) ?? 0 }))
      .filter(x => x.count > 0)
      .sort((a, b) => b.count - a.count)
      .slice(0, limit);
  }, [properties, clients, limit]);

  if (ranking.length === 0) {
    return (
      <div className="empty-state" style={{ padding: '22px 16px' }}>
        <Icon name="building" size={22} className="empty-icon" />
        <p>Todavía no hay interés registrado en propiedades.</p>
      </div>
    );
  }

  const max = ranking[0].count || 1;

  return (
    <ol className="prop-ranking">
      {ranking.map(({ p, count }, i) => (
        <li key={p.id} className="prop-ranking-row">
          <span className="prop-ranking-rank" aria-hidden="true">{i + 1}</span>
          <div className="prop-ranking-main">
            <div className="prop-ranking-title">{p.addr || p.type || 'Propiedad'}</div>
            <div className="prop-ranking-meta">
              {[p.type, p.neigh].filter(Boolean).join(' · ') || '—'}
            </div>
            <div className="prop-ranking-bar">
              <span style={{ width: `${(count / max) * 100}%` }} />
            </div>
          </div>
          <span className="prop-ranking-count" aria-label={`${count} interesado${count !== 1 ? 's' : ''}`}>
            <Icon name="users" size={12} /> {count}
          </span>
        </li>
      ))}
    </ol>
  );
}

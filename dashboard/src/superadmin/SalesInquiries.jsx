import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { http } from '../api';

const STATUS_LABELS = { open: 'Abierta', contacted: 'Contactado', closed: 'Cerrada' };
const STATUS_COLORS = { open: '#2f8f4e', contacted: '#9a6c10', closed: '#8b929b' };

function StatusBadge({ status }) {
  return (
    <span style={{
      font: '600 11px/1 Inter,sans-serif', padding: '4px 8px', borderRadius: 9999,
      background: `${STATUS_COLORS[status] ?? '#8b929b'}22`,
      color: STATUS_COLORS[status] ?? '#8b929b',
    }}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export default function SalesInquiries() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['sales-inquiries', filter],
    queryFn: () => http.get('/sales-inquiries', { params: filter ? { status: filter } : {} }).then(r => r.data),
    staleTime: 30_000,
  });

  const patch = useMutation({
    mutationFn: ({ id, status }) => http.patch(`/sales-inquiries/${id}`, { status }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sales-inquiries'] }),
  });

  const items = data?.items ?? [];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <h2 style={{ margin: 0, font: '600 18px/1 Inter,sans-serif' }}>
          Consultas Enterprise
          {data?.open_total > 0 && (
            <span style={{ marginLeft: 10, font: '600 12px/1 Inter,sans-serif', background: '#2f8f4e22', color: '#2f8f4e', padding: '4px 9px', borderRadius: 9999 }}>
              {data.open_total} nuevas
            </span>
          )}
        </h2>
        <select value={filter} onChange={e => setFilter(e.target.value)} style={{ marginLeft: 'auto', padding: '6px 10px', borderRadius: 8, border: '1px solid var(--fg-border,#e0e0e0)', font: '400 13px/1 Inter,sans-serif', background: 'var(--surface-base,#fff)' }}>
          <option value="">Todas</option>
          <option value="open">Abiertas</option>
          <option value="contacted">Contactadas</option>
          <option value="closed">Cerradas</option>
        </select>
      </div>

      {isLoading ? (
        <p style={{ color: 'var(--fg-secondary,#666)' }}>Cargando…</p>
      ) : items.length === 0 ? (
        <p style={{ color: 'var(--fg-secondary,#666)' }}>Sin consultas.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map(item => (
            <div key={item.id} style={{ background: 'var(--surface-card,#fff)', border: '1px solid var(--fg-border,#e0e0e0)', borderRadius: 10, padding: '16px 20px' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ font: '600 14px/1.3 Inter,sans-serif', marginBottom: 4 }}>{item.contact_name}</div>
                  <div style={{ font: '400 12px/1.4 Inter,sans-serif', color: 'var(--fg-secondary,#666)' }}>
                    {item.contact_email} · {item.tenant_name ?? item.tenant_id}
                  </div>
                  {item.phone && <div style={{ font: '400 12px/1.4 Inter,sans-serif', color: 'var(--fg-secondary,#666)' }}>📞 {item.phone}</div>}
                  {item.property_count && <div style={{ font: '400 12px/1.4 Inter,sans-serif', color: 'var(--fg-secondary,#666)' }}>Propiedades: {item.property_count}</div>}
                  {item.message && <div style={{ font: '400 13px/1.5 Inter,sans-serif', marginTop: 8, padding: '8px 12px', background: 'var(--surface-base,#f6f8fa)', borderRadius: 6 }}>{item.message}</div>}
                  <div style={{ font: '400 11px/1 Inter,sans-serif', color: 'var(--fg-tertiary,#999)', marginTop: 8 }}>
                    {new Date(item.created_at).toLocaleString('es-AR')}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
                  <StatusBadge status={item.status} />
                  <select
                    value={item.status}
                    onChange={e => patch.mutate({ id: item.id, status: e.target.value })}
                    style={{ padding: '5px 8px', borderRadius: 6, border: '1px solid var(--fg-border,#e0e0e0)', font: '400 12px/1 Inter,sans-serif', cursor: 'pointer' }}
                  >
                    <option value="open">Abierta</option>
                    <option value="contacted">Contactado</option>
                    <option value="closed">Cerrada</option>
                  </select>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

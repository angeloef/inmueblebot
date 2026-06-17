import React, { useState } from 'react';
import { Button, Pill, Icon, initials, pushToast } from './Primitives';
import { fmtCurrency } from './data';
import { useClients, useProperties, useRelateClientToProperty, useTeamMembers } from './api';

// Relaciones cliente↔propiedad (compartidas entre el lado cliente y el lado propiedad).
const RELATIONS = [
  ['buyer', 'Comprador'],
  ['tenant', 'Inquilino'],
  ['interested', 'Interesado'],
];

/**
 * Flujo de vínculo cliente↔propiedad, parametrizado por "lado".
 * - side="client":   se fija `client` y se elige una propiedad.
 * - side="property": se fija `property` y se elige un cliente.
 * Reutiliza el mismo endpoint (`useRelateClientToProperty`) y el mismo patrón visual.
 *
 * @param {{
 *   side: 'client' | 'property',
 *   client?: { id: string | number },
 *   property?: { id: string | number },
 *   onDone?: () => void,
 *   defaultRelation?: 'buyer' | 'tenant' | 'interested',
 * }} props
 */
export default function LinkClientProperty({ side, client, property, onDone, defaultRelation = 'interested' }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [relation, setRelation] = useState(defaultRelation);
  const [agentId, setAgentId] = useState('');
  const relateClient = useRelateClientToProperty();

  const isClientSide = side === 'client';
  const { data: properties = [] } = useProperties();
  const { data: clients = [] } = useClients();
  const { data: members = [] } = useTeamMembers();
  // Solo miembros activos (aceptados) como agentes asignables.
  const agents = members.filter(m => (m.status ?? 'accepted') === 'accepted');

  const close = () => { setOpen(false); setSearch(''); setRelation(defaultRelation); setAgentId(''); };

  const link = (propId, clientId, label) => {
    relateClient.mutate(
      { prop_id: propId, client_id: clientId, relation, update_status: true, agent_id: agentId || null },
      {
        // Mantener el panel abierto si falla, para reintentar sin reabrirlo.
        onError:   () => pushToast({ text: 'Error al vincular. Verificá la conexión.', kind: 'danger' }),
        onSuccess: () => {
          pushToast({ text: `${label} vinculado correctamente.`, kind: 'success' });
          close();
          if (onDone) onDone();
        },
      },
    );
  };

  if (!open) {
    return (
      <Button kind="secondary" size="sm" icon={isClientSide ? 'building' : 'user-plus'} onClick={() => setOpen(true)}>
        {isClientSide ? 'Vincular propiedad' : 'Vincular cliente'}
      </Button>
    );
  }

  const q = search.toLowerCase();
  const matchedProps = properties
    .filter(p => (search ? (p.addr || '').toLowerCase().includes(q) || (p.neigh || '').toLowerCase().includes(q) : true))
    .slice(0, 8);
  const matchedClients = clients
    .filter(c => (search ? (c.name || '').toLowerCase().includes(q) : true))
    .slice(0, 8);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <input
        aria-label={isClientSide ? 'Buscar propiedad por dirección' : 'Buscar cliente por nombre'}
        placeholder={isClientSide ? 'Buscar propiedad por dirección...' : 'Buscar cliente por nombre...'}
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{ width: '100%', padding: '6px 10px', fontSize: 13, border: '1px solid var(--border-default)', borderRadius: 6 }}
        autoFocus
      />
      <div style={{ display: 'flex', gap: 6 }}>
        {RELATIONS.map(([k, l]) => (
          <button key={k} type="button" className={`chip ${relation === k ? 'active' : ''}`} aria-pressed={relation === k} onClick={() => setRelation(k)}>{l}</button>
        ))}
      </div>
      {agents.length > 0 && (
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Agente asignado</label>
          <select value={agentId} onChange={e => setAgentId(e.target.value)} aria-label="Agente asignado">
            <option value="">Sin asignar</option>
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.name || a.email}</option>
            ))}
          </select>
        </div>
      )}
      <div style={{ maxHeight: 180, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {isClientSide
          ? matchedProps.map(p => {
              const linkProp = () => link(p.id, client.id, p.addr || 'Propiedad');
              return (
                <div key={p.id} className="popover-attendee" role="button" tabIndex={0} aria-label={`Vincular ${p.addr}`}
                     style={{ cursor: 'pointer', padding: '6px 8px', borderRadius: 6 }}
                     onClick={linkProp}
                     onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); linkProp(); } }}>
                  <span className="prop-thumb" style={{ background: p.photo, width: 40, height: 32 }} aria-hidden="true"><Icon name="building" /></span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="name" style={{ fontSize: 13, fontWeight: 500 }}>{p.addr}</div>
                    <div className="meta">{p.neigh} · {fmtCurrency(p.price, p.currency)}</div>
                  </div>
                  <Pill kind={p.status} />
                </div>
              );
            })
          : matchedClients.map(c => {
              const linkC = () => link(property.id, c.id, c.name || 'Cliente');
              return (
                <div key={c.id} className="popover-attendee" role="button" tabIndex={0} aria-label={`Vincular a ${c.name}`}
                     style={{ cursor: 'pointer', padding: '6px 8px', borderRadius: 6 }}
                     onClick={linkC}
                     onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); linkC(); } }}>
                  <span className="av" aria-hidden="true">{initials(c.name)}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="name" style={{ fontSize: 13, fontWeight: 500 }}>{c.name}</div>
                    <div className="meta">{c.phone || c.email}</div>
                  </div>
                  <Pill kind={c.role} />
                </div>
              );
            })}
        {((isClientSide && matchedProps.length === 0) || (!isClientSide && matchedClients.length === 0)) && (
          <div className="muted" style={{ fontSize: 12, padding: 8 }}>Sin resultados.</div>
        )}
      </div>
      <Button kind="ghost" size="sm" onClick={close}>Cancelar</Button>
    </div>
  );
}

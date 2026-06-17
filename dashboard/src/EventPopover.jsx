import React, { useState, useEffect, useRef, Fragment } from 'react';
import { Icon, Button, IconButton, Pill, initials } from './Primitives';
import { fmtTime12 } from './data';
import { useClients, useProperties, useCalendarStatus, useTeamMembers } from './api';

export const KIND_META = {
  visit: { label: 'Visita',   color: 'var(--accent-500)',  cls: 'ev-visit' },
  call:  { label: 'Llamada',  color: 'var(--warning-500)', cls: 'ev-call'  },
};

export function EventPopover({ event, anchor, onClose, onEdit, onReschedule, onCancel, onDelete, onOpenClient, onOpenProperty }) {
  const { data: clients = [] }    = useClients();
  const { data: properties = [] } = useProperties();
  const { data: calStatus }       = useCalendarStatus();
  const { data: members = [] }    = useTeamMembers();
  if (!event) return null;
  const meta   = KIND_META[event.kind];
  const client = clients.find(c => c.id === event.clientId);
  const agentMember = members.find(m => String(m.id) === String(event.agentId));
  const agentName = agentMember ? (agentMember.name || agentMember.email) : null;
  const prop   = properties.find(p => String(p.id) === String(event.propId));

  const ref = useRef(null);
  const [pos, setPos] = useState({ left: 0, top: 0, opacity: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const w = r.width, h = r.height;
    const margin = 8;
    if (!anchor) {
      // Opened programmatically (e.g. from notification) — center on screen
      setPos({
        left: Math.max(margin, (window.innerWidth  - w) / 2),
        top:  Math.max(margin, (window.innerHeight - h) / 2),
        opacity: 1,
      });
      return;
    }
    let left = anchor.right + margin;
    let top = anchor.top;
    if (left + w > window.innerWidth - margin) left = Math.max(margin, anchor.left - w - margin);
    if (top + h > window.innerHeight - margin) top = Math.max(margin, window.innerHeight - h - margin);
    if (top < margin) top = margin;
    setPos({ left, top, opacity: 1 });
  }, [anchor]);

  const dateLabel = (() => {
    const [y,m,d] = event.date.split('-').map(Number);
    const dt = new Date(y, m-1, d);
    const dows = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
    return `${dows[dt.getDay()].replace(/^./, c=>c.toUpperCase())}, ${d} de ${['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'][m-1]}`;
  })();

  return (
    <Fragment>
      <div className="popover-shroud" onClick={onClose} />
      <div className="popover" ref={ref} style={{ left: pos.left, top: pos.top, opacity: pos.opacity }}>
        <div className="popover-head">
          <IconButton name="edit" title="Editar" onClick={() => onEdit(event)} />
          <IconButton name="trash" title="Eliminar" onClick={() => onDelete(event)} />
          <IconButton name="mail" title="Enviar correo" />
          <IconButton name="more" title="Más" />
          <span className="spacer" />
          <IconButton name="x" title="Cerrar" onClick={onClose} />
        </div>
        <div className="popover-body">
          <div className="popover-title">
            <span className="swatch" style={{ background: meta.color }} />
            <h3>{event.title}</h3>
          </div>
          <div className="popover-when">
            {dateLabel} · {fmtTime12(event.start)} – {fmtTime12(event.end)}
          </div>

          {prop && (
            <div className="popover-row">
              <Icon name="mapPin" size={16} />
              <div className="val">
                <a href="#" onClick={(e)=>{e.preventDefault(); onOpenProperty && onOpenProperty(prop);}}>{prop.addr}</a>
                <span className="sub">{prop.neigh} · {prop.type} {prop.rooms !== '—' && `· ${prop.rooms}`} · {prop.m2} m²</span>
              </div>
            </div>
          )}

          {client && (
            <div className="popover-row">
              <Icon name="users" size={16} />
              <div className="val">
                <div className="popover-attendee">
                  <span className="av">{initials(client.name)}</span>
                  <div>
                    <div className="name">
                      <a href="#" onClick={(e)=>{e.preventDefault(); onOpenClient && onOpenClient(client);}}>{client.name}</a>
                      <Pill kind={event.status === 'confirmed' ? 'paid' : event.status === 'cancelled' ? 'cancelled' : 'pending'}>{event.status === 'confirmed' ? 'Confirmado' : event.status === 'cancelled' ? 'Cancelado' : 'Por confirmar'}</Pill>
                    </div>
                    <div className="meta">{client.tags.join(' · ')}</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {client && (
            <div className="popover-row">
              <Icon name="phone" size={16} />
              <div className="val">
                <a className="tel" href={`tel:${client.phone}`}>{client.phone}</a>
                <span className="sub">{client.email}</span>
              </div>
            </div>
          )}

          <div className="popover-row">
            <Icon name="user" size={16} />
            <div className="val">
              {agentName || 'Sin asignar'}
              <span className="sub">Agente asignado</span>
            </div>
          </div>

          {event.notes && (
            <div className="popover-row">
              <Icon name="file" size={16} />
              <div className="val" style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>{event.notes}</div>
            </div>
          )}

          <div className="popover-row">
            <Icon name="calendar" size={16} />
            <div className="val" style={{ display:'flex', alignItems:'center', gap: 6, fontSize: 12, color: 'var(--fg-secondary)' }}>
              {(() => {
                if (!calStatus) {
                  // loading — no indicator
                  return null;
                }
                if (calStatus.configured && event.calendarEventId) {
                  return (
                    <span style={{display:'inline-flex',alignItems:'center',gap:4,padding:'2px 7px',background:'var(--success-50)',color:'var(--success-700)',borderRadius:4,fontWeight:500}}>
                      <span style={{width:6,height:6,borderRadius:'50%',background:'var(--success-500)'}}></span>
                      Sincronizado con Google Calendar
                    </span>
                  );
                }
                if (calStatus.configured) {
                  return (
                    <span style={{display:'inline-flex',alignItems:'center',gap:4,padding:'2px 7px',background:'var(--gray-100)',color:'var(--fg-tertiary)',borderRadius:4,fontWeight:400,fontSize:11}}>
                      <span style={{width:6,height:6,borderRadius:'50%',background:'var(--fg-tertiary)'}}></span>
                      No sincronizado con Google Calendar
                    </span>
                  );
                }
                return (
                  <span style={{display:'inline-flex',alignItems:'center',gap:4,padding:'2px 7px',background:'var(--gray-50)',color:'var(--fg-tertiary)',borderRadius:4,fontWeight:400,fontSize:11}}>
                    <span style={{width:6,height:6,borderRadius:'50%',background:'var(--fg-muted)'}}></span>
                    Google Calendar no configurado
                  </span>
                );
              })()}
            </div>
          </div>
        </div>
        <div className="popover-actions">
          <Button kind="secondary" size="sm" icon="refresh" onClick={() => onReschedule(event)}>Reprogramar</Button>
          <Button kind="secondary" size="sm" icon="edit" onClick={() => onEdit(event)}>Modificar</Button>
          <Button kind="danger" size="sm" icon="x" onClick={() => onCancel(event)}>Cancelar</Button>
        </div>
      </div>
    </Fragment>
  );
}

/** Prefijo de título para cada kind, e.g. "Visita · " */
const KIND_PREFIX = {
  visit: 'Visita · ',
  call:  'Llamada · ',
};

/** Dado el título actual y el nuevo kind, actualiza el prefijo */
function applyKindPrefix(title, newKind) {
  const newPfx = KIND_PREFIX[newKind] || '';
  // Quita cualquier prefijo conocido existente
  const bare = title.replace(/^(Visita|Llamada)\s·\s/, '');
  return newPfx + bare;
}

/** Devuelve true si la combinación fecha+hora ya pasó (margen de 1 min). */
function isPastDateTime(dateISO, timeStr) {
  if (!dateISO || !timeStr) return false;
  const dt = new Date(`${dateISO}T${timeStr}:00`);
  return dt.getTime() < Date.now() - 60_000;
}

export function EventEditor({ event, mode, onClose, onSave, saving = false }) {
  const { data: clients = [] }    = useClients();
  const { data: properties = [] } = useProperties();
  const { data: members = [] }    = useTeamMembers();
  const agents = members.filter(m => (m.status ?? 'accepted') === 'accepted');
  const today = new Date().toISOString().slice(0, 10);
  const [pastError, setPastError] = useState(false);
  const [form, setForm] = useState(() => {
    const base = event || {
      title: '', kind: 'visit', date: today, start: '10:00', end: '11:00',
      clientId: '', propId: '', agentId: '', status: 'pending', notes: '',
    };
    // En modo create, pre-rellena el título con el prefijo del kind
    if (mode === 'create' && !base.title) {
      return { ...base, title: KIND_PREFIX[base.kind] || '' };
    }
    return base;
  });
  const set = (k, v) => { setPastError(false); setForm(f => ({ ...f, [k]: v })); };

  // Kinds that auto-fill from client vs. property
  const CLIENT_KINDS = ['call'];
  const PROP_KINDS   = ['visit'];

  /** Returns the subtitle from the current title (strips any known prefix). */
  const bareTitle = (title) => title.replace(/^(Visita|Llamada)\s·\s/, '');

  const handleKindChange = (newKind) => {
    setForm(f => {
      const pfx = KIND_PREFIX[newKind] || '';
      // Re-derive subtitle from whichever entity is already selected
      let sub = bareTitle(f.title);
      if (CLIENT_KINDS.includes(newKind) && f.clientId) {
        const c = clients.find(cl => cl.id === f.clientId);
        if (c) sub = c.name;
      } else if (PROP_KINDS.includes(newKind) && f.propId) {
        const p = properties.find(pr => String(pr.id) === String(f.propId));
        if (p) sub = p.addr;
      }
      return { ...f, kind: newKind, title: pfx + sub };
    });
  };

  const handleClientChange = (newClientId) => {
    setForm(f => {
      const clientId = newClientId || null;
      if (!CLIENT_KINDS.includes(f.kind)) return { ...f, clientId };
      const pfx = KIND_PREFIX[f.kind] || '';
      const c = clients.find(cl => cl.id === newClientId);
      const sub = c ? c.name : bareTitle(f.title);
      return { ...f, clientId, title: pfx + sub };
    });
  };

  const handlePropChange = (newPropId) => {
    setForm(f => {
      const propId = newPropId || null;
      if (!PROP_KINDS.includes(f.kind)) return { ...f, propId };
      const pfx = KIND_PREFIX[f.kind] || '';
      const p = properties.find(pr => String(pr.id) === newPropId);
      const sub = p ? p.addr : bareTitle(f.title);
      return { ...f, propId, title: pfx + sub };
    });
  };

  const titles = { create: 'Nuevo evento', edit: 'Modificar evento', reschedule: 'Reprogramar evento' };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{titles[mode] || 'Evento'}</h3>
          <span className="close"><IconButton name="x" onClick={onClose} /></span>
        </div>
        <div className="modal-body">
          {mode !== 'reschedule' && (
            <Fragment>
              <div className="field">
                <label>Título</label>
                <input value={form.title} onChange={e => set('title', e.target.value)} placeholder="Visita · Av. Cabildo 2350" />
              </div>
              <div className="field-row">
                <div className="field">
                  <label>Tipo</label>
                  <select value={form.kind} onChange={e => handleKindChange(e.target.value)}>
                    <option value="visit">Visita</option>
                    <option value="call">Llamada</option>
                  </select>
                </div>
                <div className="field">
                  <label>Agente</label>
                  <select value={form.agentId} onChange={e => set('agentId', e.target.value)}>
                    <option value="">Sin asignar</option>
                    {agents.map(a => <option key={a.id} value={a.id}>{a.name || a.email}</option>)}
                  </select>
                </div>
              </div>
            </Fragment>
          )}
          <div className="field-row">
            <div className="field">
              <label>Fecha</label>
              <input type="date" value={form.date} min={mode !== 'edit' ? today : undefined} onChange={e => set('date', e.target.value)} />
            </div>
            <div className="field-row" style={{ gap: 8 }}>
              <div className="field">
                <label>Inicio</label>
                <input type="time" value={form.start} onChange={e => set('start', e.target.value)} />
              </div>
              <div className="field">
                <label>Fin</label>
                <input type="time" value={form.end} onChange={e => set('end', e.target.value)} />
              </div>
            </div>
          </div>
          {mode !== 'reschedule' && (
            <Fragment>
              <div className="field-row">
                <div className="field">
                  <label>Cliente</label>
                  <select value={form.clientId || ''} onChange={e => handleClientChange(e.target.value)}>
                    <option value="">— Sin cliente —</option>
                    {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label>Propiedad</label>
                  <select value={form.propId || ''} onChange={e => handlePropChange(e.target.value)}>
                    <option value="">— Sin propiedad —</option>
                    {properties.map(p => <option key={p.id} value={p.id}>{p.addr}</option>)}
                  </select>
                </div>
              </div>
              <div className="field">
                <label>Notas</label>
                <textarea value={form.notes || ''} onChange={e => set('notes', e.target.value)} placeholder="Detalles para el agente o el cliente..." />
              </div>
            </Fragment>
          )}
          {mode === 'reschedule' && (
            <div style={{padding:'10px 12px',background:'var(--accent-50)',border:'1px solid var(--accent-100)',borderRadius:7,fontSize:12,color:'var(--accent-700)',marginTop:4}}>
              Se enviará una notificación al cliente con la nueva fecha y hora.
            </div>
          )}
        </div>
        <div className="modal-foot">
          {pastError && (
            <span style={{ fontSize: 12, color: 'var(--danger-600)', flex: 1 }}>
              ⚠ No se pueden crear eventos en el pasado.
            </span>
          )}
          <Button kind="ghost" size="sm" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button kind="primary" size="sm" icon="check" disabled={saving} onClick={() => {
            if (mode !== 'edit' && isPastDateTime(form.date, form.start)) {
              setPastError(true);
              return;
            }
            onSave(form);
          }}>
            {saving ? 'Guardando…' : mode === 'create' ? 'Crear evento' : mode === 'reschedule' ? 'Reprogramar' : 'Guardar cambios'}
          </Button>
        </div>
      </div>
    </div>
  );
}

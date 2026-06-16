import React, { useState, useEffect, Fragment } from 'react';
import { Icon, Button, IconButton, Pill, initials, pushToast } from './Primitives';
import { fmtCurrency, fmtTime12 } from './data';
import { useClients, useProperties, useEvents, useActivity, useCreateClient, useUpdateClient, useDeleteClient } from './api';
import { KIND_META } from './EventPopover';
import { useFocusTrap } from './useFocusTrap';
import DocumentsPanel from './DocumentsPanel';
import ExportCsv from './ExportCsv';
import LinkClientProperty from './LinkClientProperty';
import Timeline from './Timeline';

const ROLE_OPTIONS = [
  { value: 'prospect', label: 'Prospecto' },
  { value: 'tenant',  label: 'Inquilino' },
  { value: 'Owner',     label: 'Propietario' },
  { value: 'client',   label: 'Cliente' },
  
];

function ClientEditor({ client, mode, onClose, onSave, saving = false }) {
  const isEdit = mode === 'edit';
  const [form, setForm] = useState({
    name:  client?.name  ?? '',
    phone: client?.phone ?? '',
    email: client?.email ?? '',
    role:  client?.role  ?? 'prospect',
    notes: client?.notes ?? '',
  });
  const [errors, setErrors] = useState({});

  const set = (k, v) => {
    setErrors(e => ({ ...e, [k]: '' }));
    setForm(f => ({ ...f, [k]: v }));
  };

  // Teléfono: solo dígitos (y opcionalmente un + inicial)
  const handlePhone = (e) => {
    const raw = e.target.value;
    const clean = raw.replace(/[^\d]/g, '');
    set('phone', clean);
  };

  const handleSave = () => {
    const newErrors = {};
    if (!form.name.trim())  newErrors.name  = 'El nombre es obligatorio.';
    if (!form.phone.trim()) newErrors.phone = 'El teléfono es obligatorio.';
    if (Object.keys(newErrors).length) { setErrors(newErrors); return; }
    onSave(form);
  };

  const trapRef = useFocusTrap(onClose);

  return (
    <div className="modal-backdrop" onClick={onClose} aria-hidden="true">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="client-editor-title" ref={trapRef} onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3 id="client-editor-title">{isEdit ? 'Modificar cliente' : 'Nuevo cliente'}</h3>
          <span className="close"><IconButton name="x" title="Cerrar" onClick={onClose} /></span>
        </div>
        <div className="modal-body">
          <div className="field">
            <label htmlFor="client-name">Nombre *</label>
            <input
              id="client-name"
              autoFocus
              className={errors.name ? 'invalid' : ''}
              aria-invalid={errors.name ? 'true' : undefined}
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="Nombre completo"
            />
            {errors.name && <span className="field-error">{errors.name}</span>}
          </div>
          <div className="field-row">
            <div className="field">
              <label htmlFor="client-phone">Teléfono / WhatsApp *</label>
              <input
                id="client-phone"
                className={errors.phone ? 'invalid' : ''}
                aria-invalid={errors.phone ? 'true' : undefined}
                inputMode="numeric"
                value={form.phone}
                onChange={handlePhone}
                placeholder="5491112345678"
              />
              {errors.phone && <span className="field-error">{errors.phone}</span>}
            </div>
            <div className="field">
              <label htmlFor="client-email">Email</label>
              <input id="client-email" type="email" value={form.email} onChange={e => set('email', e.target.value)} placeholder="nombre@email.com" />
            </div>
          </div>
          <div className="field">
            <label htmlFor="client-role">Rol</label>
            <select id="client-role" value={form.role} onChange={e => set('role', e.target.value)}>
              {ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="client-notes">Notas</label>
            <textarea id="client-notes" value={form.notes} onChange={e => set('notes', e.target.value)} placeholder="Preferencias, presupuesto, detalles..." />
          </div>
        </div>
        <div className="modal-foot">
          <Button kind="ghost" size="sm" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button kind="primary" size="sm" icon="check" onClick={handleSave} disabled={saving}>
            {saving ? 'Guardando…' : isEdit ? 'Guardar cambios' : 'Crear cliente'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ClientDrawer({ client, onClose, onEdit, onDelete, onOpenProperty, onOpenEvent, onAgenda }) {
  const { data: properties = [] } = useProperties();
  const { data: allEvents = [] }  = useEvents();
  const { data: activity = [] }   = useActivity('client', client?.id);
  if (!client) return null;
  const [tab, setTab] = useState('overview');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const interestProps = (client.interest || []).map(id => properties.find(p => String(p.id) === String(id))).filter(Boolean);
  // Properties linked via property_relations (buyer, tenant, interested)
  const linkedProps = (client.property_relations || []).map(r => ({
    prop: properties.find(p => String(p.id) === String(r.prop_id)),
    relation: r.relation,
  })).filter(({ prop }) => prop);
  const events = allEvents.filter(e => e.clientId === client.id).sort((a,b)=>b.date.localeCompare(a.date));
  const today = new Date().toISOString().slice(0, 10);
  const trapRef = useFocusTrap(onClose);

  return (
    <Fragment>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="drawer wide" role="dialog" aria-modal="true" aria-labelledby="client-drawer-title" ref={trapRef}>
        <div className="drawer-head" style={{padding:0,display:'block',borderBottom:'none'}}>
          <div style={{display:'flex',padding:'12px 16px 0',justifyContent:'flex-end',gap:4,alignItems:'center'}}>
            <IconButton name="edit" title="Editar cliente" onClick={() => onEdit && onEdit(client)} />
            {confirmDelete
              ? <span style={{display:'flex',alignItems:'center',gap:6,fontSize:12,color:'var(--danger-600)'}}>
                  ¿Eliminar?
                  <Button kind="danger" size="sm" onClick={() => onDelete && onDelete(client)}>Sí</Button>
                  <Button kind="ghost" size="sm" onClick={() => setConfirmDelete(false)}>No</Button>
                </span>
              : <IconButton name="trash" title="Eliminar cliente" onClick={() => setConfirmDelete(true)} />
            }
            <IconButton name="x" onClick={onClose} />
          </div>
          <div className="client-hero" style={{borderBottom:'none',paddingTop:6}}>
            <span className="client-av size-lg" aria-hidden="true">{initials(client.name)}</span>
            <div className="info">
              <h2 id="client-drawer-title">{client.name}</h2>
              <div className="meta">
                <Pill kind={client.role} />
                {client.tags.map((t,i) => <span key={i} className="client-tag">{t}</span>)}
              </div>
              <div className="meta" style={{marginTop:8}}>
                <span><Icon name="phone" size={12} style={{verticalAlign:'middle',marginRight:4,color:'var(--fg-tertiary)'}}/> <a href={`tel:${client.phone}`}>{client.phone}</a></span>
                <span><Icon name="mail" size={12} style={{verticalAlign:'middle',marginRight:4,color:'var(--fg-tertiary)'}}/> <a href={`mailto:${client.email}`}>{client.email}</a></span>
              </div>
              <div className="quick">
                <Button kind="primary" size="sm" icon="phone" disabled={!client.phone}
                        onClick={() => client.phone && window.open(`tel:${client.phone}`)}>Llamar</Button>
                <Button kind="secondary" size="sm" icon="whatsapp" disabled={!client.phone}
                        onClick={() => client.phone && window.open(`https://wa.me/${client.phone.replace(/[^\d]/g, '')}`, '_blank', 'noopener,noreferrer')}>WhatsApp</Button>
                <Button kind="secondary" size="sm" icon="mail" disabled={!client.email}
                        onClick={() => client.email && window.open(`mailto:${client.email}`)}>Correo</Button>
                <Button kind="secondary" size="sm" icon="calendar" disabled={!onAgenda}
                        onClick={() => onAgenda && onAgenda(client)}>Agendar</Button>
              </div>
            </div>
          </div>
        </div>
        <div className="tabs" role="tablist" aria-label="Secciones del cliente">
          {[['overview','Resumen'],['interest','Propiedades'],['activity','Actividad'],['docs','Documentos']].map(([k,l]) => (
            <button key={k} role="tab" id={`client-tab-${k}`} aria-controls={`client-tabpanel-${k}`}
                    aria-selected={tab===k} tabIndex={tab===k ? 0 : -1}
                    className={tab===k?'active':''} onClick={()=>setTab(k)}>{l}</button>
          ))}
        </div>
        <div className="drawer-body" role="tabpanel" id={`client-tabpanel-${tab}`} aria-labelledby={`client-tab-${tab}`}>
          {tab === 'overview' && <Fragment>
            <div className="detail-block">
              <h3>Datos</h3>
              <dl className="def-list">
                <dt>DNI</dt><dd className="tabular">{client.dni || '—'}</dd>
                <dt>Email</dt><dd>{client.email ? <a href={`mailto:${client.email}`}>{client.email}</a> : '—'}</dd>
                <dt>Cliente desde</dt><dd>{client.since}</dd>
                <dt>Agente asignado</dt><dd>{client.agent || '—'}</dd>
                <dt>Último contacto</dt><dd>{client.lastContact}</dd>
                <dt>Visitas</dt><dd className="tabular">{client.visits}</dd>
              </dl>
            </div>
            {client.notes && (
              <div className="detail-block">
                <h3>Notas</h3>
                <div style={{fontSize:13,color:'var(--fg-secondary)'}}>{client.notes}</div>
              </div>
            )}
            <div className="detail-block">
              <h3>Próximos eventos</h3>
              {events.filter(e => e.date >= today).length === 0 ? <div className="muted" style={{fontSize:12}}>Sin eventos programados.</div> :
                events.filter(e => e.date >= today).slice(0,3).map(e => (
                  <div key={e.id} style={{display:'flex',gap:10,padding:'8px 0',borderBottom:'1px solid var(--border-subtle)',fontSize:13,alignItems:'center',cursor:'pointer'}} onClick={(ev) => onOpenEvent && onOpenEvent(e, ev.currentTarget.getBoundingClientRect())}>
                    <span style={{width:6,height:6,borderRadius:'50%',background:KIND_META[e.kind]?.color || 'var(--gray-400)'}}></span>
                    <span className="tabular muted" style={{minWidth:78}}>{e.date.slice(8)}/{e.date.slice(5,7)} {fmtTime12(e.start)}</span>
                    <span style={{flex:1}}>{e.title.replace(/^[^·]+·\s*/,'')}</span>
                    {e.status === 'cancelled' ? <Pill kind="cancelled">Cancelada</Pill> : e.status === 'pending' ? <Pill kind="pending">Por confirmar</Pill> : <Pill kind="paid">Confirmada</Pill>}
                  </div>
                ))}
            </div>
          </Fragment>}
          {tab === 'interest' && <div className="detail-block">
            <h3>Propiedades vinculadas ({interestProps.length + linkedProps.length})</h3>
            <div style={{marginBottom:10}}>
              <LinkClientProperty side="client" client={client} />
            </div>
            {interestProps.length === 0 && linkedProps.length === 0
              ? <div className="muted" style={{fontSize:12}}>Sin propiedades asignadas.</div>
              : <>
                {linkedProps.map(({ prop, relation }) => (
                  <div key={`linked-${prop.id}-${relation}`} style={{display:'flex',alignItems:'center',gap:12,padding:'10px 0',borderBottom:'1px solid var(--border-subtle)',cursor:'pointer'}} onClick={() => onOpenProperty(prop)}>
                    <span className="prop-thumb" style={{background:prop.photo,width:52,height:42}}><Icon name="building" /></span>
                    <div style={{flex:1,minWidth:0}}>
                      <div style={{fontSize:13,fontWeight:500}}>{prop.addr}</div>
                      <div style={{fontSize:11,color:'var(--fg-tertiary)'}}>{prop.neigh} · {prop.rooms !== '—' && prop.rooms + ' · '}{prop.m2} m²</div>
                    </div>
                    <span className={`pill ${relation === 'buyer' ? 'pill-paid' : relation === 'tenant' ? 'pill-rented' : 'pill-available'}`} style={{fontSize:10}}>
                      {relation === 'buyer' ? 'Comprador' : relation === 'tenant' ? 'Inquilino' : 'Interesado'}
                    </span>
                    <div className="tabular" style={{fontSize:13,fontWeight:500,minWidth:110,textAlign:'right'}}>{fmtCurrency(prop.price, prop.currency)}</div>
                  </div>
                ))}
                {interestProps.map(p => (
                  <div key={p.id} style={{display:'flex',alignItems:'center',gap:12,padding:'10px 0',borderBottom:'1px solid var(--border-subtle)',cursor:'pointer'}} onClick={() => onOpenProperty(p)}>
                    <span className="prop-thumb" style={{background:p.photo,width:52,height:42}}><Icon name="building" /></span>
                    <div style={{flex:1,minWidth:0}}>
                      <div style={{fontSize:13,fontWeight:500}}>{p.addr}</div>
                      <div style={{fontSize:11,color:'var(--fg-tertiary)'}}>{p.neigh} · {p.rooms !== '—' && p.rooms + ' · '}{p.m2} m²</div>
                    </div>
                    <Pill kind={p.status} />
                    <div className="tabular" style={{fontSize:13,fontWeight:500,minWidth:110,textAlign:'right'}}>{fmtCurrency(p.price, p.currency)}</div>
                  </div>
                ))}
              </>
            }
          </div>}
          {tab === 'docs' && (
            <DocumentsPanel clientId={client.id} title="Documentos del cliente" />
          )}
          {tab === 'activity' && <div className="detail-block">
            <h3>Historial ({events.length + activity.length})</h3>
            <Timeline events={events} activity={activity}
                      emptyText="Sin actividad registrada." />
          </div>}
        </div>
      </div>
    </Fragment>
  );
}

export default function Clients({ initialClient, initialPhone, onOpenProperty, onOpenEvent, onAgenda }) {
  const { data: clients = [] } = useClients();
  const createClientMut = useCreateClient();
  const updateClientMut = useUpdateClient();
  const deleteClientMut = useDeleteClient();

  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [open, setOpen]     = useState(initialClient || null);
  const [editor, setEditor] = useState(null); // { mode: 'create'|'edit', client? }

  useEffect(() => { if (initialClient) setOpen(initialClient); }, [initialClient]);

  // Open client by phone (from notification navigation)
  const [phoneHandled, setPhoneHandled] = React.useState(false);
  useEffect(() => {
    if (!initialPhone || phoneHandled || clients.length === 0) return;
    const found = clients.find(c => c.phone === initialPhone || c.phone?.endsWith(initialPhone.slice(-8)));
    if (found) { setPhoneHandled(true); setOpen(found); }
  }, [initialPhone, clients, phoneHandled]);

  const handleDelete = (client) => {
    setOpen(null);
    deleteClientMut.mutate(client.id, {
      onSuccess: () => pushToast({ text: 'Cliente eliminado.' }),
      onError:   () => pushToast({ text: 'Error al eliminar el cliente.', kind: 'danger' }),
    });
  };

  const handleSave = (form) => {
    const mode = editor.mode;
    const clientId = editor.client?.id;
    if (mode === 'create') {
      setEditor(null); // optimistic close for create
      createClientMut.mutate(form, {
        onSuccess: () => pushToast({ text: 'Cliente creado.' }),
        onError:   () => pushToast({ text: 'Error al crear el cliente.', kind: 'danger' }),
      });
    } else {
      updateClientMut.mutate({ id: clientId, ...form }, {
        onSuccess: (_, vars) => {
          setEditor(null); // close only on success for edit
          setOpen(c => c ? { ...c, ...form } : c);
          pushToast({ text: 'Cliente actualizado.' });
        },
        onError: () => pushToast({ text: 'Error al guardar los cambios.', kind: 'danger' }),
      });
    }
  };

  const filtered = clients.filter(c => {
    if (filter !== 'all' && c.role !== filter) return false;
    if (search) {
      const q = search.toLowerCase();
      const matchName = c.name?.toLowerCase().includes(q);
      const strippedPhone = search.replace(/\D/g, '');
      const matchPhone = strippedPhone.length > 0 && c.phone?.includes(strippedPhone);
      if (!matchName && !matchPhone) return false;
    }
    return true;
  });
  const counts = {
    all: clients.length,
    prospect: clients.filter(c=>c.role==='prospect').length,
    tenant: clients.filter(c=>c.role==='tenant').length,
    owner: clients.filter(c=>c.role==='owner').length,
  };

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Clientes</h1>
          <div className="sub">{clients.length} contactos · {counts.prospect} prospectos activos · {counts.tenant} inquilinos</div>
        </div>
        <div className="page-h-actions">
          <ExportCsv dataset="leads" label="Exportar" />
          <Button kind="primary" icon="plus" onClick={() => setEditor({ mode: 'create' })}>Nuevo cliente</Button>
        </div>
      </div>

      <div className="page-kpis">
        <div className="kpi-grid">
          <div className="kpi"><span className="kpi-label">Prospectos activos</span><span className="kpi-value">{counts.prospect}</span><span className="kpi-delta up"><Icon name="arrowUp" size={12}/>+3 esta semana</span></div>
          <div className="kpi"><span className="kpi-label">Inquilinos</span><span className="kpi-value">{counts.tenant}</span><span className="kpi-delta">Pago al día: 100%</span></div>
          <div className="kpi"><span className="kpi-label">Propietarios</span><span className="kpi-value">{counts.owner}</span><span className="kpi-delta">5 propiedades en cartera</span></div>
          <div className="kpi"><span className="kpi-label">Tasa de conversión</span><span className="kpi-value" style={{color:'var(--accent-500)'}}>21%</span><span className="kpi-delta up"><Icon name="arrowUp" size={12}/>+4 pts vs abril</span></div>
        </div>
      </div>

      <div className="scroll-surface surface">
        <div className="filter-bar">
          <input placeholder="Buscar por nombre o teléfono..." value={search} onChange={e=>setSearch(e.target.value)} />
          {[['all','Todos',counts.all],['prospect','Prospectos',counts.prospect],['tenant','Inquilinos',counts.tenant],['owner','Propietarios',counts.owner]].map(([k,l,n]) => (
            <button key={k} type="button" className={`chip ${filter===k?'active':''}`} aria-pressed={filter===k} onClick={()=>setFilter(k)}>{l}<span className="num">{n}</span></button>
          ))}
        </div>
        <div className="tbl-scroll">
          <table className="tbl clients-tbl">
            <thead><tr>
              <th>Cliente</th><th>Tipo</th><th>Teléfono</th><th>Agente</th><th>Visitas</th><th>Último contacto</th><th></th>
            </tr></thead>
            <tbody>
              {filtered.map(c => (
                <tr key={c.id} tabIndex={0} aria-label={`Ver perfil de ${c.name}`}
                    onClick={() => setOpen(c)}
                    onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setOpen(c); } }}>
                  <td>
                    <div className="client-row-name">
                      <span className="client-av" aria-hidden="true">{initials(c.name)}</span>
                      <div>
                        <b>{c.name}</b>
                        <span>{c.tags.join(' · ')}</span>
                      </div>
                    </div>
                  </td>
                  <td><Pill kind={c.role} /></td>
                  <td className="tabular muted">{c.phone}</td>
                  <td className="muted">{c.agent}</td>
                  <td className="tabular">{c.visits}</td>
                  <td className="muted">{c.lastContact}</td>
                  <td><div className="row-actions"><IconButton name="phone" aria-label="Llamar" /><IconButton name="whatsapp" aria-label="WhatsApp" /><IconButton name="more" aria-label="Más acciones" /></div></td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan="7" className="tbl-empty">No hay clientes que coincidan con los filtros.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {open && (
        <ClientDrawer
          client={open}
          onClose={() => setOpen(null)}
          onEdit={(c) => setEditor({ mode: 'edit', client: c })}
          onDelete={handleDelete}
          onOpenProperty={onOpenProperty}
          onOpenEvent={onOpenEvent}
          onAgenda={onAgenda ? (c) => { setOpen(null); onAgenda(c); } : undefined}
        />
      )}
      {editor && (
        <ClientEditor
          client={editor.client}
          mode={editor.mode}
          saving={editor.mode === 'edit' && updateClientMut.isPending}
          onClose={() => !updateClientMut.isPending && setEditor(null)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}

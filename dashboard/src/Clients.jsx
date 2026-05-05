import React, { useState, useEffect, Fragment } from 'react';
import { Icon, Button, IconButton, Pill, initials } from './Primitives';
import { fmtCurrency, fmtTime12 } from './data';
import { useClients, useProperties, useEvents } from './api';
import { KIND_META } from './EventPopover';

function ClientDrawer({ client, onClose, onOpenProperty, onOpenEvent }) {
  const { data: properties = [] } = useProperties();
  const { data: allEvents = [] }  = useEvents();
  if (!client) return null;
  const [tab, setTab] = useState('overview');
  const interestProps = (client.interest || []).map(id => properties.find(p => String(p.id) === String(id))).filter(Boolean);
  const events = allEvents.filter(e => e.clientId === client.id).sort((a,b)=>b.date.localeCompare(a.date));
  const today = new Date().toISOString().slice(0, 10);

  return (
    <Fragment>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer wide">
        <div className="drawer-head" style={{padding:0,display:'block',borderBottom:'none'}}>
          <div style={{display:'flex',padding:'12px 16px 0',justifyContent:'flex-end'}}>
            <IconButton name="x" onClick={onClose} />
          </div>
          <div className="client-hero" style={{borderBottom:'none',paddingTop:6}}>
            <span className="client-av size-lg">{initials(client.name)}</span>
            <div className="info">
              <h2>{client.name}</h2>
              <div className="meta">
                <Pill kind={client.role} />
                {client.tags.map((t,i) => <span key={i} className="client-tag">{t}</span>)}
              </div>
              <div className="meta" style={{marginTop:8}}>
                <span><Icon name="phone" size={12} style={{verticalAlign:'middle',marginRight:4,color:'var(--fg-tertiary)'}}/> <a href={`tel:${client.phone}`}>{client.phone}</a></span>
                <span><Icon name="mail" size={12} style={{verticalAlign:'middle',marginRight:4,color:'var(--fg-tertiary)'}}/> <a href={`mailto:${client.email}`}>{client.email}</a></span>
              </div>
              <div className="quick">
                <Button kind="primary" size="sm" icon="phone">Llamar</Button>
                <Button kind="secondary" size="sm" icon="whatsapp">WhatsApp</Button>
                <Button kind="secondary" size="sm" icon="mail">Correo</Button>
                <Button kind="secondary" size="sm" icon="calendar">Agendar</Button>
              </div>
            </div>
          </div>
        </div>
        <div className="tabs">
          {[['overview','Resumen'],['interest','Intereses'],['activity','Actividad']].map(([k,l]) => (
            <button key={k} className={tab===k?'active':''} onClick={()=>setTab(k)}>{l}</button>
          ))}
        </div>
        <div className="drawer-body">
          {tab === 'overview' && <Fragment>
            <div className="detail-block">
              <h3>Datos</h3>
              <dl className="def-list">
                <dt>DNI</dt><dd className="tabular">{client.dni || '—'}</dd>
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
            <h3>Propiedades de interés ({interestProps.length})</h3>
            {interestProps.length === 0
              ? <div className="muted" style={{fontSize:12}}>Sin propiedades asignadas.</div>
              : interestProps.map(p => (
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
          </div>}
          {tab === 'activity' && <div className="detail-block">
            <h3>Historial ({events.length})</h3>
            {events.length === 0 ? <div className="muted" style={{fontSize:12}}>Sin actividad registrada.</div> : events.map(e => (
              <div key={e.id} style={{display:'flex',gap:10,padding:'10px 0',borderBottom:'1px solid var(--border-subtle)',fontSize:13,alignItems:'flex-start'}}>
                <span style={{width:24,height:24,borderRadius:6,background:'var(--gray-50)',display:'inline-flex',alignItems:'center',justifyContent:'center',color:KIND_META[e.kind]?.color || 'var(--gray-400)',flexShrink:0}}>
                  <Icon name={e.kind === 'visit' ? 'mapPin' : e.kind === 'call' ? 'phone' : e.kind === 'sign' ? 'contract' : 'calendar'} size={13} />
                </span>
                <div style={{flex:1}}>
                  <div style={{fontWeight:500}}>{e.title.replace(/^[^·]+·\s*/,'')}</div>
                  <div style={{fontSize:11,color:'var(--fg-tertiary)'}}>{e.date} · {fmtTime12(e.start)} · {e.agent}</div>
                </div>
                {e.status === 'cancelled' ? <Pill kind="cancelled">Cancelada</Pill> : e.status === 'pending' ? <Pill kind="pending">Pendiente</Pill> : <Pill kind="paid">OK</Pill>}
              </div>
            ))}
          </div>}
        </div>
      </div>
    </Fragment>
  );
}

export default function Clients({ initialClient, onOpenProperty, onOpenEvent }) {
  const { data: clients = [] } = useClients();
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(initialClient || null);
  useEffect(() => { if (initialClient) setOpen(initialClient); }, [initialClient]);

  const filtered = clients.filter(c => {
    if (filter !== 'all' && c.role !== filter) return false;
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
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
          <Button kind="secondary" icon="download" size="sm">Exportar</Button>
          <Button kind="primary" icon="plus" size="sm">Nuevo cliente</Button>
        </div>
      </div>

      <div className="page-kpis">
        <div className="kpi-grid" style={{gridTemplateColumns:'repeat(4,1fr)'}}>
          <div className="kpi"><span className="kpi-label">Prospectos activos</span><span className="kpi-value">{counts.prospect}</span><span className="kpi-delta up"><Icon name="arrowUp" size={12}/>+3 esta semana</span></div>
          <div className="kpi"><span className="kpi-label">Inquilinos</span><span className="kpi-value">{counts.tenant}</span><span className="kpi-delta">Pago al día: 100%</span></div>
          <div className="kpi"><span className="kpi-label">Propietarios</span><span className="kpi-value">{counts.owner}</span><span className="kpi-delta">5 propiedades en cartera</span></div>
          <div className="kpi"><span className="kpi-label">Tasa de conversión</span><span className="kpi-value" style={{color:'var(--accent-500)'}}>21%</span><span className="kpi-delta up"><Icon name="arrowUp" size={12}/>+4 pts vs abril</span></div>
        </div>
      </div>

      <div className="scroll-surface surface">
        <div className="filter-bar">
          <input placeholder="Buscar por nombre..." value={search} onChange={e=>setSearch(e.target.value)} />
          {[['all','Todos',counts.all],['prospect','Prospectos',counts.prospect],['tenant','Inquilinos',counts.tenant],['owner','Propietarios',counts.owner]].map(([k,l,n]) => (
            <span key={k} className={`chip ${filter===k?'active':''}`} onClick={()=>setFilter(k)}>{l}<span className="num">{n}</span></span>
          ))}
        </div>
        <div className="tbl-scroll">
          <table className="tbl">
            <thead><tr>
              <th>Cliente</th><th>Tipo</th><th>Teléfono</th><th>Agente</th><th>Visitas</th><th>Último contacto</th><th></th>
            </tr></thead>
            <tbody>
              {filtered.map(c => (
                <tr key={c.id} onClick={() => setOpen(c)}>
                  <td>
                    <div className="client-row-name">
                      <span className="client-av">{initials(c.name)}</span>
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
                  <td><div className="row-actions"><IconButton name="phone" /><IconButton name="whatsapp" /><IconButton name="more" /></div></td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan="7" className="tbl-empty">No hay clientes que coincidan con los filtros.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {open && <ClientDrawer client={open} onClose={() => setOpen(null)} onOpenProperty={onOpenProperty} onOpenEvent={onOpenEvent} />}
    </div>
  );
}

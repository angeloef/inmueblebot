import React, { useState, useEffect, useRef, Fragment } from 'react';
import { Icon, Button, IconButton, Pill, StatusDropdown, initials, pushToast } from './Primitives';
import { fmtCurrency, fmtTime12 } from './data';
import { useProperties, useClients, useEvents, useCreateProperty, useUpdateProperty, useDeleteProperty, useUpdatePropertyStatus, useRelateClientToProperty, useBranches, useReassignProperty, useActivity, propertyApi, useCreatePropertyImport, useMyPropertyImports } from './api';
import { KIND_META } from './EventPopover';
import { useFocusTrap } from './useFocusTrap';
import { useAuth } from './auth';
import Timeline from './Timeline';

/** Bloque "Sucursal" del drawer: solo para el dueño de una org en vista consolidada
 *  (Todas las sucursales). Permite mover la propiedad a otra sucursal. */
function ReassignBranchBlock({ propertyId }) {
  const { me, activeBranch } = useAuth();
  const isOrgConsolidated = me?.scope === 'org' && !activeBranch;
  const { data: branches = [] } = useBranches(isOrgConsolidated);
  const reassign = useReassignProperty();
  const [target, setTarget] = useState('');
  if (!isOrgConsolidated || branches.length === 0) return null;

  const move = () => {
    if (!target) return;
    reassign.mutate({ propId: propertyId, branchId: target }, {
      onSuccess: () => { pushToast({ text: 'Propiedad reasignada.', kind: 'success' }); setTarget(''); },
      onError: (e) => pushToast({ text: e?.response?.data?.detail || 'Error al reasignar.', kind: 'danger' }),
    });
  };

  return (
    <div className="detail-block">
      <h3>Sucursal</h3>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={target} onChange={(e) => setTarget(e.target.value)} style={{ flex: 1, minWidth: 180 }}>
          <option value="">Mover a sucursal…</option>
          {branches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
        <Button kind="secondary" size="sm" disabled={!target || reassign.isPending} onClick={move}>
          {reassign.isPending ? 'Moviendo…' : 'Mover'}
        </Button>
      </div>
    </div>
  );
}

/** Devuelve true si el string es una URL de imagen (base64 o http) */
const isImg = (s) => s && (
  s.startsWith('data:') ||
  s.startsWith('http') ||
  s.startsWith('/') ||
  // Raw base64: long string of base64 chars (no spaces/newlines)
  (s.length > 50 && /^[A-Za-z0-9+/=]+$/.test(s.slice(0, 100)))
);

/**
 * Imagen de propiedad con skeleton shimmer (estilo YouTube) mientras carga.
 * La imagen es un recurso HTTP diferido (loading=lazy): solo se descargan las
 * visibles, en paralelo y cacheadas. El shimmer se muestra hasta `onLoad`.
 */
function PropertyImage({ src, alt = '', radius = 0, aspect = '4/3', fallback = null }) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);
  const showImg = isImg(src) && !errored;
  return (
    <div className="prop-img" style={{ aspectRatio: aspect || undefined, borderRadius: radius }}>
      {showImg && !loaded && <span className="img-skeleton" aria-hidden="true" />}
      {showImg ? (
        <img
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setErrored(true)}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block',
                   opacity: loaded ? 1 : 0, transition: 'opacity var(--dur-base, .25s) ease' }}
        />
      ) : fallback}
    </div>
  );
}

function PropertyDrawer({ property, onClose, onOpenClient, onAgenda, onEdit, onDelete }) {
  const { data: clients = [] }   = useClients();
  const { data: properties = [] } = useProperties();
  const { data: allEvents = [] } = useEvents();
  const updateStatus     = useUpdatePropertyStatus();
  const relateClient     = useRelateClientToProperty();
  const { data: activity = [] } = useActivity('property', property?.id);
  // Use fresh data from the cache so drawer reflects mutation updates immediately
  const freshProperty = properties.find(p => String(p.id) === String(property.id)) || property;
  property = freshProperty;
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignSearch, setAssignSearch] = useState('');
  const [assignRelation, setAssignRelation] = useState(freshProperty.operation === 'rent' ? 'tenant' : 'buyer');
  const [linkEditOpen, setLinkEditOpen] = useState(null);
  const trapRef = useFocusTrap(onClose);
  const assignBlockRef = useRef(null);
  const pendingScrollRef = useRef(false);
  // Desplazar al bloque de asignación recién cuando el alta se abrió y re-renderizó,
  // así el scroll cae sobre el formulario ya expandido (no antes del re-render).
  useEffect(() => {
    if (assignOpen && pendingScrollRef.current) {
      pendingScrollRef.current = false;
      assignBlockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [assignOpen]);
  if (!property) return null;

  // Interested clients: from property_relations (new) and legacy interest array
  const relatedClientIds = new Set();
  const interestedClients = clients.filter(c => {
    const fromRelations = (c.property_relations || []).some(r => String(r.prop_id) === String(property.id) && r.relation === 'interested');
    const fromLegacy = (c.interest || []).includes(String(property.id));
    if (fromRelations || fromLegacy) relatedClientIds.add(c.id);
    return fromRelations || fromLegacy;
  });
  // Buyer/tenant from property_relations
  const buyerClient = clients.find(c => (c.property_relations || []).some(r => String(r.prop_id) === String(property.id) && r.relation === 'buyer'));
  const tenantClient = clients.find(c => (c.property_relations || []).some(r => String(r.prop_id) === String(property.id) && r.relation === 'tenant'));

  // Atajo del header: si no hay cliente vinculado, abre el alta preseleccionada en
  // "Inquilino" y luego desplaza (vía el effect de arriba); si ya hay comprador o
  // inquilino, solo desplaza a la tarjeta existente (evita doble inquilino). Plan 02.
  const handleLinkTenant = () => {
    if (!buyerClient && !tenantClient) {
      setAssignRelation('tenant');
      pendingScrollRef.current = true;
      setAssignOpen(true);
    } else {
      requestAnimationFrame(() => {
        assignBlockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  };

  const events = allEvents.filter(e => String(e.propId) === String(property.id));
  /** true si la propiedad es para alquiler (muestra /mes en precio) */
  const isRent = property.operation === 'rent' && property.status !== 'sale';
  return (
    <Fragment>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="drawer wide" role="dialog" aria-modal="true" aria-labelledby="property-drawer-title" ref={trapRef}>
        <div className="drawer-head">
          <div>
            <h2 id="property-drawer-title">{property.addr}</h2>
            <div className="sub">{property.neigh} · {property.type} · {property.rooms !== '—' && property.rooms + ' · '}{property.m2} m²</div>
          </div>
          <span className="close"><IconButton name="x" title="Cerrar" onClick={onClose} /></span>
        </div>
        <div className="drawer-body">
          {/* ── Image Gallery ── */}
          {(property.images?.length > 0 || property.photo) ? (
            <ImageGallery images={property.images || (property.photo ? [property.photo] : [])} />
          ) : (
            <div className="prop-photo" style={{ background: property.photo || 'var(--gray-100)', marginBottom: 14 }}>Foto · {property.type}</div>
          )}

          <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:14,flexWrap:'wrap'}}>
            <StatusDropdown kind={property.status} onSelect={(s) => updateStatus.mutate({ id: property.id, status: s })} />
            {buyerClient && <Pill kind="active">Comprador: {buyerClient.name}</Pill>}
            {tenantClient && <Pill kind="active">Inquilino: {tenantClient.name}</Pill>}
            <span className="tabular" style={{fontSize:18,fontWeight:600,letterSpacing:'-0.01em'}}>
              {fmtCurrency(property.price, property.currency)}
            </span>
            {isRent && <span className="muted" style={{fontSize:12}}>/ mes</span>}
            <span style={{marginLeft:'auto',display:'flex',gap:6}}>
              <Button kind="danger" size="sm" icon="trash" onClick={() => onDelete && onDelete(property)}>Eliminar</Button>
              <Button kind="secondary" size="sm" icon="user-plus"
                      aria-label={(buyerClient || tenantClient) ? 'Ver cliente vinculado' : 'Vincular inquilino'}
                      onClick={handleLinkTenant}>Vincular inquilino</Button>
              <Button kind="secondary" size="sm" icon="edit" onClick={() => onEdit && onEdit(property)}>Editar</Button>
              <Button kind="primary" size="sm" icon="calendar" onClick={() => onAgenda(property)}>Agendar visita</Button>
            </span>
          </div>

          <div className="detail-block">
            <h3>Características</h3>
            <div className="prop-stats-grid">
              <div style={{display:'flex',alignItems:'center',gap:8}}>
                <Icon name="bed" size={16} style={{color:'var(--fg-tertiary)'}} />
                <div><div style={{fontSize:13,fontWeight:500}}>{property.rooms}</div><div style={{fontSize:11,color:'var(--fg-tertiary)'}}>Ambientes</div></div>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:8}}>
                <Icon name="bath" size={16} style={{color:'var(--fg-tertiary)'}} />
                <div><div style={{fontSize:13,fontWeight:500}}>{property.baths}</div><div style={{fontSize:11,color:'var(--fg-tertiary)'}}>Baños</div></div>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:8}}>
                <Icon name="ruler" size={16} style={{color:'var(--fg-tertiary)'}} />
                <div><div style={{fontSize:13,fontWeight:500}}>{property.m2} m²</div><div style={{fontSize:11,color:'var(--fg-tertiary)'}}>Superficie</div></div>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:8}}>
                <Icon name="car" size={16} style={{color:'var(--fg-tertiary)'}} />
                <div><div style={{fontSize:13,fontWeight:500}}>{property.parking}</div><div style={{fontSize:11,color:'var(--fg-tertiary)'}}>Cocheras</div></div>
              </div>
            </div>
          </div>

          <div className="detail-block">
            <h3>Datos</h3>
            <dl className="def-list">
              <dt>Dirección</dt><dd>{property.addr}, {property.neigh}</dd>
              <dt>Tipo</dt><dd>{property.type}</dd>
              <dt>Operación</dt><dd>{property.operation === 'rent' ? 'Alquiler' : 'Venta'}</dd>
              <dt>Código interno</dt><dd className="tabular">IB-{property.id.toUpperCase()}</dd>
            </dl>
          </div>

          <ReassignBranchBlock propertyId={property.id} />

          <div className="detail-block">
            <h3>Clientes interesados ({interestedClients.length})</h3>
            {interestedClients.length === 0 ? (
              <div className="muted" style={{fontSize:12}}>Sin clientes asignados todavía.</div>
            ) : interestedClients.map(c => (
              <div key={c.id} className="popover-attendee" role="button" tabIndex={0} aria-label={`Ver perfil de ${c.name}`} style={{padding:'8px 0',borderBottom:'1px solid var(--border-subtle)',cursor:'pointer'}} onClick={() => onOpenClient && onOpenClient(c)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenClient && onOpenClient(c); } }}>
                <span className="av" aria-hidden="true">{initials(c.name)}</span>
                <div style={{flex:1}}>
                  <div className="name" style={{fontSize:13,fontWeight:500}}>{c.name}</div>
                  <div className="meta">{c.tags.join(' · ')}</div>
                </div>
                <Pill kind={c.role} />
              </div>
            ))}
          </div>

          <div className="detail-block" ref={assignBlockRef}>
            <h3>Asignar comprador / inquilino</h3>
            <div style={{display:'flex',flexDirection:'column',gap:8,marginTop:4}}>
              {(() => {
                const linked = buyerClient || tenantClient;
                if (linked) {
                  const isBuyer = buyerClient === linked;
                  const bgColor = isBuyer ? 'var(--success-50)' : 'var(--info-50)';
                  const bdColor = isBuyer ? 'var(--success-100)' : 'var(--info-100)';
                  return (
                    <React.Fragment>
                      <div className="popover-attendee" style={{padding:'10px 10px',borderRadius:8,background:bgColor,border:'1px solid '+bdColor,cursor:'pointer'}} onClick={() => onOpenClient && onOpenClient(linked)}>
                        <span className="av">{initials(linked.name)}</span>
                        <div style={{flex:1,minWidth:0}}>
                          <div style={{fontSize:13,fontWeight:600,color:isBuyer?'var(--success-700)':'var(--info-700)'}}>{linked.name}</div>
                          <div style={{fontSize:11,color:isBuyer?'var(--success-500)':'var(--info-500)'}}>{linked.phone || linked.email || 'Sin teléfono'}</div>
                        </div>
                        <Pill kind="active">{isBuyer ? 'Comprador' : 'Inquilino'}</Pill>
                        <div style={{position:'relative',marginLeft:4}} onClick={e => e.stopPropagation()}>
                          {linkEditOpen === (isBuyer ? 'buyer' : 'tenant') ? (
                            <div className="status-dropdown-menu" style={{position:'absolute',top:'100%',right:0,minWidth:160,zIndex:10}} role="menu">
                              <button type="button" role="menuitem" className="status-dropdown-item" onClick={() => { setLinkEditOpen(null); relateClient.mutate({ prop_id: property.id, client_id: linked.id, relation: isBuyer ? 'tenant' : 'buyer', update_status: true }, { onSuccess: () => pushToast({ text: 'Relación actualizada.', kind: 'success' }), onError: () => pushToast({ text: 'Error al actualizar.', kind: 'danger' }) }); }}>
                                Cambiar a {isBuyer ? 'Inquilino' : 'Comprador'}
                              </button>
                              <button type="button" role="menuitem" className="status-dropdown-item" onClick={() => { setLinkEditOpen(null); relateClient.mutate({ prop_id: property.id, client_id: linked.id, relation: 'interested', update_status: false }, { onSuccess: () => pushToast({ text: 'Cliente movido a interesados.', kind: 'success' }), onError: () => pushToast({ text: 'Error al actualizar.', kind: 'danger' }) }); }}>
                                Cambiar a Interesado
                              </button>
                              <div style={{borderTop:'1px solid var(--border-subtle)',margin:'4px 0'}} />
                              <button type="button" role="menuitem" className="status-dropdown-item" style={{color:'var(--danger-500)'}} onClick={() => { setLinkEditOpen(null); relateClient.mutate({ prop_id: property.id, client_id: linked.id, relation: 'none' }, { onSuccess: () => pushToast({ text: 'Cliente desvinculado.', kind: 'success' }), onError: () => pushToast({ text: 'Error al desvincular.', kind: 'danger' }) }); }}>
                                Desvincular
                              </button>
                            </div>
                          ) : null}
                          <IconButton name={linkEditOpen === (isBuyer ? 'buyer' : 'tenant') ? 'x' : 'edit'} aria-label={linkEditOpen === (isBuyer ? 'buyer' : 'tenant') ? 'Cerrar menú' : 'Editar relación'} onClick={() => setLinkEditOpen(linkEditOpen === (isBuyer ? 'buyer' : 'tenant') ? null : (isBuyer ? 'buyer' : 'tenant'))} />
                        </div>
                      </div>
                    </React.Fragment>
                  );
                }
                return !assignOpen ? (
                  <Button kind="secondary" size="sm" onClick={() => setAssignOpen(true)} icon="user-plus">Vincular cliente</Button>
                ) : (
                  <div style={{display:'flex',flexDirection:'column',gap:8}}>
                    <input placeholder="Buscar cliente por nombre..." value={assignSearch} onChange={e => setAssignSearch(e.target.value)}
                           style={{width:'100%',padding:'6px 10px',fontSize:13,border:'1px solid var(--border-default)',borderRadius:6}} autoFocus />
                    <div style={{display:'flex',gap:6}}>
                      {[['buyer','Comprador'],['tenant','Inquilino'],['interested','Interesado']].map(([k,l]) => (
                        <button key={k} type="button" className={`chip ${assignRelation===k?'active':''}`} aria-pressed={assignRelation===k} onClick={()=>setAssignRelation(k)}>{l}</button>
                      ))}
                    </div>
                    <div style={{maxHeight:160,overflowY:'auto',display:'flex',flexDirection:'column',gap:2}}>
                      {clients.filter(c => assignSearch ? c.name.toLowerCase().includes(assignSearch.toLowerCase()) : true).slice(0, 8).map(c => {
                        const linkClient = () => {
                          relateClient.mutate({ prop_id: property.id, client_id: c.id, relation: assignRelation, update_status: true }, {
                            onError: () => pushToast({ text: 'Error al vincular cliente. Verificá la conexión.', kind: 'danger' }),
                            onSuccess: () => pushToast({ text: 'Cliente vinculado correctamente.', kind: 'success' }),
                          });
                          setAssignOpen(false);
                          setAssignSearch('');
                        };
                        return (
                        <div key={c.id} className="popover-attendee" role="button" tabIndex={0} aria-label={`Vincular a ${c.name}`} style={{cursor:'pointer',padding:'6px 8px',borderRadius:6}}
                             onClick={linkClient}
                             onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); linkClient(); } }}>
                          <span className="av" aria-hidden="true">{initials(c.name)}</span>
                          <div style={{flex:1}}>
                            <div className="name" style={{fontSize:13,fontWeight:500}}>{c.name}</div>
                            <div className="meta">{c.phone || c.email}</div>
                          </div>
                          <Pill kind={c.role} />
                        </div>
                        );
                      })}
                      {clients.filter(c => assignSearch ? c.name.toLowerCase().includes(assignSearch.toLowerCase()) : true).length === 0 && (
                        <div className="muted" style={{fontSize:12,padding:8}}>Sin resultados.</div>
                      )}
                    </div>
                    <Button kind="ghost" size="sm" onClick={() => { setAssignOpen(false); setAssignSearch(''); }}>Cancelar</Button>
                  </div>
                );
              })()}
            </div>
          </div>

          <div className="detail-block">
            <h3>Visitas y actividad ({events.length + activity.length})</h3>
            <Timeline events={events} activity={activity} limit={12}
                      emptyText="Sin actividad registrada todavía." />
          </div>
        </div>
      </div>
    </Fragment>
  );
}

function ImageGallery({ images }) {
  const [idx, setIdx] = useState(0);
  const img = images[idx];
  if (!img) return null;
  const prev = () => setIdx(i => (i === 0 ? images.length - 1 : i - 1));
  const next = () => setIdx(i => (i === images.length - 1 ? 0 : i + 1));
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ position: 'relative', borderRadius: 8, overflow: 'hidden', aspectRatio: '4/3', background: 'var(--gray-100)', marginBottom: images.length > 1 ? 8 : 0 }}>
        {images.length > 1 && (
          <>
            <button type="button" aria-label="Foto anterior" onClick={prev}
              style={{ position:'absolute',left:8,top:'50%',transform:'translateY(-50%)',zIndex:2,
                       border:'none',background:'rgba(0,0,0,0.45)',color:'white',width:32,height:32,
                       borderRadius:'50%',cursor:'pointer',display:'flex',alignItems:'center',
                       justifyContent:'center',fontSize:16,lineHeight:1 }}>
              <span aria-hidden="true">‹</span>
            </button>
            <button type="button" aria-label="Siguiente foto" onClick={next}
              style={{ position:'absolute',right:8,top:'50%',transform:'translateY(-50%)',zIndex:2,
                       border:'none',background:'rgba(0,0,0,0.45)',color:'white',width:32,height:32,
                       borderRadius:'50%',cursor:'pointer',display:'flex',alignItems:'center',
                       justifyContent:'center',fontSize:16,lineHeight:1 }}>
              <span aria-hidden="true">›</span>
            </button>
          </>
        )}
        {isImg(img) ? (
          <img src={img} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        ) : (
          <div style={{ width: '100%', height: '100%', display:'flex',alignItems:'center',justifyContent:'center',color:'var(--fg-tertiary)',fontSize:13 }}>
            {img}
          </div>
        )}
        {images.length > 1 && (
          <div aria-live="polite" aria-atomic="true"
               style={{ position:'absolute',bottom:8,left:'50%',transform:'translateX(-50%)',
                        background:'rgba(0,0,0,0.55)',color:'white',fontSize:11,
                        padding:'2px 10px',borderRadius:10,whiteSpace:'nowrap' }}>
            Foto {idx + 1} de {images.length}
          </div>
        )}
      </div>
      {images.length > 1 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {images.map((url, i) => (
            <button key={i} type="button" aria-label={`Ver foto ${i + 1}${i === idx ? ' (actual)' : ''}`} aria-pressed={i === idx} onClick={() => setIdx(i)}
                 style={{ width: 56, height: 44, borderRadius: 6, overflow: 'hidden', cursor: 'pointer', padding: 0,
                          border: i === idx ? '2px solid var(--accent-500)' : '2px solid transparent',
                          opacity: i === idx ? 1 : 0.55, transition: 'opacity 0.15s',
                          background: 'var(--gray-100)' }}>
              {isImg(url) ? (
                <img src={url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <div style={{ width:'100%',height:'100%',display:'flex',alignItems:'center',justifyContent:'center',fontSize:10,color:'var(--fg-tertiary)' }} aria-hidden="true">📷</div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Compress an image File to JPEG, max 1200px on the longest side, quality 0.78.
 *  Returns a Promise<string> with the resulting data URL (~100-200 KB for typical photos). */
function compressImage(file, maxPx = 1200, quality = 0.78) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxPx / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale);
        const h = Math.round(img.height * scale);
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL('image/jpeg', quality));
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(file);
  });
}

function PhotoDropzone({ photos, onAdd, onRemove, onSetCover }) {
  const [drag, setDrag] = useState(false);
  const inputRef = React.useRef(null);

  const acceptFiles = (fileList) => {
    const files = Array.from(fileList || []).filter(f => f.type.startsWith('image/'));
    if (!files.length) return;
    Promise.all(files.map(f =>
      compressImage(f).then(url => ({
        id: 'ph_' + Math.random().toString(36).slice(2, 8),
        name: f.name.replace(/\.[^.]+$/, '.jpg'),
        size: Math.round(url.length * 0.75),   // approx bytes after compression
        url,
      }))
    )).then(items => onAdd(items));
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    acceptFiles(e.dataTransfer.files);
  };

  return (
    <div className="field">
      <label id="dropzone-label">Fotos de la propiedad</label>
      <div
        className={`dropzone ${drag ? 'drag' : ''} ${photos.length ? 'has-files' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current && inputRef.current.click()}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current && inputRef.current.click(); } }}
        role="button"
        tabIndex={0}
        aria-labelledby="dropzone-label"
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => { acceptFiles(e.target.files); e.target.value = ''; }}
        />
        <div className="dz-icon"><Icon name="upload" size={20} /></div>
        <div className="dz-title">Arrastrá las imágenes aquí</div>
        <div className="dz-hint">o <span className="dz-link">seleccioná desde tu equipo</span> · JPG, PNG, WebP · hasta 10 fotos</div>
      </div>

      {photos.length > 0 && (
        <div className="dz-grid">
          {photos.map((p, i) => (
            <div key={p.id} className={`dz-thumb ${i === 0 ? 'cover' : ''}`}>
              <img src={p.url} alt={p.name} />
              {i === 0 && <span className="dz-cover-tag">Portada</span>}
              <div className="dz-thumb-actions">
                {i !== 0 && (
                  <button type="button" className="dz-btn" title="Marcar como portada" aria-label="Marcar como portada"
                          onClick={(e) => { e.stopPropagation(); onSetCover(p.id); }}>
                    <Icon name="star" size={12} />
                  </button>
                )}
                <button type="button" className="dz-btn danger" title="Eliminar" aria-label="Eliminar foto"
                        onClick={(e) => { e.stopPropagation(); onRemove(p.id); }}>
                  <Icon name="trash" size={12} />
                </button>
              </div>
              <div className="dz-thumb-caption">{p.name}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatPriceDisplay(raw, currency) {
  if (!raw) return '';
  const n = parseInt(raw, 10);
  if (isNaN(n)) return '';
  return currency === 'USD' ? n.toLocaleString('en-US') : n.toLocaleString('es-AR');
}

function RefsInput({ refs, onChange }) {
  const [pending, setPending] = React.useState('');
  const addRef = () => {
    const val = pending.trim();
    if (!val || refs.includes(val)) { setPending(''); return; }
    onChange([...refs, val]);
    setPending('');
  };
  const removeRef = (item) => onChange(refs.filter(r => r !== item));
  const handleKey = (e) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addRef(); }
  };
  return (
    <div className="field">
      <label>Puntos de referencia</label>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: refs.length ? 6 : 0 }}>
        {refs.map(r => (
          <span key={r} style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
            background: 'var(--accent-50)', border: '1px solid var(--accent-100)',
            borderRadius: 12, padding: '2px 8px', fontSize: 13 }}>
            {r}
            <button type="button" title="Eliminar" onClick={() => removeRef(r)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                lineHeight: 1, color: 'var(--fg-tertiary)', fontSize: 14 }}>×</button>
          </span>
        ))}
      </div>
      <input
        placeholder="Ej: Hospital SAMIC, Terminal de ómnibus (Enter para agregar)"
        value={pending}
        onChange={e => setPending(e.target.value)}
        onKeyDown={handleKey}
        onBlur={addRef}
      />
    </div>
  );
}

function CityAutocomplete({ city, placeId, onChange }) {
  const [open, setOpen]       = useState(false);
  const [suggestions, setSug] = useState([]);
  const [active, setActive]   = useState(-1);
  const [loading, setLoading] = useState(false);
  // Coordenadas para el dropdown en position:fixed — escapa el overflow del
  // .modal-body (que antes lo recortaba y no dejaba ver/scrollear la lista).
  const [pos, setPos]         = useState(null);
  const boxRef      = React.useRef(null);
  const inputRef    = React.useRef(null);
  const debounceRef = React.useRef(null);
  const reqIdRef    = React.useRef(0);

  const computePos = React.useCallback(() => {
    const el = inputRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({ top: r.bottom + 2, left: r.left, width: r.width });
  }, []);

  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  // Mientras está abierto, reposiciona el dropdown fixed si el modal scrollea o
  // cambia el tamaño de la ventana (capture:true atrapa el scroll del modal-body).
  useEffect(() => {
    if (!open) return;
    computePos();
    const onMove = () => computePos();
    window.addEventListener('resize', onMove);
    window.addEventListener('scroll', onMove, true);
    return () => {
      window.removeEventListener('resize', onMove);
      window.removeEventListener('scroll', onMove, true);
    };
  }, [open, computePos]);

  const queryRemote = (text) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const q = (text || '').trim();
    if (q.length < 2) { setSug([]); setOpen(false); setLoading(false); return; }
    // Abre el dropdown ya con estado de carga: el backend puede tardar (cold
    // start de Render + ida a Google), así que la espera tiene que ser visible.
    setOpen(true);
    setLoading(true);
    setActive(-1);
    const reqId = ++reqIdRef.current;
    debounceRef.current = setTimeout(async () => {
      const res = await propertyApi.autocompleteCity(q);
      if (reqId !== reqIdRef.current) return;  // respuesta vieja (out-of-order) → ignorar
      setSug(res);
      setLoading(false);
    }, 250);
  };

  const handleInput = (e) => {
    const v = e.target.value;
    onChange(v, '');
    queryRemote(v);
  };

  const pick = (s) => {
    onChange(s.description, s.place_id);
    setOpen(false);
    setSug([]);
  };

  const handleKey = (e) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(i => Math.min(i + 1, suggestions.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(i => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter') { if (active >= 0) { e.preventDefault(); pick(suggestions[active]); } }
    else if (e.key === 'Escape') { setOpen(false); }
  };

  const dropdownStyle = {
    position: 'fixed',
    top: pos ? pos.top : 0, left: pos ? pos.left : 0, width: pos ? pos.width : 'auto',
    zIndex: 1000,
    margin: 0, padding: 0, listStyle: 'none', maxHeight: 240, overflowY: 'auto',
    background: 'var(--surface-float)', border: '1px solid var(--border-default)',
    borderRadius: 8, boxShadow: 'var(--shadow-lg)',
  };
  const hintStyle = { padding: '8px 10px', fontSize: 14, color: 'var(--fg-tertiary)' };

  return (
    <div className="field" ref={boxRef} style={{ position: 'relative' }}>
      <label>Ciudad</label>
      <input
        ref={inputRef}
        placeholder="Oberá"
        value={city}
        onChange={handleInput}
        onKeyDown={handleKey}
        onFocus={() => { if (suggestions.length || loading) setOpen(true); }}
        autoComplete="off"
      />
      {open && pos && (
        <ul style={dropdownStyle}>
          {loading && <li style={hintStyle}>Buscando…</li>}
          {!loading && suggestions.length === 0 && <li style={hintStyle}>Sin resultados</li>}
          {!loading && suggestions.map((s, i) => (
            <li key={s.place_id}
              onMouseDown={(e) => { e.preventDefault(); pick(s); }}
              onMouseEnter={() => setActive(i)}
              style={{
                padding: '8px 10px', cursor: 'pointer', fontSize: 14,
                background: i === active ? 'var(--accent-50)' : 'transparent',
              }}>
              {s.description}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Wizard de propiedad ──────────────────────────────────────────────────────

const PROP_STEPS = [
  { id: 'ubicacion',      label: 'Ubicación',      title: '¿Dónde está la propiedad?',          subtitle: 'Dirección completa y zona.' },
  { id: 'caracteristicas',label: 'Características', title: '¿Cómo es la propiedad?',             subtitle: 'Tipo, operación y características.' },
  { id: 'precio',         label: 'Precio',          title: '¿Cuál es el precio?',                subtitle: 'El bot filtra por presupuesto.' },
  { id: 'fotos',          label: 'Fotos',            title: 'Agregá fotos de la propiedad',       subtitle: 'La primera foto es la portada.' },
  { id: 'revision',       label: 'Revisión',         title: 'Revisá y guardá',                    subtitle: 'Vista previa antes de confirmar.' },
];

const PROP_STEP_HELP = {
  ubicacion: {
    heading: 'Sobre la dirección',
    tips: [
      'Incluí número de calle: "Av. San Martín 1250".',
      'El barrio/zona ayuda al bot a filtrar por sector.',
      'Los puntos de referencia mejoran la búsqueda: "frente al parque", "a 2 cuadras del hospital".',
    ],
    examples: ['Mitre 450, Oberá', 'Colón 1200 esq. Corrientes'],
  },
  caracteristicas: {
    heading: 'Tipo y operación',
    tips: [
      'Operación (alquiler/venta) define cómo ofrece el bot la propiedad.',
      'Estado "disponible" la muestra en las búsquedas activas.',
      'Completá m² y ambientes para que el bot pueda filtrar por tamaño.',
    ],
    examples: [],
  },
  precio: {
    heading: 'Precio de publicación',
    tips: [
      'Ingresá el precio en la moneda de publicación.',
      'El bot usa este valor para filtrar por presupuesto del cliente.',
      'Para alquileres, es el valor mensual.',
    ],
    examples: ['ARS 285.000 /mes', 'USD 85.000 venta'],
  },
  fotos: {
    heading: 'Tips para las fotos',
    tips: [
      'La primera foto es la portada de la propiedad.',
      'Podés reordenar: arrastrá o usá el ícono de estrella.',
      'JPG, PNG o WebP · hasta 10 fotos por propiedad.',
    ],
    examples: [],
  },
  revision: {
    heading: 'Antes de guardar',
    tips: [
      'Revisá dirección y precio: son los datos clave para el bot.',
      'Podés editar la propiedad en cualquier momento.',
      'La propiedad queda activa de inmediato una vez guardada.',
    ],
    examples: [],
  },
};

const PROP_STEP_MICROCOPY = [
  '¡Empezá por la ubicación!',
  '¿Cómo es la propiedad?',
  '¡Casi listo, el precio!',
  'Sumá las fotos',
  '¡Un último vistazo!',
];

function PropertyWizard({ onClose, onSave, mode = 'create', initialData = null }) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});

  const [form, setForm] = useState(() => {
    if (initialData) {
      return {
        addr:      initialData.addr      || '',
        neigh:     initialData.neigh     || '',
        city:      initialData.city      || '',
        type:      initialData.type      || 'Departamento',
        operation: initialData.operation || 'rent',
        status:    initialData.status    || 'available',
        rooms:      initialData.rooms      || '2 amb',
        ambientes:  initialData.ambientes  ?? 2,
        dormitorios: initialData.dormitorios ?? 1,
        m2:        initialData.m2        != null ? String(initialData.m2) : '',
        baths:     initialData.baths     ?? 1,
        parking:   initialData.parking   ?? 0,
        price:     initialData.price     != null ? String(initialData.price) : '',
        currency:  initialData.currency  || 'ARS',
        desc:      initialData.desc || initialData.notes || '',
        notes:     initialData.notes     || '',
        photos:    [],
        refs:      initialData.refs || [],
        place_id:  initialData.place_id || '',
      };
    }
    return {
      addr: '', neigh: '', city: '', type: 'Departamento', operation: 'rent', status: 'available',
      rooms: '2 amb', ambientes: 2, dormitorios: 1, m2: '', baths: 1, parking: 0,
      price: '', currency: 'ARS',
      desc: '', notes: '', photos: [], refs: [], place_id: '',
    };
  });

  const [priceDisplay, setPriceDisplay] = useState(() =>
    initialData?.price != null
      ? formatPriceDisplay(String(initialData.price), initialData.currency || 'ARS')
      : ''
  );

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const handlePriceChange = (e) => {
    const raw = e.target.value.replace(/\D/g, '');
    set('price', raw);
    setPriceDisplay(formatPriceDisplay(raw, form.currency));
  };

  const handleCurrencyChange = (e) => {
    const cur = e.target.value;
    set('currency', cur);
    setPriceDisplay(formatPriceDisplay(form.price, cur));
  };

  const addPhotos = (items) => setForm(f => ({ ...f, photos: [...f.photos, ...items].slice(0, 10) }));
  const removePhoto = (id) => setForm(f => ({ ...f, photos: f.photos.filter(p => p.id !== id) }));
  const setCover = (id) => setForm(f => {
    const target = f.photos.find(p => p.id === id);
    if (!target) return f;
    return { ...f, photos: [target, ...f.photos.filter(p => p.id !== id)] };
  });

  const trapRef = useFocusTrap(onClose);
  const totalSteps = PROP_STEPS.length;
  const pct = Math.round(((step + 1) / totalSteps) * 100);

  const validate = (upToStep) => {
    const errs = {};
    if (upToStep > 0 && !form.addr.trim()) errs.addr = 'La dirección es obligatoria.';
    if (upToStep > 2 && !form.price)       errs.price = 'El precio es obligatorio.';
    return errs;
  };

  const goNext = () => {
    const errs = validate(step + 1);
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setStep(s => Math.min(s + 1, totalSteps - 1));
  };

  const goBack = () => setStep(s => Math.max(s - 1, 0));

  const jumpTo = (i) => {
    const errs = validate(i);
    if (!Object.keys(errs).length || i < step) { setErrors({}); setStep(i); }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA' && step < totalSteps - 1) {
      e.preventDefault();
      goNext();
    }
  };

  const handleSave = async () => {
    const errs = validate(totalSteps);
    if (Object.keys(errs).length) { setErrors(errs); setStep(errs.addr ? 0 : 2); return; }
    setSaving(true);
    try {
      const imagesUrls = form.photos.map(p => p.url);
      const photo = imagesUrls[0] || (mode === 'edit' ? null : '');
      const allImages = imagesUrls.length > 0 ? imagesUrls : (mode === 'edit' ? null : []);
      await onSave({
        addr:      form.addr,
        neigh:     form.neigh,
        city:      form.city,
        type:      form.type,
        operation: form.operation,
        status:    form.status,
        rooms:     form.rooms,
        ambientes: form.ambientes,
        dormitorios: form.dormitorios,
        m2:        Number(form.m2) || 0,
        baths:     Number(form.baths) || 0,
        parking:   Number(form.parking) || 0,
        price:     Number(form.price) || 0,
        currency:  form.currency,
        notes:     form.desc || form.notes,
        photo,
        images:    allImages,
        refs:      form.refs,
        place_id:  form.place_id,
      });
    } finally {
      setSaving(false);
    }
  };

  const helpData = PROP_STEP_HELP[PROP_STEPS[step].id];

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div
        className="drawer prop-wizard"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prop-wizard-title"
        ref={trapRef}
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div className="drawer-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="prop-wizard-title" style={{ margin: 0, fontSize: 15 }}>
              {mode === 'edit' ? 'Editar propiedad' : 'Nueva propiedad'}
            </h2>
            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
              {PROP_STEPS[step].title}
            </div>
          </div>
          <IconButton name="x" title="Cerrar" onClick={onClose} />
        </div>

        {/* Progreso */}
        <div className="faq-progress-wrap">
          <div className="faq-step-dots" aria-label="Pasos del wizard">
            {PROP_STEPS.map((s, i) => (
              <button
                key={s.id}
                type="button"
                aria-current={i === step ? 'step' : undefined}
                aria-label={`Ir al paso ${i + 1}: ${s.label}`}
                className={`faq-step-dot${i < step ? ' done' : ''}${i === step ? ' current' : ''}`}
                onClick={() => jumpTo(i)}
              >
                {i < step ? <Icon name="check" size={11} /> : i + 1}
              </button>
            ))}
          </div>
          <div
            className="faq-progress-bar"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Progreso"
          >
            <div className="faq-progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="faq-progress-label">
            <span>{PROP_STEP_MICROCOPY[step]}</span>
            <span className="muted">{step + 1} / {totalSteps}</span>
          </div>
        </div>

        {/* Cuerpo: form + panel de ayuda */}
        <div className="faq-wizard-body">
          <div className="faq-wizard-form">

            {/* Paso 1: Ubicación */}
            {step === 0 && (
              <>
                <div className="field">
                  <label htmlFor="pw-addr">Dirección <span style={{ color: 'var(--danger-500)' }}>*</span></label>
                  <input
                    id="pw-addr"
                    placeholder="Av. San Martín 1250"
                    value={form.addr}
                    onChange={e => { set('addr', e.target.value); setErrors(prev => ({ ...prev, addr: undefined })); }}
                    className={errors.addr ? 'invalid' : ''}
                    autoFocus
                  />
                  {errors.addr && <span className="field-error">{errors.addr}</span>}
                </div>
                <div className="field-row">
                  <div className="field">
                    <label htmlFor="pw-neigh">Barrio / zona</label>
                    <input id="pw-neigh" placeholder="Centro, Norte..." value={form.neigh} onChange={e => set('neigh', e.target.value)} />
                  </div>
                  <CityAutocomplete
                    city={form.city}
                    placeId={form.place_id}
                    onChange={(city, placeId) => setForm(f => ({ ...f, city, place_id: placeId }))}
                  />
                </div>
                <RefsInput refs={form.refs} onChange={v => set('refs', v)} />
              </>
            )}

            {/* Paso 2: Características */}
            {step === 1 && (
              <>
                <div className="field-row">
                  <div className="field">
                    <label htmlFor="pw-type">Tipo</label>
                    <select id="pw-type" value={form.type} onChange={e => set('type', e.target.value)} autoFocus>
                      <option>Departamento</option>
                      <option>Casa</option>
                      <option>PH</option>
                      <option>Local</option>
                      <option>Oficina</option>
                      <option>Terreno</option>
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="pw-op">Operación</label>
                    <select id="pw-op" value={form.operation} onChange={e => set('operation', e.target.value)}>
                      <option value="rent">Alquiler</option>
                      <option value="sale">Venta</option>
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="pw-status">Estado</label>
                    <select id="pw-status" value={form.status} onChange={e => set('status', e.target.value)}>
                      <option value="available">Disponible</option>
                      <option value="reserved">Reservada</option>
                      <option value="rented">Alquilada</option>
                      <option value="sale">En venta</option>
                    </select>
                  </div>
                </div>
                <div className="prop-attrs-grid">
                  <div className="field">
                    <label htmlFor="pw-rooms">Ambientes</label>
                    <select id="pw-rooms" value={form.rooms} onChange={e => {
                      const val = e.target.value;
                      const amb = parseInt(val) || 0;
                      set('rooms', val);
                      set('ambientes', amb || null);
                      set('dormitorios', amb <= 1 ? 0 : amb - 1);
                    }}>
                      <option value="—">—</option>
                      <option>1 amb</option>
                      <option>2 amb</option>
                      <option>3 amb</option>
                      <option>4 amb</option>
                      <option>5+ amb</option>
                    </select>
                  </div>
                  {form.rooms !== '—' && form.ambientes !== 1 && (
                    <div className="field">
                      <label htmlFor="pw-dorms">Dormitorios</label>
                      <input id="pw-dorms" type="number" min="0" value={form.dormitorios} onChange={e => set('dormitorios', Number(e.target.value))} style={{ textAlign: 'center' }} />
                    </div>
                  )}
                  <div className="field">
                    <label htmlFor="pw-baths">Baños</label>
                    <input id="pw-baths" type="number" min="0" value={form.baths} onChange={e => set('baths', e.target.value)} style={{ textAlign: 'center' }} />
                  </div>
                  <div className="field">
                    <label htmlFor="pw-parking">Cocheras</label>
                    <input id="pw-parking" type="number" min="0" value={form.parking} onChange={e => set('parking', e.target.value)} style={{ textAlign: 'center' }} />
                  </div>
                  <div className="field">
                    <label htmlFor="pw-m2">Superficie (m²)</label>
                    <input id="pw-m2" type="number" min="1" placeholder="58" value={form.m2} onChange={e => set('m2', e.target.value)} />
                  </div>
                </div>
              </>
            )}

            {/* Paso 3: Precio */}
            {step === 2 && (
              <>
                <div className="field-row">
                  <div className="field">
                    <label htmlFor="pw-price">Precio <span style={{ color: 'var(--danger-500)' }}>*</span></label>
                    <input
                      id="pw-price"
                      type="text"
                      inputMode="numeric"
                      placeholder={form.currency === 'USD' ? '85,000' : '285.000'}
                      value={priceDisplay}
                      onChange={handlePriceChange}
                      className={errors.price ? 'invalid' : ''}
                      autoFocus
                    />
                    {errors.price && <span className="field-error">{errors.price}</span>}
                  </div>
                  <div className="field">
                    <label htmlFor="pw-currency">Moneda</label>
                    <select id="pw-currency" value={form.currency} onChange={handleCurrencyChange}>
                      <option value="ARS">ARS — pesos</option>
                      <option value="USD">USD — dólares</option>
                    </select>
                  </div>
                </div>
                <div className="field-row">
                  <div className="field">
                    <label>Código interno</label>
                    <input placeholder="Se genera automáticamente" disabled />
                  </div>
                </div>
              </>
            )}

            {/* Paso 4: Fotos */}
            {step === 3 && (
              <PhotoDropzone
                photos={form.photos}
                onAdd={addPhotos}
                onRemove={removePhoto}
                onSetCover={setCover}
              />
            )}

            {/* Paso 5: Revisión */}
            {step === 4 && (
              <>
                <div className="field">
                  <label htmlFor="pw-desc">Descripción</label>
                  <textarea
                    id="pw-desc"
                    placeholder="Descripción para mostrar a los clientes, ej: 'Departamento luminoso con balcón...'"
                    value={form.desc}
                    onChange={e => set('desc', e.target.value)}
                    rows={3}
                    style={{ resize: 'vertical', width: '100%' }}
                    autoFocus
                  />
                </div>
                <div className="field">
                  <label htmlFor="pw-notes">Notas internas</label>
                  <textarea
                    id="pw-notes"
                    placeholder="Detalles internos para el equipo"
                    value={form.notes}
                    onChange={e => set('notes', e.target.value)}
                    rows={2}
                    style={{ resize: 'vertical', width: '100%' }}
                  />
                </div>
                {/* Preview ficha */}
                <div className="prop-wizard-preview">
                  <div className="prop-wizard-preview-label">Vista previa</div>
                  <div className="prop-wizard-preview-card">
                    {form.photos.length > 0 && (
                      <img
                        src={form.photos[0].url}
                        alt="Portada"
                        className="prop-wizard-preview-img"
                      />
                    )}
                    <div className="prop-wizard-preview-body">
                      <div className="prop-wizard-preview-addr">{form.addr || '—'}</div>
                      <div className="prop-wizard-preview-meta">
                        {form.neigh && <span>{form.neigh} · </span>}
                        {form.type} · {form.rooms !== '—' ? form.rooms + ' · ' : ''}{form.m2 ? form.m2 + ' m²' : ''}
                      </div>
                      <div className="prop-wizard-preview-price">
                        {form.price
                          ? (form.currency === 'USD' ? 'USD ' : 'ARS ') + priceDisplay
                          : <span style={{ color: 'var(--danger-400)' }}>Sin precio</span>}
                        {form.operation === 'rent' && <span className="muted"> /mes</span>}
                      </div>
                      {form.desc && (
                        <div className="prop-wizard-preview-desc">{form.desc.slice(0, 120)}{form.desc.length > 120 ? '…' : ''}</div>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Panel lateral de ayuda */}
          <aside className="faq-help-panel" aria-label="Consejos">
            <div className="faq-help-heading">
              <Icon name="info" size={13} style={{ color: 'var(--accent-500)', flexShrink: 0 }} />
              {helpData.heading}
            </div>
            <ul className="faq-help-tips">
              {helpData.tips.map((tip, i) => <li key={i}>{tip}</li>)}
            </ul>
            {helpData.examples.length > 0 && (
              <>
                <div className="faq-help-examples-label">Ejemplos</div>
                {helpData.examples.map((ex, i) => (
                  <div key={i} className="faq-help-example">&ldquo;{ex}&rdquo;</div>
                ))}
              </>
            )}
          </aside>
        </div>

        {/* Footer */}
        <div className="faq-wizard-footer">
          <Button kind="secondary" size="sm" onClick={step === 0 ? onClose : goBack}>
            {step === 0 ? 'Cancelar' : 'Atrás'}
          </Button>
          {step < totalSteps - 1 ? (
            <Button kind="primary" size="sm" onClick={goNext} icon="arrowRight">
              Siguiente
            </Button>
          ) : (
            <Button kind="primary" size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Guardando…' : mode === 'edit' ? 'Guardar cambios' : 'Crear propiedad'}
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

// ─── Estado vacío de propiedades (0 propiedades) ──────────────────────────────

function PropertiesEmptyState({ onNew, onImport }) {
  return (
    <div className="faq-empty">
      <div className="faq-empty-icon">
        <Icon name="building" size={36} style={{ color: 'var(--accent-400)' }} />
      </div>
      <h3 className="faq-empty-title">Todavía no tenés propiedades cargadas</h3>
      <p className="faq-empty-sub">
        Cargá tu primera propiedad y el bot podrá mostrarla a tus clientes, filtrar por presupuesto y agendar visitas.
      </p>
      <div className="faq-empty-actions">
        <Button kind="primary" icon="plus" onClick={onNew}>Cargar mi primera propiedad</Button>
        <Button kind="secondary" icon="upload" onClick={onImport}>Mandanos tu listado y las subimos por vos</Button>
      </div>
    </div>
  );
}

const IMPORT_STATUS_LABEL = {
  received:    { label: 'Recibido',    color: 'var(--accent-600)' },
  in_progress: { label: 'En proceso',  color: 'var(--warning-700)' },
  completed:   { label: 'Cargadas',    color: 'var(--state-success-fg)' },
  cancelled:   { label: 'Cancelado',   color: 'var(--fg-muted)' },
};

const ALLOWED_IMPORT_TYPES = [
  'application/pdf',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/csv',
  'text/plain',
  'image/jpeg',
  'image/png',
  'image/webp',
];

const MAX_IMPORT_FILE_MB = 5;
const MAX_IMPORT_FILES = 10;

function ImportModal({ onClose }) {
  const [files, setFiles] = useState([]);
  const [note, setNote] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);
  const trapRef = useFocusTrap();
  const createImport = useCreatePropertyImport();

  const addFiles = (incoming) => {
    const valid = [...incoming].filter(f => {
      if (!ALLOWED_IMPORT_TYPES.includes(f.type)) {
        pushToast({ text: `Tipo no permitido: ${f.name}`, kind: 'warning' });
        return false;
      }
      if (f.size > MAX_IMPORT_FILE_MB * 1024 * 1024) {
        pushToast({ text: `${f.name} supera 5 MB`, kind: 'warning' });
        return false;
      }
      return true;
    });
    setFiles(prev => {
      const next = [...prev, ...valid].slice(0, MAX_IMPORT_FILES);
      if (prev.length + valid.length > MAX_IMPORT_FILES) {
        pushToast({ text: `Máximo ${MAX_IMPORT_FILES} archivos por pedido`, kind: 'warning' });
      }
      return next;
    });
  };

  const removeFile = (idx) => setFiles(prev => prev.filter((_, i) => i !== idx));

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  };

  const handleSubmit = async () => {
    const filePayloads = await Promise.all(
      files.map(f => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({
          filename: f.name,
          content_type: f.type || 'application/octet-stream',
          data: reader.result.split(',')[1],
        });
        reader.onerror = reject;
        reader.readAsDataURL(f);
      }))
    );
    createImport.mutate(
      { note: note.trim() || null, files: filePayloads },
      {
        onSuccess: () => {
          pushToast({ text: '¡Pedido enviado! Te avisamos cuando esté cargado.' });
          onClose();
        },
        onError: () => pushToast({ text: 'Error al enviar el pedido.', kind: 'danger' }),
      }
    );
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="import-modal-title"
         onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box" ref={trapRef} style={{ maxWidth: 520 }}>
        <div className="modal-header">
          <h2 id="import-modal-title" style={{ margin: 0, fontSize: 16 }}>Mandanos tu listado de propiedades</h2>
          <IconButton icon="x" aria-label="Cerrar" onClick={onClose} />
        </div>
        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <p style={{ margin: 0, color: 'var(--fg-secondary)', fontSize: 14 }}>
            Subí tus propiedades en el formato que tengas (planilla, PDF, Word, fotos) y las cargamos por vos.
            Te avisamos por email cuando estén listas.
          </p>
          <div
            className={`prop-import-dropzone${dragOver ? ' drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Área para subir archivos de propiedades"
            onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && fileRef.current?.click()}
          >
            <Icon name="upload" size={24} style={{ color: 'var(--accent-400)', marginBottom: 8 }} />
            <span style={{ fontSize: 14, color: 'var(--fg-secondary)' }}>
              Arrastrá archivos acá o <strong>hacé clic</strong>
            </span>
            <span style={{ fontSize: 12, color: 'var(--fg-muted)', marginTop: 4 }}>
              Excel, CSV, PDF, Word, imágenes · hasta 5 MB por archivo · máx. {MAX_IMPORT_FILES} archivos
            </span>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept={ALLOWED_IMPORT_TYPES.join(',')}
              style={{ display: 'none' }}
              onChange={e => addFiles(e.target.files)}
            />
          </div>
          {files.length > 0 && (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {files.map((f, i) => (
                <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '6px 10px', background: 'var(--surface-base)', borderRadius: 8, border: '1px solid var(--border-subtle)' }}>
                  <Icon name="file" size={14} style={{ color: 'var(--fg-muted)', flexShrink: 0 }} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                  <span style={{ color: 'var(--fg-muted)', fontSize: 11 }}>{(f.size / 1024).toFixed(0)} KB</span>
                  <IconButton icon="x" size={12} aria-label={`Quitar ${f.name}`} onClick={() => removeFile(i)} />
                </li>
              ))}
            </ul>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label htmlFor="import-note" style={{ fontSize: 13, fontWeight: 600 }}>Contexto / nota (opcional)</label>
            <textarea
              id="import-note"
              rows={3}
              placeholder="¿Cuántas propiedades son aprox.? ¿Algo que debamos saber?"
              value={note}
              onChange={e => setNote(e.target.value)}
              maxLength={4000}
              style={{ resize: 'vertical', fontSize: 14, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-subtle)', background: 'var(--surface-base)', color: 'var(--fg-primary)' }}
            />
          </div>
        </div>
        <div className="modal-footer">
          <Button kind="secondary" onClick={onClose}>Cancelar</Button>
          <Button
            kind="primary"
            icon="send"
            onClick={handleSubmit}
            disabled={files.length === 0 || createImport.isPending}
          >
            {createImport.isPending ? 'Enviando…' : 'Enviar listado'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ImportStatusPanel() {
  const { data, isLoading } = useMyPropertyImports();
  const items = data?.items ?? [];
  if (isLoading || items.length === 0) return null;

  return (
    <div className="prop-import-status-panel">
      <div className="prop-import-status-title">
        <Icon name="inbox" size={14} />
        Mis importaciones
      </div>
      <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map(req => {
          const meta = IMPORT_STATUS_LABEL[req.status] || IMPORT_STATUS_LABEL.received;
          return (
            <li key={req.id} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
              <span style={{ flex: 1, color: 'var(--fg-secondary)' }}>
                {new Date(req.created_at).toLocaleDateString('es-AR')}
                {req.file_count > 0 && ` · ${req.file_count} archivo${req.file_count > 1 ? 's' : ''}`}
              </span>
              <span style={{ fontWeight: 700, color: meta.color }}>{meta.label}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function Properties({ onOpenClient, initialProperty }) {
  const { data: properties = [] } = useProperties();
  const createProperty  = useCreateProperty();
  const updateProperty  = useUpdateProperty();
  const deleteProperty  = useDeleteProperty();
  const updateStatus    = useUpdatePropertyStatus();
  const [filter, setFilter] = useState('all');
  const [op, setOp] = useState('all');
  const [search, setSearch] = useState('');
  const [view, setView] = useState(() => {
    const stored = localStorage.getItem('propView');
    return stored === 'list' || stored === 'grid' ? stored : 'grid';
  });
  const [open, setOpen] = useState(initialProperty || null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [showImportModal, setShowImportModal] = useState(false);

  // Persistir la vista elegida para recordarla al volver a la pestaña
  useEffect(() => {
    localStorage.setItem('propView', view);
  }, [view]);

  const handleDelete = (property) => {
    // Close immediately — the optimistic update removes the card on the spot and
    // rolls back (with an error toast) if the request fails.
    setDeleteTarget(null);
    setOpen(null);
    pushToast({ text: `Propiedad eliminada — ${property.addr}.`, kind: 'danger' });
    deleteProperty.mutate(property.id, {
      onError: () => pushToast({ text: 'Error al eliminar la propiedad. Se restauró en la lista.', kind: 'danger' }),
    });
  };

  const filtered = properties.filter(p => {
    if (filter !== 'all' && p.status !== filter) return false;
    if (op !== 'all' && p.operation !== op) return false;
    if (search && !(p.addr.toLowerCase().includes(search.toLowerCase()) || p.neigh.toLowerCase().includes(search.toLowerCase()))) return false;
    return true;
  });

  const counts = {
    all: properties.length,
    available: properties.filter(p=>p.status==='available').length,
    rented: properties.filter(p=>p.status==='rented').length,
    sale: properties.filter(p=>p.status==='sale').length,
    reserved: properties.filter(p=>p.status==='reserved').length,
    sold: properties.filter(p=>p.status==='sold').length,
  };

  const isEmpty = properties.length === 0;

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Propiedades</h1>
          <div className="sub">{properties.length} en cartera · {counts.available} disponibles · {counts.rented} alquiladas · {counts.sold} vendidas</div>
        </div>
        {!isEmpty && (
          <div className="page-h-actions">
            <Button kind="secondary" icon="download">Exportar</Button>
            <Button kind="ghost" icon="upload" onClick={() => setShowImportModal(true)}>Importar listado</Button>
            <Button kind="primary" icon="plus" onClick={() => setCreating(true)}>Agregar propiedad</Button>
          </div>
        )}
      </div>
      <div className="scroll-surface surface">
        {isEmpty ? (
          <PropertiesEmptyState onNew={() => setCreating(true)} onImport={() => setShowImportModal(true)} />
        ) : null}
        {!isEmpty && <ImportStatusPanel />}
        {!isEmpty && (<><div className="filter-bar">
          <input placeholder="Buscar por dirección, barrio..." value={search} onChange={e => setSearch(e.target.value)} />
          {[['all','Todas',counts.all],['available','Disponibles',counts.available],['rented','Alquiladas',counts.rented],['sale','En venta',counts.sale],['reserved','Reservadas',counts.reserved],['sold','Vendidas',counts.sold]].map(([k,l,n]) => (
            <button key={k} type="button" className={`chip ${filter===k?'active':''}`} aria-pressed={filter===k} onClick={()=>setFilter(k)}>{l}<span className="num">{n}</span></button>
          ))}
          <span style={{flex:1}}></span>
          <select value={op} onChange={e=>setOp(e.target.value)}>
            <option value="all">Todas las operaciones</option>
            <option value="rent">Alquiler</option>
            <option value="sale">Venta</option>
          </select>
          <div className="views" role="group" aria-label="Tipo de vista">
            <button type="button" aria-label="Vista de lista" aria-pressed={view==='list'} className={view==='list'?'active':''} onClick={()=>setView('list')}><Icon name="list" size={13} /></button>
            <button type="button" aria-label="Vista de grilla" aria-pressed={view==='grid'} className={view==='grid'?'active':''} onClick={()=>setView('grid')}><Icon name="grid" size={13} /></button>
          </div>
        </div>
        <div className="tbl-scroll">
          {view === 'list' ? (
            <table className="tbl props-tbl">
              <thead><tr>
                <th>Propiedad</th>
                <th className="props-col-tipo">Tipo</th>
                <th>Estado</th>
                <th className="props-col-op">Operación</th>
                <th style={{textAlign:'right'}}>Precio</th>
                <th></th>
              </tr></thead>
              <tbody>
                {filtered.map(p => (
                  <tr key={p.id} tabIndex={0} aria-label={`Ver propiedad ${p.addr}`}
                      onClick={() => setOpen(p)}
                      onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setOpen(p); } }}>
                    <td>
                      <div style={{display:'flex',alignItems:'center',gap:10}}>
                        <span className="prop-thumb" style={{overflow:'hidden',padding:0}}>
                          <PropertyImage
                            src={p.photo}
                            alt=""
                            radius={5}
                            aspect={null}
                            fallback={<Icon name="building" />}
                          />
                        </span>
                        <div className="addr-block">
                          <div className="a1">{p.addr}</div>
                          <div className="a2">{p.neigh} · {p.rooms !== '—' && p.rooms + ' · '}{p.m2} m²</div>
                        </div>
                      </div>
                    </td>
                    <td className="muted props-col-tipo">{p.type}</td>
                    <td><StatusDropdown kind={p.status} onSelect={(s) => updateStatus.mutate({ id: p.id, status: s })} /></td>
                    <td className="muted props-col-op">{p.operation === 'rent' ? 'Alquiler' : 'Venta'}</td>
                    <td className="price" style={{textAlign:'right',whiteSpace:'nowrap'}}>
                      {fmtCurrency(p.price, p.currency)}
                      {p.operation === 'rent' && p.status !== 'sale' && <span className="muted" style={{fontWeight:400}}> /mes</span>}
                    </td>
                    <td><div className="row-actions" onClick={e => e.stopPropagation()}>
                      <IconButton name="edit" aria-label="Editar propiedad" onClick={() => setEditing(p)} />
                      <IconButton name="trash" aria-label="Eliminar propiedad" onClick={() => setDeleteTarget(p)} />
                    </div></td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="7" className="tbl-empty">No hay propiedades que coincidan con los filtros.</td></tr>}
              </tbody>
            </table>
          ) : (
            <div className="prop-grid">
              {filtered.map(p => (
                <div key={p.id} className="prop-card" tabIndex={0} aria-label={`Ver propiedad ${p.addr}`}
                     onClick={() => setOpen(p)}
                     onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); setOpen(p); } }}>
                  <div className="prop-card-media">
                    <PropertyImage
                      src={p.photo}
                      alt={p.addr}
                      radius="10px 10px 0 0"
                      fallback={<div className="prop-photo-fallback">{p.type}</div>}
                    />
                    <StatusDropdown kind={p.status} overlay onSelect={(s) => updateStatus.mutate({ id: p.id, status: s })} />
                  </div>
                  <div className="prop-card-body">
                    <div className="prop-card-addr">{p.addr}</div>
                    <div className="prop-card-meta">{p.neigh}</div>
                    <div className="prop-card-meta">{p.rooms !== '—' && p.rooms + ' · '}{p.m2} m² · {p.baths} baño{p.baths!==1?'s':''}</div>
                    <div className="prop-card-price tabular">
                      {fmtCurrency(p.price, p.currency)}
                      <span className="cur">{p.currency}</span>
                      {p.operation==='rent' && p.status !== 'sale' && <span className="per">/mes</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </>)}
      </div>
      {open && (
        <PropertyDrawer
          property={open}
          onClose={() => setOpen(null)}
          onOpenClient={onOpenClient}
          onAgenda={() => { setOpen(null); pushToast({text:'Visita: completá los datos en el calendario.'}); }}
          onEdit={(p) => { setOpen(null); setEditing(p); }}
          onDelete={(p) => { setOpen(null); setDeleteTarget(p); }}
        />
      )}
      {deleteTarget && (
        <div className="modal-backdrop" onClick={() => setDeleteTarget(null)} aria-hidden="true">
          <div className="modal" style={{maxWidth:420}} role="dialog" aria-modal="true" aria-labelledby="delete-prop-title" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h3 id="delete-prop-title">Eliminar propiedad</h3>
            </div>
            <div className="modal-body">
              <p style={{fontSize:14,color:'var(--fg-secondary)',margin:0}}>
                ¿Estás seguro de que querés eliminar <b>{deleteTarget.addr}</b>?
                Esta acción no se puede deshacer y borrará la propiedad de la base de datos.
              </p>
            </div>
            <div className="modal-foot">
              <Button kind="ghost" size="sm" onClick={() => setDeleteTarget(null)}>Cancelar</Button>
              <Button kind="danger" size="sm" icon="trash"
                onClick={() => handleDelete(deleteTarget)}>
                Sí, eliminar
              </Button>
            </div>
          </div>
        </div>
      )}
      {creating && (
        <PropertyWizard
          onClose={() => setCreating(false)}
          onSave={(data) => new Promise((resolve, reject) => {
            createProperty.mutate(data, {
              onSuccess: () => { pushToast({ text: 'Propiedad creada.' }); setCreating(false); resolve(); },
              onError: (e) => { pushToast({ text: 'Error al crear la propiedad.', kind: 'danger' }); reject(e); },
            });
          })}
        />
      )}
      {editing && (
        <PropertyWizard
          mode="edit"
          initialData={editing}
          onClose={() => setEditing(null)}
          onSave={(data) => new Promise((resolve, reject) => {
            updateProperty.mutate({ id: editing.id, ...data }, {
              onSuccess: () => { pushToast({ text: 'Propiedad actualizada.' }); setEditing(null); resolve(); },
              onError: (e) => { pushToast({ text: 'Error al guardar los cambios.', kind: 'danger' }); reject(e); },
            });
          })}
        />
      )}
      {showImportModal && <ImportModal onClose={() => setShowImportModal(false)} />}
    </div>
  );
}

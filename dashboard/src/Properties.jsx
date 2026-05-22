import React, { useState, Fragment } from 'react';
import { Icon, Button, IconButton, Pill, StatusDropdown, initials, pushToast } from './Primitives';
import { fmtCurrency, fmtTime12 } from './data';
import { useProperties, useClients, useEvents, useCreateProperty, useUpdateProperty, useDeleteProperty, useUpdatePropertyStatus, useRelateClientToProperty } from './api';
import { KIND_META } from './EventPopover';

/** Devuelve true si el string es una URL de imagen (base64 o http) */
const isImg = (s) => s && (
  s.startsWith('data:') ||
  s.startsWith('http') ||
  s.startsWith('/') ||
  // Raw base64: long string of base64 chars (no spaces/newlines)
  (s.length > 50 && /^[A-Za-z0-9+/=]+$/.test(s.slice(0, 100)))
);

function PropertyDrawer({ property, onClose, onOpenClient, onAgenda, onEdit, onDelete }) {
  const { data: clients = [] }   = useClients();
  const { data: properties = [] } = useProperties();
  const { data: allEvents = [] } = useEvents();
  const updateStatus     = useUpdatePropertyStatus();
  const relateClient     = useRelateClientToProperty();
  // Use fresh data from the cache so drawer reflects mutation updates immediately
  const freshProperty = properties.find(p => String(p.id) === String(property.id)) || property;
  property = freshProperty;
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignSearch, setAssignSearch] = useState('');
  const [assignRelation, setAssignRelation] = useState(freshProperty.operation === 'rent' ? 'tenant' : 'buyer');
  const [linkEditOpen, setLinkEditOpen] = useState(null);
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
  const events = allEvents.filter(e => String(e.propId) === String(property.id));
  /** true si la propiedad es para alquiler (muestra /mes en precio) */
  const isRent = property.operation === 'rent' && property.status !== 'sale';
  return (
    <Fragment>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer wide">
        <div className="drawer-head">
          <div>
            <h2>{property.addr}</h2>
            <div className="sub">{property.neigh} · {property.type} · {property.rooms !== '—' && property.rooms + ' · '}{property.m2} m²</div>
          </div>
          <span className="close"><IconButton name="x" onClick={onClose} /></span>
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
              <dt>Agente</dt><dd>{property.agent}</dd>
              <dt>Código interno</dt><dd className="tabular">IB-{property.id.toUpperCase()}</dd>
            </dl>
          </div>

          <div className="detail-block">
            <h3>Clientes interesados ({interestedClients.length})</h3>
            {interestedClients.length === 0 ? (
              <div className="muted" style={{fontSize:12}}>Sin clientes asignados todavía.</div>
            ) : interestedClients.map(c => (
              <div key={c.id} className="popover-attendee" style={{padding:'8px 0',borderBottom:'1px solid var(--border-subtle)',cursor:'pointer'}} onClick={() => onOpenClient && onOpenClient(c)}>
                <span className="av">{initials(c.name)}</span>
                <div style={{flex:1}}>
                  <div className="name" style={{fontSize:13,fontWeight:500}}>{c.name}</div>
                  <div className="meta">{c.tags.join(' · ')}</div>
                </div>
                <Pill kind={c.role} />
              </div>
            ))}
          </div>

          <div className="detail-block">
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
                            <div style={{position:'absolute',top:'100%',right:0,minWidth:160,background:'white',border:'1px solid var(--border-default)',borderRadius:8,boxShadow:'var(--shadow-md)',zIndex:10,padding:4}}>
                              <div className="status-dropdown-item" onClick={() => { setLinkEditOpen(null); relateClient.mutate({ prop_id: property.id, client_id: linked.id, relation: isBuyer ? 'tenant' : 'buyer', update_status: true }, { onSuccess: () => pushToast({ text: 'Relación actualizada.', kind: 'success' }), onError: () => pushToast({ text: 'Error al actualizar.', kind: 'danger' }) }); }}>
                                Cambiar a {isBuyer ? 'Inquilino' : 'Comprador'}
                              </div>
                              <div className="status-dropdown-item" onClick={() => { setLinkEditOpen(null); relateClient.mutate({ prop_id: property.id, client_id: linked.id, relation: 'interested', update_status: false }, { onSuccess: () => pushToast({ text: 'Cliente movido a interesados.', kind: 'success' }), onError: () => pushToast({ text: 'Error al actualizar.', kind: 'danger' }) }); }}>
                                Cambiar a Interesado
                              </div>
                              <div style={{borderTop:'1px solid var(--border-subtle)',margin:'4px 0'}} />
                              <div className="status-dropdown-item" style={{color:'var(--danger-500)'}} onClick={() => { setLinkEditOpen(null); relateClient.mutate({ prop_id: property.id, client_id: linked.id, relation: 'none' }, { onSuccess: () => pushToast({ text: 'Cliente desvinculado.', kind: 'success' }), onError: () => pushToast({ text: 'Error al desvincular.', kind: 'danger' }) }); }}>
                                Desvincular
                              </div>
                            </div>
                          ) : null}
                          <IconButton name={linkEditOpen === (isBuyer ? 'buyer' : 'tenant') ? 'x' : 'edit'} onClick={() => setLinkEditOpen(linkEditOpen === (isBuyer ? 'buyer' : 'tenant') ? null : (isBuyer ? 'buyer' : 'tenant'))} />
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
                        <span key={k} className={`chip ${assignRelation===k?'active':''}`} onClick={()=>setAssignRelation(k)}>{l}</span>
                      ))}
                    </div>
                    <div style={{maxHeight:160,overflowY:'auto',display:'flex',flexDirection:'column',gap:2}}>
                      {clients.filter(c => assignSearch ? c.name.toLowerCase().includes(assignSearch.toLowerCase()) : true).slice(0, 8).map(c => (
                        <div key={c.id} className="popover-attendee" style={{cursor:'pointer',padding:'6px 8px',borderRadius:6}}
                             onClick={() => {
                               relateClient.mutate({ prop_id: property.id, client_id: c.id, relation: assignRelation, update_status: true }, {
                                 onError: () => pushToast({ text: 'Error al vincular cliente. Verificá la conexión.', kind: 'danger' }),
                                 onSuccess: () => pushToast({ text: 'Cliente vinculado correctamente.', kind: 'success' }),
                               });
                               setAssignOpen(false);
                               setAssignSearch('');
                             }}>
                          <span className="av">{initials(c.name)}</span>
                          <div style={{flex:1}}>
                            <div className="name" style={{fontSize:13,fontWeight:500}}>{c.name}</div>
                            <div className="meta">{c.phone || c.email}</div>
                          </div>
                          <Pill kind={c.role} />
                        </div>
                      ))}
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
            <h3>Visitas y actividad ({events.length})</h3>
            {events.length === 0 ? (
              <div className="muted" style={{fontSize:12}}>Sin eventos programados.</div>
            ) : events.slice(0,5).map(e => {
              const c = clients.find(x => x.id === e.clientId);
              return (
                <div key={e.id} style={{display:'flex',gap:10,padding:'8px 0',borderBottom:'1px solid var(--border-subtle)',fontSize:13,alignItems:'center'}}>
                  <span style={{width:6,height:6,borderRadius:'50%',background:KIND_META[e.kind].color,flexShrink:0}}></span>
                  <span className="tabular muted" style={{minWidth:78}}>{e.date.slice(8)}/{e.date.slice(5,7)} {fmtTime12(e.start)}</span>
                  <span style={{flex:1}}>{c ? c.name : e.title}</span>
                  {e.status === 'cancelled' ? <Pill kind="cancelled">Cancelada</Pill> : e.status === 'pending' ? <Pill kind="pending">Por confirmar</Pill> : <Pill kind="paid">Confirmada</Pill>}
                </div>
              );
            })}
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
            <button onClick={prev}
              style={{ position:'absolute',left:8,top:'50%',transform:'translateY(-50%)',zIndex:2,
                       border:'none',background:'rgba(0,0,0,0.45)',color:'white',width:32,height:32,
                       borderRadius:'50%',cursor:'pointer',display:'flex',alignItems:'center',
                       justifyContent:'center',fontSize:16,lineHeight:1 }}>
              ‹
            </button>
            <button onClick={next}
              style={{ position:'absolute',right:8,top:'50%',transform:'translateY(-50%)',zIndex:2,
                       border:'none',background:'rgba(0,0,0,0.45)',color:'white',width:32,height:32,
                       borderRadius:'50%',cursor:'pointer',display:'flex',alignItems:'center',
                       justifyContent:'center',fontSize:16,lineHeight:1 }}>
              ›
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
          <div style={{ position:'absolute',bottom:8,left:'50%',transform:'translateX(-50%)',
                        background:'rgba(0,0,0,0.55)',color:'white',fontSize:11,
                        padding:'2px 10px',borderRadius:10,whiteSpace:'nowrap' }}>
            {idx + 1} / {images.length}
          </div>
        )}
      </div>
      {images.length > 1 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {images.map((url, i) => (
            <div key={i} onClick={() => setIdx(i)}
                 style={{ width: 56, height: 44, borderRadius: 6, overflow: 'hidden', cursor: 'pointer',
                          border: i === idx ? '2px solid var(--primary-500)' : '2px solid transparent',
                          opacity: i === idx ? 1 : 0.55, transition: 'all 0.15s',
                          background: 'var(--gray-100)' }}>
              {isImg(url) ? (
                <img src={url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <div style={{ width:'100%',height:'100%',display:'flex',alignItems:'center',justifyContent:'center',fontSize:10,color:'var(--fg-tertiary)' }}>📷</div>
              )}
            </div>
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
      <label>Fotos de la propiedad</label>
      <div
        className={`dropzone ${drag ? 'drag' : ''} ${photos.length ? 'has-files' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current && inputRef.current.click()}
        role="button"
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
                  <button type="button" className="dz-btn" title="Marcar como portada"
                          onClick={(e) => { e.stopPropagation(); onSetCover(p.id); }}>
                    <Icon name="star" size={12} />
                  </button>
                )}
                <button type="button" className="dz-btn danger" title="Eliminar"
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

function NewPropertyModal({ onClose, onSave, mode = 'create', initialData = null, saving = false }) {
  const [form, setForm] = useState(() => {
    if (initialData) {
      return {
        addr:      initialData.addr      || '',
        neigh:     initialData.neigh     || '',
        city:      initialData.city      || initialData.neigh || '',
        type:      initialData.type      || 'Departamento',
        operation: initialData.operation || 'rent',
        status:    initialData.status    || 'available',
        rooms:     initialData.rooms     || '2 amb',
        m2:        initialData.m2        != null ? String(initialData.m2) : '',
        baths:     initialData.baths     ?? 1,
        parking:   initialData.parking   ?? 0,
        price:     initialData.price     != null ? String(initialData.price) : '',
        currency:  initialData.currency  || 'ARS',
        agent:     initialData.agent     || 'M. Pereyra',
        desc:      initialData.desc || initialData.notes || '',
        notes:     initialData.notes     || '',
        photos:    [],
      };
    }
    return {
      addr: '', neigh: '', city: '', type: 'Departamento', operation: 'rent', status: 'available',
      rooms: '2 amb', m2: '', baths: 1, parking: 0,
      price: '', currency: 'ARS', agent: 'M. Pereyra',
      desc: '', notes: '', photos: [],
    };
  });
  const [priceDisplay, setPriceDisplay] = useState(() =>
    initialData?.price != null
      ? formatPriceDisplay(String(initialData.price), initialData.currency || 'ARS')
      : ''
  );
  const [touched, setTouched] = useState({ addr: false, price: false });

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

  const canSave = form.addr.trim() && form.price;
  const errAddr  = touched.addr  && !form.addr.trim();
  const errPrice = touched.price && !form.price;

  const submit = () => {
    setTouched({ addr: true, price: true });
    if (!canSave) return;
    const imagesUrls = form.photos.map(p => p.url);
    const photo = imagesUrls[0] || (mode === 'edit' ? initialData?.photo || '' : '');
    const allImages = imagesUrls.length > 0 ? imagesUrls : (mode === 'edit' ? (initialData?.images || []) : []);
    onSave({
      addr:      form.addr,
      neigh:     form.neigh,
      city:      form.city,
      type:      form.type,
      operation: form.operation,
      status:    form.status,
      rooms:     form.rooms,
      m2:        Number(form.m2) || 0,
      baths:     Number(form.baths) || 0,
      parking:   Number(form.parking) || 0,
      price:     Number(form.price) || 0,
      currency:  form.currency,
      agent:     form.agent,
      notes:     form.desc || form.notes,
      photo,
      images: allImages,
    });
  };
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal lg" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{mode === 'edit' ? 'Editar propiedad' : 'Nueva propiedad'}</h3>
          <span className="close"><IconButton name="x" onClick={onClose} /></span>
        </div>
        <div className="modal-body">
          <div className="field">
            <label>Dirección <span style={{color:'var(--danger-500)'}}>*</span></label>
            <input
              placeholder="Av. Cabildo 2350"
              value={form.addr}
              onChange={e => set('addr', e.target.value)}
              onBlur={() => setTouched(t => ({ ...t, addr: true }))}
              autoFocus
              style={errAddr ? { borderColor: 'var(--danger-500)', boxShadow: '0 0 0 2px var(--danger-100)' } : undefined}
            />
            {errAddr && <span style={{fontSize:11,color:'var(--danger-500)',marginTop:3,display:'block'}}>La dirección es obligatoria.</span>}
          </div>
          <div className="field-row">
            <div className="field">
              <label>Barrio / zona</label>
              <input placeholder="Belgrano" value={form.neigh} onChange={e => set('neigh', e.target.value)} />
            </div>
            <div className="field">
              <label>Ciudad</label>
              <input placeholder="Oberá" value={form.city} onChange={e => set('city', e.target.value)} />
            </div>
            <div className="field">
              <label>Código interno</label>
              <input placeholder="Se genera automáticamente" disabled />
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label>Tipo</label>
              <select value={form.type} onChange={e => set('type', e.target.value)}>
                <option>Departamento</option>
                <option>Casa</option>
                <option>PH</option>
                <option>Local</option>
                <option>Oficina</option>
                <option>Terreno</option>
              </select>
            </div>
            <div className="field">
              <label>Operación</label>
              <select value={form.operation} onChange={e => set('operation', e.target.value)}>
                <option value="rent">Alquiler</option>
                <option value="sale">Venta</option>
              </select>
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label>Estado</label>
              <select value={form.status} onChange={e => set('status', e.target.value)}>
                <option value="available">Disponible</option>
                <option value="reserved">Reservada</option>
                <option value="rented">Alquilada</option>
                <option value="sale">En venta</option>
              </select>
            </div>
            <div className="field">
              <label>Agente asignado</label>
              <select value={form.agent} onChange={e => set('agent', e.target.value)}>
                <option>M. Pereyra</option>
                <option>J. Suárez</option>
                <option>L. Ferreyra</option>
                <option>D. Ramírez</option>
              </select>
            </div>
          </div>

          <div className="prop-attrs-grid">
            <div className="field">
              <label>Ambientes</label>
              <select value={form.rooms} onChange={e => set('rooms', e.target.value)}>
                <option value="—">—</option>
                <option>1 amb</option>
                <option>2 amb</option>
                <option>3 amb</option>
                <option>4 amb</option>
                <option>5+ amb</option>
              </select>
            </div>
            <div className="field">
              <label>Baños</label>
              <input type="number" min="0" value={form.baths} onChange={e => set('baths', e.target.value)} style={{textAlign:'center'}} />
            </div>
            <div className="field">
              <label>Cocheras</label>
              <input type="number" min="0" value={form.parking} onChange={e => set('parking', e.target.value)} style={{textAlign:'center'}} />
            </div>
            <div className="field">
              <label>Superficie (m²)</label>
              <input type="number" min="1" placeholder="58" value={form.m2} onChange={e => set('m2', e.target.value)} />
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label>Precio <span style={{color:'var(--danger-500)'}}>*</span></label>
              <input
                type="text"
                inputMode="numeric"
                placeholder={form.currency === 'USD' ? '85,000' : '285.000'}
                value={priceDisplay}
                onChange={handlePriceChange}
                onBlur={() => setTouched(t => ({ ...t, price: true }))}
                style={errPrice ? { borderColor: 'var(--danger-500)', boxShadow: '0 0 0 2px var(--danger-100)' } : undefined}
              />
              {errPrice && <span style={{fontSize:11,color:'var(--danger-500)',marginTop:3,display:'block'}}>El precio es obligatorio.</span>}
            </div>
            <div className="field">
              <label>Moneda</label>
              <select value={form.currency} onChange={handleCurrencyChange}>
                <option value="ARS">ARS — pesos</option>
                <option value="USD">USD — dólares</option>
              </select>
            </div>
          </div>

          <div className="field">
            <label>Descripción</label>
            <textarea placeholder="Descripción para mostrar a los clientes, ej: 'Departamento luminoso con balcón y vista al parque...'"
              value={form.desc} onChange={e => set('desc', e.target.value)} rows={3}
              style={{resize:'vertical',width:'100%'}} />
          </div>

          <div className="field">
            <label>Notas</label>
            <textarea placeholder="Detalles internos para el equipo" value={form.notes} onChange={e => set('notes', e.target.value)} rows={2} style={{resize:'vertical',width:'100%'}} />
          </div>

          <PhotoDropzone
            photos={form.photos}
            onAdd={addPhotos}
            onRemove={removePhoto}
            onSetCover={setCover}
          />
        </div>
        <div className="modal-foot">
          <Button kind="ghost" size="sm" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button kind="primary" size="sm" onClick={submit} disabled={!canSave || saving}>
            {saving ? 'Guardando…' : mode === 'edit' ? 'Guardar cambios' : 'Crear propiedad'}
          </Button>
        </div>
      </div>
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
  const [view, setView] = useState('grid');
  const [open, setOpen] = useState(initialProperty || null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const handleDelete = (property) => {
    deleteProperty.mutate(property.id, {
      onSuccess: () => {
        setDeleteTarget(null);
        setOpen(null);
        pushToast({ text: `Propiedad eliminada — ${property.addr}.`, kind: 'danger' });
      },
      onError: () => pushToast({ text: 'Error al eliminar la propiedad.', kind: 'danger' }),
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

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Propiedades</h1>
          <div className="sub">{properties.length} en cartera · {counts.available} disponibles · {counts.rented} alquiladas · {counts.sold} vendidas</div>
        </div>
        <div className="page-h-actions">
          <Button kind="secondary" icon="download">Exportar</Button>
          <Button kind="primary" icon="plus" onClick={() => setCreating(true)}>Agregar propiedad</Button>
        </div>
      </div>
      <div className="scroll-surface surface">
        <div className="filter-bar">
          <input placeholder="Buscar por dirección, barrio..." value={search} onChange={e => setSearch(e.target.value)} />
          {[['all','Todas',counts.all],['available','Disponibles',counts.available],['rented','Alquiladas',counts.rented],['sale','En venta',counts.sale],['reserved','Reservadas',counts.reserved],['sold','Vendidas',counts.sold]].map(([k,l,n]) => (
            <span key={k} className={`chip ${filter===k?'active':''}`} onClick={()=>setFilter(k)}>{l}<span className="num">{n}</span></span>
          ))}
          <span style={{flex:1}}></span>
          <select value={op} onChange={e=>setOp(e.target.value)}>
            <option value="all">Todas las operaciones</option>
            <option value="rent">Alquiler</option>
            <option value="sale">Venta</option>
          </select>
          <div className="views">
            <button className={view==='list'?'active':''} onClick={()=>setView('list')}><Icon name="list" size={13} /></button>
            <button className={view==='grid'?'active':''} onClick={()=>setView('grid')}><Icon name="grid" size={13} /></button>
          </div>
        </div>
        <div className="tbl-scroll">
          {view === 'list' ? (
            <table className="tbl">
              <thead><tr>
                <th>Propiedad</th><th>Tipo</th><th>Estado</th><th>Operación</th><th style={{textAlign:'right'}}>Precio</th><th>Agente</th><th></th>
              </tr></thead>
              <tbody>
                {filtered.map(p => (
                  <tr key={p.id} onClick={() => setOpen(p)}>
                    <td>
                      <div style={{display:'flex',alignItems:'center',gap:10}}>
                        <span className="prop-thumb" style={{background: isImg(p.photo) ? 'var(--gray-100)' : (p.photo || 'var(--gray-100)'), overflow: 'hidden'}}>
                          {isImg(p.photo) ? <img src={p.photo} alt="" style={{width:'100%',height:'100%',objectFit:'cover'}} /> : <Icon name="building" />}
                        </span>
                        <div className="addr-block">
                          <div className="a1">{p.addr}</div>
                          <div className="a2">{p.neigh} · {p.rooms !== '—' && p.rooms + ' · '}{p.m2} m²</div>
                        </div>
                      </div>
                    </td>
                    <td className="muted">{p.type}</td>
                    <td><StatusDropdown kind={p.status} onSelect={(s) => updateStatus.mutate({ id: p.id, status: s })} /></td>
                    <td className="muted">{p.operation === 'rent' ? 'Alquiler' : 'Venta'}</td>
                    <td className="price" style={{textAlign:'right',whiteSpace:'nowrap'}}>
                      {fmtCurrency(p.price, p.currency)}
                      {p.operation === 'rent' && p.status !== 'sale' && <span className="muted" style={{fontWeight:400}}> /mes</span>}
                    </td>
                    <td className="muted">{p.agent}</td>
                    <td><div className="row-actions" onClick={e => e.stopPropagation()}>
                      <IconButton name="edit" onClick={() => setEditing(p)} />
                      <IconButton name="trash" onClick={() => setDeleteTarget(p)} />
                    </div></td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="7" className="tbl-empty">No hay propiedades que coincidan con los filtros.</td></tr>}
              </tbody>
            </table>
          ) : (
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(240px,1fr))',gap:14,padding:14}}>
              {filtered.map(p => (
                <div key={p.id} onClick={() => setOpen(p)} style={{border:'1px solid var(--border-default)',borderRadius:10,cursor:'pointer',background:'white',transition:'box-shadow var(--dur-fast)'}} onMouseEnter={(e)=>e.currentTarget.style.boxShadow='var(--shadow-sm)'} onMouseLeave={(e)=>e.currentTarget.style.boxShadow=''}>
                  <div style={{position:'relative'}}>
                    {isImg(p.photo) ? (
                      <div style={{aspectRatio:'4/3',background:'var(--gray-100)',overflow:'hidden',borderRadius:'10px 10px 0 0'}}>
                        <img src={p.photo} alt={p.addr} style={{width:'100%',height:'100%',objectFit:'cover',display:'block'}} />
                      </div>
                    ) : (
                      <div className="prop-photo" style={{background: p.photo || 'var(--gray-100)', borderRadius:'10px 10px 0 0', aspectRatio:'4/3'}}>{p.type}</div>
                    )}
                    <StatusDropdown kind={p.status} overlay onSelect={(s) => updateStatus.mutate({ id: p.id, status: s })} />
                  </div>
                  <div style={{padding:12,display:'flex',flexDirection:'column',gap:6}}>
                    <div style={{fontSize:13,fontWeight:600,color:'var(--fg-primary)'}}>{p.addr}</div>
                    <div style={{fontSize:11,color:'var(--fg-tertiary)'}}>{p.neigh}</div>
                    <div style={{fontSize:11,color:'var(--fg-tertiary)'}}>{p.type && p.type + ' · '}{p.rooms !== '—' && p.rooms + ' · '}{p.m2} m² · {p.baths} baño{p.baths!==1?'s':''}</div>
                    <div className="tabular" style={{fontSize:14,fontWeight:600,marginTop:2,display:'flex',alignItems:'baseline',gap:5}}>
                      {fmtCurrency(p.price, p.currency)}
                      <span style={{fontSize:10,fontWeight:500,color:'var(--fg-muted)',letterSpacing:'0.02em'}}>{p.currency}</span>
                      {p.operation==='rent' && p.status !== 'sale' && <span className="muted" style={{fontWeight:400,fontSize:11}}> /mes</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
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
        <div className="modal-backdrop" onClick={() => setDeleteTarget(null)}>
          <div className="modal" style={{maxWidth:420}} onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Eliminar propiedad</h3>
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
                onClick={() => handleDelete(deleteTarget)}
                disabled={deleteProperty.isPending}>
                {deleteProperty.isPending ? 'Eliminando...' : 'Sí, eliminar'}
              </Button>
            </div>
          </div>
        </div>
      )}
      {creating && (
        <NewPropertyModal
          onClose={() => setCreating(false)}
          onSave={(data) => {
            setCreating(false);
            createProperty.mutate(data, {
              onSuccess: () => pushToast({ text: 'Propiedad creada.' }),
              onError: () => pushToast({ text: 'Error al crear la propiedad.', kind: 'danger' }),
            });
          }}
        />
      )}
      {editing && (
        <NewPropertyModal
          mode="edit"
          initialData={editing}
          onClose={() => setEditing(null)}
          onSave={(data) => {
            setEditing(null);
            updateProperty.mutate({ id: editing.id, ...data }, {
              onSuccess: () => pushToast({ text: 'Propiedad actualizada.' }),
              onError: () => pushToast({ text: 'Error al guardar los cambios.', kind: 'danger' }),
            });
          }}
        />
      )}
    </div>
  );
}

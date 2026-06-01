import React, { useState, useEffect, useRef, useMemo, Fragment } from 'react';

export function Icon({ name, size = 24, stroke = 2, style, className }) {
  const paths = {
    home: <><path d="M3 12l9-9 9 9"/><path d="M5 10v10h14V10"/></>,
    building: <><path d="M3 21h18"/><path d="M5 21V5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v16"/><path d="M14 21V9a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v12"/><path d="M7.5 7.5h3M7.5 11h3"/><path d="M16 11.5h1.5M16 14.5h1.5"/><path d="M8.5 21v-3a1.5 1.5 0 0 1 3 0v3"/></>,
    contract: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 13h6M9 17h4"/></>,
    money: <><path d="M12 2v20"/><path d="M5 8h11a3 3 0 0 1 0 6H8a3 3 0 0 0 0 6h11"/></>,
    calendar: <><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></>,
    users: <><circle cx="9" cy="7.5" r="3"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 4.8a3 3 0 0 1 0 5.4"/><path d="M16.8 13.2a5.5 5.5 0 0 1 3.7 6.8"/></>,
    user: <><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></>,
    folder: <><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    search: <><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></>,
    chevronLeft: <path d="M15 18l-6-6 6-6"/>,
    chevronRight: <path d="M9 18l6-6-6-6"/>,
    chevronDown: <path d="M6 9l6 6 6-6"/>,
    arrowUp: <path d="M7 17l5-5 5 5M12 17V7"/>,
    arrowDown: <path d="M7 7l5 5 5-5M12 7v10"/>,
    arrowRight: <path d="M5 12h14M12 5l7 7-7 7"/>,
    more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
    edit: <><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></>,
    trash: <><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6"/></>,
    filter: <path d="M22 3H2l8 9.5V19l4 2v-8.5L22 3z"/>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></>,
    check: <path d="M20 6L9 17l-5-5"/>,
    x: <path d="M18 6L6 18M6 6l12 12"/>,
    clock: <><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></>,
    phone: <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>,
    mail: <><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></>,
    mapPin: <><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></>,
    activity: <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>,
    refresh: <><path d="M3 12a9 9 0 0 1 15-6.7l3 3"/><path d="M21 4v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7l-3-3"/><path d="M3 20v-5h5"/></>,
    video: <><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></>,
    msg: <><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></>,
    whatsapp: <><path d="M12 3.2a8.8 8.8 0 0 0-7.5 13.4l-1.3 4.2 4.3-1.3A8.8 8.8 0 1 0 12 3.2z"/><path fill="currentColor" stroke="none" transform="translate(-0.3 -0.5)" d="M9.7 7.9c-.2-.4-.4-.4-.6-.4h-.5c-.2 0-.5.1-.7.3-.3.3-1 .9-1 2.2 0 1.3 1 2.6 1.1 2.7.1.2 1.9 3 4.7 4.1.6.3 1.1.4 1.5.5.6.2 1.2.2 1.6.1.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2-.1-.1-.2-.2-.5-.3-.3-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1-.2.2-.6.8-.8 1-.1.1-.3.2-.5.1-.4-.2-1.1-.5-2-1.3-.7-.7-1.2-1.4-1.4-1.7-.1-.2 0-.4.1-.5.1-.1.2-.3.4-.4.1-.1.2-.3.2-.4.1-.1 0-.3 0-.4 0-.1-.5-1.4-.7-1.9z"/></>,
    eye: <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>,
    bed: <><path d="M2 4v16M22 12v8M2 12h20M2 18h20"/><path d="M6 12V8a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v4"/></>,
    bath: <><path d="M9 6V3.5a1.5 1.5 0 1 1 3 0V6"/><path d="M2 12h20l-1 7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M2 12V5a2 2 0 0 1 2-2h2"/></>,
    ruler: <path d="M16 2l6 6L8 22l-6-6L16 2zM7.5 10.5l2 2M10.5 7.5l2 2M13.5 4.5l2 2M4.5 13.5l2 2"/>,
    car: <><path d="M5 17H3a1 1 0 0 1-1-1v-3a3 3 0 0 1 3-3h14a3 3 0 0 1 3 3v3a1 1 0 0 1-1 1h-2"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M5 10l1.5-4.5A2 2 0 0 1 8.5 4h7a2 2 0 0 1 2 1.5L19 10"/></>,
    download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></>,
    upload: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></>,
    star: <polygon points="12 2 15.1 8.6 22 9.3 17 14.1 18.2 21 12 17.8 5.8 21 7 14.1 2 9.3 8.9 8.6 12 2"/>,
    info: <><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></>,
    grid: <><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></>,
    list: <><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></>,
    copy: <><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></>,
    menu: <><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></>,
  };
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={style}>
      {paths[name] || null}
    </svg>
  );
}

export function Button({ kind = 'secondary', size, icon, children, onClick, style, type, disabled }) {
  const cls = ['btn', `btn-${kind}`, size === 'sm' ? 'btn-sm' : ''].join(' ');
  return (
    <button className={cls} onClick={onClick} style={style} type={type || 'button'} disabled={disabled}>
      {icon && <Icon name={icon} size={size === 'sm' ? 12 : 14} />}
      {children}
    </button>
  );
}

export function IconButton({ name, onClick, title, size = 16 }) {
  return (
    <button className="btn btn-ghost btn-icon" onClick={onClick} title={title} type="button">
      <Icon name={name} size={size} />
    </button>
  );
}

const PILL_KINDS = {
  available: { cls: 'pill-available', dot: '#3d8b4f', label: 'Disponible' },
  rented:    { cls: 'pill-rented',    dot: '#3a5fa8', label: 'Alquilada' },
  sale:      { cls: 'pill-sale',      dot: '#6b4d99', label: 'En venta'  },
  expiring:  { cls: 'pill-expiring',  dot: '#b07d12', label: 'Por vencer'},
  expired:   { cls: 'pill-expired',   dot: '#b53b3b', label: 'Vencido'   },
  paid:      { cls: 'pill-paid',      dot: '#3d8b4f', label: 'Pagado'    },
  pending:   { cls: 'pill-pending',   dot: '#b07d12', label: 'Pendiente' },
  cancelled: { cls: 'pill-cancelled', dot: '#8b919a', label: 'Cancelado' },
  reserved:  { cls: 'pill-rented',    dot: '#3a5fa8', label: 'Reservada' },
  active:    { cls: 'pill-paid',      dot: '#3d8b4f', label: 'Activo'    },
  prospect:  { cls: 'pill-rented',    dot: '#3a5fa8', label: 'Prospecto' },
  owner:     { cls: 'pill-sale',      dot: '#6b4d99', label: 'Propietario'},
  tenant:    { cls: 'pill-paid',      dot: '#3d8b4f', label: 'Inquilino' },
};
export function Pill({ kind, children, className }) {
  const k = PILL_KINDS[kind];
  if (!k) return <span className={`pill pill-neutral ${className || ''}`}>{children}</span>;
  return (
    <span className={`pill ${k.cls} ${className || ''}`}>
      <span className="dot" style={{ background: k.dot }} />
      {children || k.label}
    </span>
  );
}

/* ── Status Dropdown ──────────────────────────────────────────────────────────
 * Clickable pill that opens a floating menu of all statuses.
 * Props:
 *   kind      – current status key
 *   onSelect  – called with (newStatusKey) on selection
 *   overlay   – if true, renders as pill-overlay (absolute top-right)
 *   size      – 'sm' | 'md' (default 'md')
 */
const STATUS_OPTIONS = ['available','sold','rented','reserved'];
const STATUS_LABELS = {
  available: { label: 'Disponible',  dot: '#3d8b4f', cls: 'pill-available' },
  sold:      { label: 'Vendida',     dot: '#6b4d99', cls: 'pill-sale'      },
  rented:    { label: 'Alquilada',   dot: '#3a5fa8', cls: 'pill-rented'    },
  reserved:  { label: 'Reservada',   dot: '#3a5fa8', cls: 'pill-rented'    },
};
export function StatusDropdown({ kind, onSelect, overlay, size = 'md' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const current = STATUS_LABELS[kind] ?? STATUS_LABELS.available;
  // Fallback for legacy statuses like 'sale' that don't match DB values
  if (!STATUS_LABELS[kind]) {
    const cls = overlay ? `pill pill-neutral pill-overlay` : `pill pill-neutral`;
    return (
      <span style={{ position: overlay ? 'absolute' : 'static', top: overlay ? 8 : undefined, right: overlay ? 8 : undefined, zIndex: overlay ? 1 : undefined }}>
        <span className={cls}><span className="dot" style={{background:'#8b919a'}} />{kind}</span>
      </span>
    );
  }
  const cls = overlay ? `pill ${current.cls} pill-overlay` : `pill ${current.cls}`;

  return (
    <span ref={ref} className={`status-dropdown ${open ? 'open' : ''}`} style={{ position: overlay ? 'absolute' : 'relative', display:'inline-block', top: overlay ? 8 : undefined, right: overlay ? 8 : undefined, zIndex: overlay ? 1 : undefined }}>
      <span className={cls} style={{ cursor:'pointer', userSelect:'none' }} onClick={(e) => { e.stopPropagation(); setOpen(o => !o); }}>
        <span className="dot" style={{ background: current.dot }} />
        {current.label}
        <svg width="8" height="8" viewBox="0 0 8 8" style={{ marginLeft:2, opacity:0.6 }}><path d="M2 3l2 2 2-2" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
      </span>
      {open && (
        <div className="status-dropdown-menu" style={{ right: overlay ? 0 : undefined, left: overlay ? 'auto' : 0 }} onClick={(e) => e.stopPropagation()}>
          {STATUS_OPTIONS.map(sk => {
            const opt = STATUS_LABELS[sk];
            return (
              <div key={sk} className={`status-dropdown-item ${sk === kind ? 'active' : ''}`}
                   onClick={() => { onSelect(sk); setOpen(false); }}>
                <span className="sd-dot" style={{ background: opt.dot }} />
                {opt.label}
              </div>
            );
          })}
        </div>
      )}
    </span>
  );
}

export function initials(name) {
  return name.split(' ').slice(0, 2).map(s => s[0]).join('').toUpperCase();
}

const toastListeners = [];
export function pushToast(t) { toastListeners.forEach(fn => fn(t)); }
export function ToastStack() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    const onPush = (t) => {
      const id = Math.random().toString(36).slice(2);
      setItems(s => [...s, { id, ...t }]);
      setTimeout(() => setItems(s => s.filter(i => i.id !== id)), 3500);
    };
    toastListeners.push(onPush);
    return () => { toastListeners.splice(toastListeners.indexOf(onPush), 1); };
  }, []);
  return (
    <div className="toast-stack">
      {items.map(t => (
        <div key={t.id} className={`toast ${t.kind || ''}`}>
          <Icon className="icon" name={t.kind === 'danger' ? 'x' : 'check'} size={16} />
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}

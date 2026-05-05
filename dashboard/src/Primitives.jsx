import React, { useState, useEffect, useRef, useMemo, Fragment } from 'react';

export function Icon({ name, size = 16, stroke = 1.5, style, className }) {
  const paths = {
    home: <><path d="M3 12l9-9 9 9"/><path d="M5 10v10h14V10"/></>,
    building: <><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 9h.01M9 12h.01M9 15h.01M15 9h.01M15 12h.01M15 15h.01"/></>,
    contract: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M9 13h6M9 17h4"/></>,
    money: <><path d="M12 2v20"/><path d="M5 8h11a3 3 0 0 1 0 6H8a3 3 0 0 0 0 6h11"/></>,
    calendar: <><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-8 0v2"/><circle cx="12" cy="7" r="4"/></>,
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
    whatsapp: <><path d="M16.7 13.4c-.3-.1-1.6-.8-1.8-.9-.2-.1-.4-.1-.6.1-.2.3-.7.9-.8 1.1-.2.2-.3.2-.5.1-.4-.2-1.4-.5-2.7-1.7-1-1-1.6-2.1-1.8-2.5-.2-.4 0-.6.1-.7.1-.1.3-.3.4-.5.1-.2.2-.3.3-.5.1-.2 0-.4 0-.5 0-.1-.6-1.4-.8-1.9-.2-.5-.4-.4-.6-.4h-.5c-.2 0-.5.1-.7.4-.3.3-1 1-1 2.4 0 1.4 1 2.8 1.2 3 .1.2 2 3 4.7 4.2.7.3 1.2.5 1.6.6.7.2 1.3.2 1.8.1.6-.1 1.6-.7 1.8-1.3.2-.6.2-1.1.2-1.3-.1-.1-.3-.1-.6-.3z"/><path d="M19 5a10 10 0 0 0-15.8 12L2 22l5-1.3A10 10 0 1 0 19 5z"/></>,
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

export function IconButton({ name, onClick, title, size = 14 }) {
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
export function Pill({ kind, children }) {
  const k = PILL_KINDS[kind];
  if (!k) return <span className="pill pill-neutral">{children}</span>;
  return (
    <span className={`pill ${k.cls}`}>
      <span className="dot" style={{ background: k.dot }} />
      {children || k.label}
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

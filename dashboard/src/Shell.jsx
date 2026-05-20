import React, { useState, useRef, useEffect } from 'react';
import { Icon } from './Primitives';
import { useNotifications, useMarkNotificationRead, useMarkAllRead, useDeleteNotification } from './api';

export function Sidebar({ active, onNav, isOpen, onClose }) {
  const items = [
    { id: 'dashboard',  icon: 'home',     label: 'Inicio' },
    { id: 'calendar',   icon: 'calendar', label: 'Calendario' },
    { id: 'properties', icon: 'building', label: 'Propiedades' },
    { id: 'clients',    icon: 'users',    label: 'Clientes' },
    { id: 'faqs',       icon: 'msg',      label: 'FAQ' },
  ];
  const more = [
    { id: 'documents',  icon: 'folder',   label: 'Documentos' },
  ];

  const handleNav = (id) => {
    onNav(id);
    if (onClose) onClose();
  };

  return (
    <>
      {isOpen && <div className="sb-backdrop" onClick={onClose} />}
      <aside className={`sb${isOpen ? ' open' : ''}`}>
        <div className="sb-brand">
          <img src="/logo.svg" alt="InmuebleBot" />
          <button className="sb-close" onClick={onClose} aria-label="Cerrar menú">
            <Icon name="x" size={16} />
          </button>
        </div>
        <div className="sb-section">Principal</div>
        {items.map(it => (
          <div key={it.id}
               className={`sb-item ${active === it.id ? 'active' : ''}`}
               onClick={() => handleNav(it.id)}>
            <Icon name={it.icon} size={16} />
            <span>{it.label}</span>
            {it.badge && <span className="badge">{it.badge}</span>}
          </div>
        ))}
        {more.map(it => (
          <div key={it.id}
               className={`sb-item ${active === it.id ? 'active' : ''}`}
               onClick={() => handleNav(it.id)}>
            <Icon name={it.icon} size={16} />
            <span>{it.label}</span>
          </div>
        ))}
        <div className="sb-section">Sistema</div>
        <div className={`sb-item ${active === 'settings' ? 'active' : ''}`} onClick={() => handleNav('settings')}>
          <Icon name="settings" size={16} />
          <span>Configuración</span>
        </div>
        <div className="sb-bottom">
          <span className="av">MP</span>
          <div className="who">
            <b>María Pereyra</b>
            <span>Inmobiliaria Norte</span>
          </div>
        </div>
      </aside>
    </>
  );
}

// ── Icono por tipo de notificación ────────────────────────────────────────────
const TYPE_ICON = {
  visit_scheduled:   '📅',
  visit_rescheduled: '🔄',
  visit_cancelled:   '❌',
  call_scheduled:    '📞',
  handoff_requested: '🚨',
  new_lead:          '👤',
  lead_qualified:    '⭐',
  bot_error:         '⚠️',
};

function timeAgo(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'ahora';
  if (m < 60) return `hace ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h}h`;
  return `hace ${Math.floor(h / 24)}d`;
}

function NotificationPanel({ onClose, onAction }) {
  const { data, isLoading } = useNotifications();
  const markRead   = useMarkNotificationRead();
  const markAll    = useMarkAllRead();
  const deleteNotif = useDeleteNotification();

  const notifications = data?.notifications ?? [];
  const unread = data?.unread_count ?? 0;

  return (
    <div className="notif-panel" onClick={e => e.stopPropagation()}>
      <div className="notif-header">
        <span className="notif-title">Notificaciones {unread > 0 && <span className="notif-badge-sm">{unread}</span>}</span>
        {unread > 0 && (
          <button className="notif-mark-all" onClick={() => markAll.mutate()}>
            Marcar todo leído
          </button>
        )}
      </div>

      <div className="notif-list">
        {isLoading && <div className="notif-empty">Cargando...</div>}
        {!isLoading && notifications.length === 0 && (
          <div className="notif-empty">Sin notificaciones</div>
        )}
        {notifications.map(n => (
          <div
            key={n.id}
            className={`notif-item ${n.read ? 'read' : 'unread'}`}
            onClick={() => {
              if (!n.read) markRead.mutate(n.id);
              if (onAction) { onAction(n); onClose(); }
            }}
          >
            <span className="notif-icon">{TYPE_ICON[n.type] ?? '🔔'}</span>
            <div className="notif-content">
              <div className="notif-item-title">{n.title}</div>
              {n.body && <div className="notif-item-body">{n.body}</div>}
              <div className="notif-time">{timeAgo(n.created_at)}</div>
            </div>
            <button
              className="notif-delete"
              title="Eliminar"
              onClick={e => { e.stopPropagation(); deleteNotif.mutate(n.id); }}
            >×</button>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Topbar({ onMenuToggle, onNotifAction }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const { data } = useNotifications();
  const unread = data?.unread_count ?? 0;

  // Cierra el panel al hacer click fuera
  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <header className="tb">
      <button className="tb-menu-btn btn btn-ghost btn-icon" onClick={onMenuToggle} aria-label="Menú">
        <Icon name="menu" size={16} />
      </button>
      <div className="tb-spacer" />
      <div className="tb-notif-wrap" ref={ref}>
        <span className="tb-icon" title="Notificaciones" onClick={() => setOpen(v => !v)}>
          <Icon name="bell" size={16} />
          {unread > 0 && <span className="dot">{unread > 9 ? '9+' : unread}</span>}
        </span>
        {open && <NotificationPanel onClose={() => setOpen(false)} onAction={onNotifAction} />}
      </div>
      <span className="tb-icon" title="Ayuda">
        <Icon name="info" size={16} />
      </span>
      <span className="tb-avatar" title="María Pereyra">MP</span>
    </header>
  );
}

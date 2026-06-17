import React, { useState, useRef, useEffect } from 'react';
import { Icon, Button, IconButton, pushToast } from './Primitives';
import { useNotifications, useMarkNotificationRead, useMarkAllRead, useDeleteNotification, useDeleteReadNotifications, useCreateErrorReport } from './api';
import { useAuth } from './auth';
import { useFocusTrap } from './useFocusTrap';

// Contexto útil para el dev, sin datos sensibles (sin tokens/cookies). El backend
// igualmente redacta credenciales antes de persistir.
async function collectReportContext() {
  let version = null;
  try {
    const res = await fetch('/version', { cache: 'no-store' });
    if (res.ok) { const d = await res.json(); version = d?.commit ?? d?.build ?? null; }
  } catch { /* offline / cold start: el reporte se manda igual sin versión */ }
  return {
    route: `${window.location.pathname}${window.location.hash}`,
    version,
    user_agent: navigator.userAgent,
  };
}

const SEVERITY_OPTIONS = [
  { value: 'low', label: 'Baja' },
  { value: 'med', label: 'Media' },
  { value: 'high', label: 'Alta' },
];

// Modal global "Reportar error": mensaje + severidad. Adjunta contexto automáticamente.
function ReportErrorModal({ onClose }) {
  const [message, setMessage] = useState('');
  const [severity, setSeverity] = useState('med');
  const [error, setError] = useState('');
  const createReport = useCreateErrorReport();
  const trapRef = useFocusTrap(onClose);

  const handleSubmit = async () => {
    if (!message.trim()) { setError('Contanos qué pasó.'); return; }
    try {
      const context = await collectReportContext();
      await createReport.mutateAsync({ message: message.trim(), severity, context });
      pushToast({ kind: 'success', text: 'Reporte enviado. ¡Gracias!' });
      onClose();
    } catch {
      pushToast({ kind: 'danger', text: 'No se pudo enviar el reporte. Reintentá.' });
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="report-error-title" ref={trapRef} onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <div className="modal-head">
          <h3 id="report-error-title">Reportar un error</h3>
          <span className="close"><IconButton name="x" title="Cerrar" onClick={onClose} /></span>
        </div>
        <div className="modal-body">
          <div className="field">
            <label htmlFor="report-message">¿Qué pasó? *</label>
            <textarea
              id="report-message"
              autoFocus
              className={error ? 'invalid' : ''}
              aria-invalid={error ? 'true' : undefined}
              value={message}
              onChange={e => { setMessage(e.target.value); if (error) setError(''); }}
              placeholder="Describí el problema: qué intentabas hacer y qué salió mal."
              rows={5}
              maxLength={4000}
            />
            {error && <span className="field-error">{error}</span>}
          </div>
          <div className="field">
            <label htmlFor="report-severity">Gravedad</label>
            <select id="report-severity" value={severity} onChange={e => setSeverity(e.target.value)}>
              {SEVERITY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--fg-tertiary)' }}>
            Adjuntamos la sección actual y la versión de la app. No enviamos contraseñas ni datos sensibles.
          </p>
        </div>
        <div className="modal-foot">
          <Button kind="ghost" size="sm" onClick={onClose} disabled={createReport.isPending}>Cancelar</Button>
          <Button kind="primary" size="sm" icon="check" onClick={handleSubmit} disabled={createReport.isPending}>
            {createReport.isPending ? 'Enviando…' : 'Enviar reporte'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Iniciales para el avatar a partir del nombre o el email.
function initialsFrom(account) {
  const name = account?.account?.full_name || account?.account?.email || '';
  const parts = name.replace(/@.*/, '').split(/[.\s_-]+/).filter(Boolean);
  const ini = (parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '');
  return (ini || name.slice(0, 2) || '?').toUpperCase();
}

function roleLabelFromScope(scope) {
  if (scope === 'org')    return 'Dueño';
  if (scope === 'branch') return 'Gerente';
  return 'Titular';
}

function planLabel(me) {
  const raw = me?.plan || me?.subscription?.plan || '';
  if (!raw) return 'Gratis';
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function contextLine(me, activeBranch) {
  const orgName = me?.org_name || me?.tenant_slug || 'Inmobiliaria';
  const scope = me?.scope;
  if (scope === 'org') {
    if (activeBranch) {
      const b = (me?.branches || []).find(x => x.id === activeBranch);
      return `Dueño · viendo ${b ? b.name : 'sucursal'}`;
    }
    return `Dueño · ${orgName}`;
  }
  if (scope === 'branch') return `Gerente · ${orgName}`;
  return orgName;
}

function AccountMenu({ onNav }) {
  const { me, logout, activeBranch, selectBranch } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', handler);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', handler);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const account = me;
  const name = account?.account?.full_name || account?.account?.email || 'Mi cuenta';
  const email = account?.account?.email || '';
  const showBackToConsolidated = account?.scope === 'org' && !!activeBranch;

  const goSettings = () => { onNav('settings'); setOpen(false); };
  const backToConsolidated = () => { selectBranch(null); setOpen(false); };
  const doLogout = () => { setOpen(false); logout(); };

  return (
    <div className="acct-wrap" ref={ref}>
      {open && (
        <div className="acct-pop" role="dialog" aria-label="Cuenta" onClick={e => e.stopPropagation()}>
          <div className="acct-pop-head">
            <span className="av acct-pop-av">{initialsFrom(account)}</span>
            <div className="acct-pop-id">
              <b>{name}</b>
              {email && <span>{email}</span>}
            </div>
          </div>
          <div className="acct-chips">
            <span className="acct-chip acct-chip-role">{roleLabelFromScope(account?.scope)}</span>
            <span className="acct-chip acct-chip-plan">{planLabel(account)}</span>
          </div>
          <div className="acct-actions">
            {showBackToConsolidated && (
              <button type="button" className="sb-item" onClick={backToConsolidated}>
                <Icon name="chevronLeft" size={16} />
                <span>Volver al consolidado</span>
              </button>
            )}
            <button type="button" className="sb-item" onClick={goSettings}>
              <Icon name="settings" size={16} />
              <span>Configuración</span>
            </button>
            <button type="button" className="sb-item" onClick={doLogout}>
              <Icon name="logout" size={16} />
              <span>Cerrar sesión</span>
            </button>
          </div>
        </div>
      )}
      <button
        type="button"
        className="sb-bottom acct-trigger"
        aria-haspopup="dialog"
        aria-expanded={open ? 'true' : 'false'}
        onClick={() => setOpen(v => !v)}
        title="Mi cuenta"
      >
        <span className="av">{initialsFrom(account)}</span>
        <div className="who">
          <b>{name}</b>
          <span>{contextLine(account, activeBranch)}</span>
        </div>
        <Icon name="chevronDown" size={14} />
      </button>
    </div>
  );
}

export function Sidebar({ active, onNav, isOpen, onClose, account }) {
  const items = [
    { id: 'dashboard',  icon: 'home',     label: 'Inicio' },
    { id: 'calendar',   icon: 'calendar', label: 'Calendario' },
    { id: 'properties', icon: 'building', label: 'Propiedades' },
    { id: 'clients',    icon: 'users',    label: 'Clientes' },
    { id: 'cobranzas',  icon: 'money',    label: 'Cobranzas' },
    { id: 'website',    icon: 'grid',     label: 'Mi sitio web' },
    { id: 'faqs',       icon: 'msg',      label: 'FAQ' },
    { id: 'chats',      icon: 'whatsapp', label: 'Chats' },
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
        <button className="sb-close" onClick={onClose} aria-label="Cerrar menú">
          <Icon name="chevronLeft" size={20} />
        </button>
        <div className="sb-brand">
          <img src="/logo.svg" alt="InmuebleBot" />
        </div>
        <nav className="sb-nav" aria-label="Navegación principal">
          <div className="sb-section">Principal</div>
          {items.map(it => (
            <button key={it.id}
                 type="button"
                 className={`sb-item ${active === it.id ? 'active' : ''}`}
                 title={it.label}
                 aria-current={active === it.id ? 'page' : undefined}
                 onClick={() => handleNav(it.id)}>
              <Icon name={it.icon} size={16} />
              <span>{it.label}</span>
              {it.badge && <span className="badge">{it.badge}</span>}
            </button>
          ))}
          {more.map(it => (
            <button key={it.id}
                 type="button"
                 className={`sb-item ${active === it.id ? 'active' : ''}`}
                 title={it.label}
                 aria-current={active === it.id ? 'page' : undefined}
                 onClick={() => handleNav(it.id)}>
              <Icon name={it.icon} size={16} />
              <span>{it.label}</span>
            </button>
          ))}
          <div className="sb-section">Sistema</div>
          {account?.scope === 'org' && (
            <button type="button" className={`sb-item ${active === 'sucursales' ? 'active' : ''}`} title="Sucursales" aria-current={active === 'sucursales' ? 'page' : undefined} onClick={() => handleNav('sucursales')}>
              <Icon name="building" size={16} />
              <span>Sucursales</span>
            </button>
          )}
          {account?.scope === 'org' && (
            <button type="button" className={`sb-item ${active === 'reportes' ? 'active' : ''}`} title="Reportes" aria-current={active === 'reportes' ? 'page' : undefined} onClick={() => handleNav('reportes')}>
              <Icon name="activity" size={16} />
              <span>Reportes</span>
            </button>
          )}
          {(account?.account?.role === 'owner' || account?.account?.role === 'admin' || account?.account?.role === 'superadmin') && (
            <button type="button" className={`sb-item ${active === 'equipos' ? 'active' : ''}`} title="Equipos" aria-current={active === 'equipos' ? 'page' : undefined} onClick={() => handleNav('equipos')}>
              <Icon name="users" size={16} />
              <span>Equipos</span>
            </button>
          )}
          <button type="button" className={`sb-item ${active === 'settings' ? 'active' : ''}`} title="Configuración" aria-current={active === 'settings' ? 'page' : undefined} onClick={() => handleNav('settings')}>
            <Icon name="settings" size={16} />
            <span>Configuración</span>
          </button>
        </nav>
        <AccountMenu onNav={onNav} />
      </aside>
    </>
  );
}

// ── Config de notificaciones por tipo ─────────────────────────────────────────
const NOTIF_TYPES = {
  visit_scheduled:   { icon: 'calendarCheck',   color: '#155f6f', tint: '#eaf3f5' },
  visit_rescheduled: { icon: 'calendarRefresh', color: '#b07d12', tint: '#fdf5e6' },
  visit_cancelled:   { icon: 'calendarX',       color: '#b53b3b', tint: '#fbecec' },
  call_scheduled:    { icon: 'phone',           color: '#3a5fa8', tint: '#ecf0f8' },
  handoff_requested: { icon: 'headset',         color: '#b53b3b', solid: true },
  new_lead:          { icon: 'userPlus',        color: '#6b4d99', tint: '#f1eef7' },
  lead_qualified:    { icon: 'star',            color: '#3d8b4f', tint: '#ecf6ee' },
  bot_error:         { icon: 'alert',           color: '#8b919a', tint: '#f5f6f7', muted: true },
};

function NotifBadge({ type, size = 32, radius = 9 }) {
  const t = NOTIF_TYPES[type];
  if (!t) return null;
  const glyph = Math.round(size * 0.52);
  const bg = t.solid ? t.color : t.tint;
  const fg = t.solid ? '#fff' : t.color;
  return (
    <span style={{
      width: size, height: size, borderRadius: radius, background: bg,
      color: fg, display: 'inline-flex', alignItems: 'center',
      justifyContent: 'center', flexShrink: 0,
      boxShadow: t.solid ? 'none' : `inset 0 0 0 1px ${t.color}1f`,
    }}>
      <Icon name={t.icon} size={glyph} stroke={1.6} />
    </span>
  );
}

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
  const deleteRead = useDeleteReadNotifications();

  const notifications = data?.notifications ?? [];
  const unread = data?.unread_count ?? 0;
  const hasRead = notifications.some(n => n.read);

  return (
    <div className="notif-panel" role="dialog" aria-label="Notificaciones" onClick={e => e.stopPropagation()}>
      <div className="notif-header">
        <span className="notif-title">Notificaciones {unread > 0 && <span className="notif-badge-sm">{unread}</span>}</span>
        <div style={{display:'flex',gap:4,alignItems:'center'}}>
          {unread > 0 && (
            <button className="notif-mark-all" onClick={() => markAll.mutate()}>
              Marcar todo leído
            </button>
          )}
          {hasRead && (
            <button className="notif-mark-all" style={{color:'var(--danger-500)'}} onClick={() => deleteRead.mutate()}>
              Eliminar leídas
            </button>
          )}
        </div>
      </div>

      <div className="notif-list">
        {isLoading && <div className="notif-empty">Cargando...</div>}
        {!isLoading && notifications.length === 0 && (
          <div className="notif-empty">Sin notificaciones</div>
        )}
        {notifications.map(n => (
          <div key={n.id} className={`notif-item ${n.read ? 'read' : 'unread'}`}>
            <button
              type="button"
              className="notif-item-btn"
              onClick={() => {
                if (!n.read) markRead.mutate(n.id);
                if (onAction) { onAction(n); onClose(); }
              }}
            >
              <span className="notif-icon"><NotifBadge type={NOTIF_TYPES[n.type] ? n.type : 'bot_error'} /></span>
              <div className="notif-content">
                <div className="notif-item-title">{n.title}</div>
                {n.body && <div className="notif-item-body">{n.body}</div>}
                <div className="notif-time">{timeAgo(n.created_at)}</div>
              </div>
            </button>
            <button
              className="notif-delete"
              title="Eliminar"
              aria-label={`Eliminar notificación: ${n.title}`}
              onClick={e => { e.stopPropagation(); deleteNotif.mutate(n.id); }}
            >×</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Selector de sucursal (solo dueño de org Enterprise) ───────────────────────
function BranchSelector() {
  const { me, activeBranch, selectBranch } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  if (me?.scope !== 'org') return null;
  const branches = me.branches || [];
  const current = activeBranch ? branches.find(b => b.id === activeBranch) : null;
  const label = current ? current.name : 'Todas las sucursales';

  const choose = (id) => { selectBranch(id); setOpen(false); };

  return (
    <div className="branch-selector" ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, maxWidth: 220 }}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(v => !v)}
        title="Cambiar de sucursal"
      >
        <Icon name="building" size={16} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
        <Icon name="chevronDown" size={14} />
      </button>
      {open && (
        <div
          role="listbox"
          className="notif-panel"
          style={{ left: 0, right: 'auto', minWidth: 240, padding: 6 }}
          onClick={e => e.stopPropagation()}
        >
          <button
            type="button"
            className={`sb-item ${!activeBranch ? 'active' : ''}`}
            style={{ width: '100%' }}
            onClick={() => choose(null)}
          >
            <Icon name="grid" size={16} />
            <span>Todas las sucursales</span>
          </button>
          {branches.map(b => (
            <button
              key={b.id}
              type="button"
              className={`sb-item ${activeBranch === b.id ? 'active' : ''}`}
              style={{ width: '100%' }}
              onClick={() => choose(b.id)}
            >
              <Icon name="building" size={16} />
              <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.name}</span>
              <span
                title={b.wa_connected ? 'WhatsApp conectado' : 'Sin WhatsApp'}
                style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                         background: b.wa_connected ? 'var(--success-500, #16a34a)' : 'var(--border-300, #d0d5dd)' }}
              />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Topbar({ onMenuToggle, onNotifAction, theme, onToggleTheme, account, onLogout }) {
  const [open, setOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
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
      <BranchSelector />
      <div className="tb-spacer" />
      {onToggleTheme && (
        <button
          type="button"
          className="tb-icon"
          title={theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}
          aria-label={theme === 'dark' ? 'Activar modo claro' : 'Activar modo oscuro'}
          onClick={onToggleTheme}
        >
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={22} />
        </button>
      )}
      <div className="tb-notif-wrap" ref={ref}>
        <button
          type="button"
          className="tb-icon"
          title="Notificaciones"
          aria-label={`Notificaciones${unread > 0 ? `, ${unread} sin leer` : ''}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(v => !v)}
          onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }}
        >
          <Icon name="bell" size={24} />
          {unread > 0 && <span className="dot" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
        </button>
        {open && <NotificationPanel onClose={() => setOpen(false)} onAction={onNotifAction} />}
      </div>
      <button
        type="button"
        className="tb-icon"
        title="Reportar un error"
        aria-label="Reportar un error"
        aria-haspopup="dialog"
        onClick={() => setReportOpen(true)}
      >
        <Icon name="alert" size={22} />
      </button>
      <button type="button" className="tb-icon" title="Ayuda" aria-label="Ayuda">
        <Icon name="info" size={24} />
      </button>
      {reportOpen && <ReportErrorModal onClose={() => setReportOpen(false)} />}
      <span
        className="tb-avatar"
        title={account?.account?.email || 'Mi cuenta'}
        aria-hidden="true"
      >
        {initialsFrom(account)}
      </span>
      {onLogout && (
        <button
          type="button"
          className="tb-icon"
          title="Cerrar sesión"
          aria-label="Cerrar sesión"
          onClick={onLogout}
        >
          <Icon name="logout" size={22} />
        </button>
      )}
    </header>
  );
}

import React from 'react';
import { Icon, Button } from './Primitives';

export function Sidebar({ active, onNav }) {
  const items = [
    { id: 'dashboard',  icon: 'home',     label: 'Inicio' },
    { id: 'calendar',   icon: 'calendar', label: 'Calendario' },
    { id: 'properties', icon: 'building', label: 'Propiedades' },
    { id: 'clients',    icon: 'users',    label: 'Clientes' },
  ];
  const more = [
    { id: 'documents',  icon: 'folder',   label: 'Documentos' },
  ];
  return (
    <aside className="sb">
      <div className="sb-brand">
        <Icon name="building" size={18} style={{ color: 'var(--accent-500)' }} />
        <span>InmuebleBot</span>
      </div>
      <div className="sb-section">Principal</div>
      {items.map(it => (
        <div key={it.id}
             className={`sb-item ${active === it.id ? 'active' : ''}`}
             onClick={() => onNav(it.id)}>
          <Icon name={it.icon} size={16} />
          <span>{it.label}</span>
          {it.badge && <span className="badge">{it.badge}</span>}
        </div>
      ))}
      {more.map(it => (
        <div key={it.id}
             className={`sb-item ${active === it.id ? 'active' : ''}`}
             onClick={() => onNav(it.id)}>
          <Icon name={it.icon} size={16} />
          <span>{it.label}</span>
        </div>
      ))}
      <div className="sb-section">Sistema</div>
      <div className={`sb-item ${active === 'settings' ? 'active' : ''}`} onClick={() => onNav('settings')}>
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
  );
}

export function Topbar({ onNew }) {
  return (
    <header className="tb">
      <div className="tb-search">
        <Icon name="search" size={14} />
        <input placeholder="Buscar propiedad, contrato, cliente..." />
      </div>
      <div className="tb-spacer" />
      <Button kind="primary" icon="plus" size="sm" onClick={onNew}>Nuevo</Button>
      <div className="tb-divider"></div>
      <span className="tb-icon" title="Notificaciones">
        <Icon name="bell" size={16} />
        <span className="dot" />
      </span>
      <span className="tb-icon" title="Ayuda">
        <Icon name="info" size={16} />
      </span>
      <span className="tb-avatar" title="María Pereyra">MP</span>
    </header>
  );
}

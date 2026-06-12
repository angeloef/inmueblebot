import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

// ── Mapeo vista ↔ URL ────────────────────────────────────────────────────────
const VIEW_TO_PATH = {
  dashboard:  '/dashboard/inicio',
  calendar:   '/dashboard/calendario',
  properties: '/dashboard/propiedades',
  clients:    '/dashboard/clientes',
  cobranzas:  '/dashboard/cobranzas',
  website:    '/dashboard/sitio-web',
  faqs:       '/dashboard/faqs',
  chats:      '/dashboard/chats',
  documents:  '/dashboard/documentos',
  equipos:    '/dashboard/equipos',
  settings:   '/dashboard/configuracion',
};

const PATH_TO_VIEW = Object.fromEntries(
  Object.entries(VIEW_TO_PATH).map(([v, p]) => [p, v])
);
PATH_TO_VIEW['/dashboard'] = 'dashboard';
PATH_TO_VIEW['/'] = 'dashboard';

import { Sidebar, Topbar } from './Shell';
import { useAuth } from './auth';
import { useTheme } from './useTheme';
import { ToastStack, pushToast } from './Primitives';
import { EventPopover } from './EventPopover';
import { useUpdateEvent, useDeleteEvent } from './api';
import Dashboard from './Dashboard';
import Calendar from './Calendar';
import Properties from './Properties';
import Clients from './Clients';
import Cobranzas from './Cobranzas';
import FAQs from './FAQs';
import Chats from './Chats';
import Config from './Config'
import Equipos from './Equipos';
import Website from './Website';

// ── Notification type → destination ─────────────────────────────────────────
const NOTIF_VISIT_TYPES  = new Set(['visit_scheduled', 'visit_rescheduled', 'visit_cancelled', 'call_scheduled']);
const NOTIF_CLIENT_TYPES = new Set(['new_lead', 'lead_qualified', 'handoff_requested']);

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { me, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const [active, setActive] = useState(
    () => PATH_TO_VIEW[location.pathname] ?? 'dashboard'
  );
  const [menuOpen, setMenuOpen] = useState(false);

  // Standard cross-view navigation state
  const [clientToOpen, setClientToOpen]   = useState(null);
  const [propertyToOpen, setPropertyToOpen] = useState(null);
  const [globalPopover, setGlobalPopover] = useState(null);

  // Notification-driven navigation state
  const [calEventId, setCalEventId] = useState(null);
  const [clientPhone, setClientPhone] = useState(null);

  const updateEventMut = useUpdateEvent();
  const deleteEventMut = useDeleteEvent();

  useEffect(() => {
    const query = window.matchMedia('(min-width: 769px)');
    const handler = (e) => { if (e.matches) setMenuOpen(false); };
    query.addEventListener('change', handler);
    return () => query.removeEventListener('change', handler);
  }, []);

  useEffect(() => {
    const view = PATH_TO_VIEW[location.pathname];
    if (view && view !== active) setActive(view);
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Core navigation ───────────────────────────────────────────────────────
  const navTo = (view) => {
    setMenuOpen(false);
    setGlobalPopover(null);
    setClientToOpen(null);
    setPropertyToOpen(null);
    setCalEventId(null);
    setClientPhone(null);
    setActive(view);
    const path = VIEW_TO_PATH[view];
    if (path && location.pathname !== path) navigate(path);
  };

  const openClient = (client) => {
    setClientPhone(null);
    setClientToOpen(client);
    setActive('clients');
    const path = VIEW_TO_PATH['clients'];
    if (path && location.pathname !== path) navigate(path);
  };

  const openProperty = (prop) => {
    setPropertyToOpen(prop);
    setActive('properties');
    const path = VIEW_TO_PATH['properties'];
    if (path && location.pathname !== path) navigate(path);
  };

  const openEvent = (event, rect) => {
    setGlobalPopover({ event, anchor: rect });
  };

  // ── Notification click handler ─────────────────────────────────────────────
  const handleNotifAction = (notif) => {
    const meta = notif.metadata ?? {};

    if (NOTIF_VISIT_TYPES.has(notif.type)) {
      setCalEventId(meta.event_id ?? null);
      setClientToOpen(null);
      setClientPhone(null);
      setPropertyToOpen(null);
      setGlobalPopover(null);
      setActive('calendar');
      const path = VIEW_TO_PATH['calendar'];
      if (path && location.pathname !== path) navigate(path);

    } else if (NOTIF_CLIENT_TYPES.has(notif.type)) {
      setCalEventId(null);
      setClientToOpen(null);
      setClientPhone(notif.phone ?? null);
      setPropertyToOpen(null);
      setGlobalPopover(null);
      setActive('clients');
      const path = VIEW_TO_PATH['clients'];
      if (path && location.pathname !== path) navigate(path);

    } else {
      navTo('dashboard');
    }
  };

  const handleGlobalCancel = (e) => {
    updateEventMut.mutate({ ...e, status: 'cancelled' });
    setGlobalPopover(null);
    pushToast({ text: 'Visita cancelada.', kind: 'danger' });
  };

  const handleGlobalDelete = (e) => {
    deleteEventMut.mutate(e.id);
    setGlobalPopover(null);
    pushToast({ text: 'Evento eliminado.', kind: 'danger' });
  };

  return (
    <div className="app">
      <Sidebar active={active} onNav={navTo} isOpen={menuOpen} onClose={() => setMenuOpen(false)} account={me} />
      <div className="main">
        <Topbar onMenuToggle={() => setMenuOpen(v => !v)} onNotifAction={handleNotifAction} theme={theme} onToggleTheme={toggleTheme} account={me} onLogout={logout} />
        <div className="canvas">

          {active === 'dashboard' && (
            <Dashboard onNav={navTo} onOpenEvent={openEvent} onOpenClient={openClient} />
          )}

          {active === 'calendar' && (
            <Calendar
              key={calEventId ?? 'cal'}
              onOpenClient={openClient}
              onOpenProperty={openProperty}
              initialEventId={calEventId}
            />
          )}

          {active === 'properties' && (
            <Properties onOpenClient={openClient} initialProperty={propertyToOpen} />
          )}

          {active === 'clients' && (
            <Clients
              key={clientPhone ?? 'cli'}
              initialClient={clientToOpen}
              initialPhone={clientPhone}
              onOpenProperty={openProperty}
              onOpenEvent={openEvent}
            />
          )}

          {active === 'cobranzas' && <Cobranzas />}

          {active === 'website' && <Website />}

          {active === 'faqs' && <FAQs />}

          {active === 'chats' && <Chats />}

          {active === 'documents' && (
            <div className="page-view">
              <div className="page-h">
                <h1>Documentos</h1>
                <div className="sub">Próximamente</div>
              </div>
            </div>
          )}

          {active === 'equipos' && <Equipos />}

          {active === 'settings' && <Config />}

        </div>
      </div>
      {globalPopover && (
        <EventPopover
          event={globalPopover.event}
          anchor={globalPopover.anchor}
          onClose={() => setGlobalPopover(null)}
          onEdit={() => setGlobalPopover(null)}
          onReschedule={() => setGlobalPopover(null)}
          onCancel={handleGlobalCancel}
          onDelete={handleGlobalDelete}
          onOpenClient={openClient}
          onOpenProperty={openProperty}
        />
      )}
      <ToastStack />
    </div>
  );
}

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
  sucursales: '/dashboard/sucursales',
  reportes:   '/dashboard/reportes',
  equipos:    '/dashboard/equipos',
  settings:   '/dashboard/configuracion',
};

const PATH_TO_VIEW = Object.fromEntries(
  Object.entries(VIEW_TO_PATH).map(([v, p]) => [p, v])
);
PATH_TO_VIEW['/dashboard'] = 'dashboard';
PATH_TO_VIEW['/'] = 'dashboard';

import { Sidebar, Topbar, TrialBanner, UpgradeModal } from './Shell';
import { VIEW_GATES, FEATURE_PREVIEWS, hasFeature, dispatchUpgradeEvent } from './featureGates';
import { useAuth } from './auth';
import { useTheme } from './useTheme';
import { ToastStack, pushToast, Icon } from './Primitives';
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
import Sucursales from './Sucursales';
import Consolidated from './Consolidated';
import DocumentsView from './DocumentsView';
import Reportes from './Reportes';

// ── Feature preview (guard de ruta + upsell, plan 39) ────────────────────────
// Página real que reemplaza el dead-end: explica qué resuelve la sección y lleva
// a planes/ventas. NO monta la feature real → no reintroduce el bypass del plan 10.
// Genérica: el contenido por feature vive en FEATURE_PREVIEWS (featureGates.js).
function FeaturePreview({ gate, onGoToPlans }) {
  const preview = FEATURE_PREVIEWS[gate.feature];
  const isEnterprise = gate.required === 'enterprise';
  const ctaLabel = isEnterprise ? 'Hablar con ventas' : 'Ver planes';
  const title = preview?.title ?? 'Función de plan superior';

  return (
    <section className="feat-preview" aria-labelledby="feat-preview-title">
      <div className="feat-preview__card">
        <span className="feat-preview__badge">
          <Icon name="lock" size={13} aria-hidden="true" />
          Disponible en plan {gate.required}
        </span>
        <h1 id="feat-preview-title" className="feat-preview__title">{title}</h1>
        {preview?.problem && <p className="feat-preview__lede">{preview.problem}</p>}
        {preview?.bullets?.length > 0 && (
          <ul className="feat-preview__list">
            {preview.bullets.map((b) => (
              <li key={b} className="feat-preview__item">
                <Icon name="check" size={16} aria-hidden="true" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          className="btn btn-primary feat-preview__cta"
          onClick={() => {
            if (!isEnterprise) dispatchUpgradeEvent(gate.feature, gate.required);
            onGoToPlans();
          }}
        >
          {ctaLabel}
        </button>
      </div>
    </section>
  );
}

// ── Notification type → destination ─────────────────────────────────────────
const NOTIF_VISIT_TYPES  = new Set(['visit_scheduled', 'visit_rescheduled', 'visit_cancelled', 'call_scheduled']);
const NOTIF_CLIENT_TYPES = new Set(['new_lead', 'lead_qualified', 'handoff_requested']);

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { me, logout, activeBranch } = useAuth();
  const { theme, toggleTheme } = useTheme();

  // Dueño de org en modo "Todas las sucursales" (sin sucursal activa) → la Inicio
  // muestra el consolidado en vez del dashboard de una sola inmobiliaria.
  const showConsolidated = me?.scope === 'org' && !activeBranch;

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

  // "Agendar" desde el perfil de un cliente → abre el Calendario con un evento
  // nuevo y el cliente precargado.
  const [agendaClientId, setAgendaClientId] = useState(null);

  // Upgrade modal: abierto cuando el interceptor 402 dispara subscription:required
  const [upgradeDetail, setUpgradeDetail] = useState(null);

  useEffect(() => {
    const handler = (e) => setUpgradeDetail(e.detail ?? {});
    window.addEventListener('subscription:required', handler);
    return () => window.removeEventListener('subscription:required', handler);
  }, []);

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
    setAgendaClientId(null);
    setActive(view);
    const path = VIEW_TO_PATH[view];
    if (path && location.pathname !== path) navigate(path);
  };

  const goToPlans = () => navTo('settings');

  const openAgenda = (client) => {
    setCalEventId(null);
    setAgendaClientId(client?.id ?? null);
    setActive('calendar');
    const path = VIEW_TO_PATH['calendar'];
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
        <TrialBanner onGoToPlans={goToPlans} />
        <div className="canvas">

          {active === 'dashboard' && (
            showConsolidated
              ? <Consolidated onNav={navTo} />
              : <Dashboard onNav={navTo} onOpenEvent={openEvent} onOpenClient={openClient} />
          )}

          {active === 'calendar' && (
            <Calendar
              key={calEventId ?? (agendaClientId ? `agenda-${agendaClientId}` : 'cal')}
              onOpenClient={openClient}
              onOpenProperty={openProperty}
              initialEventId={calEventId}
              initialNewEventClientId={agendaClientId}
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
              onAgenda={openAgenda}
            />
          )}

          {active === 'cobranzas' && (
            hasFeature(me, VIEW_GATES.cobranzas.feature)
              ? <Cobranzas />
              : <FeaturePreview gate={VIEW_GATES.cobranzas} onGoToPlans={goToPlans} />
          )}

          {active === 'website' && (
            hasFeature(me, VIEW_GATES.website.feature)
              ? <Website />
              : <FeaturePreview gate={VIEW_GATES.website} onGoToPlans={goToPlans} />
          )}

          {active === 'faqs' && <FAQs />}

          {active === 'chats' && <Chats />}

          {active === 'documents' && (
            hasFeature(me, VIEW_GATES.documents.feature)
              ? <DocumentsView />
              : <FeaturePreview gate={VIEW_GATES.documents} onGoToPlans={goToPlans} />
          )}

          {active === 'sucursales' && <Sucursales />}

          {active === 'reportes' && (
            hasFeature(me, VIEW_GATES.reportes.feature)
              ? <Reportes />
              : <FeaturePreview gate={VIEW_GATES.reportes} onGoToPlans={goToPlans} />
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
      {upgradeDetail !== null && (
        <UpgradeModal
          detail={upgradeDetail}
          onClose={() => setUpgradeDetail(null)}
          onGoToPlans={goToPlans}
        />
      )}
    </div>
  );
}

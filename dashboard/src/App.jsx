import React, { useState, useEffect } from 'react';
import { Sidebar, Topbar } from './Shell';
import { ToastStack, pushToast } from './Primitives';
import { EventPopover } from './EventPopover';
import { useUpdateEvent, useDeleteEvent } from './api';
import Dashboard from './Dashboard';
import Calendar from './Calendar';
import Properties from './Properties';
import Clients from './Clients';
import FAQs from './FAQs';

export default function App() {
  const [active, setActive] = useState('dashboard');
  const [menuOpen, setMenuOpen] = useState(false);
  const [clientToOpen, setClientToOpen] = useState(null);
  const [propertyToOpen, setPropertyToOpen] = useState(null);
  const [globalPopover, setGlobalPopover] = useState(null);

  const updateEventMut = useUpdateEvent();
  const deleteEventMut = useDeleteEvent();

  // Cerrar sidebar automáticamente al pasar a desktop
  useEffect(() => {
    const query = window.matchMedia('(min-width: 769px)');
    const handler = (e) => { if (e.matches) setMenuOpen(false); };
    query.addEventListener('change', handler);
    return () => query.removeEventListener('change', handler);
  }, []);

  const navTo = (view) => {
    setMenuOpen(false);
    setGlobalPopover(null);
    setClientToOpen(null);
    setPropertyToOpen(null);
    setActive(view);
  };

  const openClient = (client) => {
    setClientToOpen(client);
    setActive('clients');
  };

  const openProperty = (prop) => {
    setPropertyToOpen(prop);
    setActive('properties');
  };

  const openEvent = (event, rect) => {
    setGlobalPopover({ event, anchor: rect });
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
      <Sidebar active={active} onNav={navTo} isOpen={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="main">
        <Topbar onMenuToggle={() => setMenuOpen(v => !v)} />
        <div className="canvas">
          {active === 'dashboard' && (
            <Dashboard onNav={navTo} onOpenEvent={openEvent} onOpenClient={openClient} />
          )}
          {active === 'calendar' && <Calendar onOpenClient={openClient} onOpenProperty={openProperty} />}
          {active === 'properties' && <Properties onOpenClient={openClient} initialProperty={propertyToOpen} />}
          {active === 'clients' && (
            <Clients
              initialClient={clientToOpen}
              onOpenProperty={() => setActive('properties')}
              onOpenEvent={openEvent}
            />
          )}
          {active === 'faqs' && <FAQs />}
          {active === 'documents' && (
            <div className="page-view">
              <div className="page-h">
                <h1>Documentos</h1>
                <div className="sub">Próximamente</div>
              </div>
            </div>
          )}
          {active === 'settings' && (
            <div className="page-view">
              <div className="page-h">
                <h1>Configuración</h1>
                <div className="sub">Próximamente</div>
              </div>
            </div>
          )}
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

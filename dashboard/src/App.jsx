import React, { useState } from 'react';
import { Sidebar, Topbar } from './Shell';
import { ToastStack, pushToast } from './Primitives';
import { EventPopover } from './EventPopover';
import { useUpdateEvent, useDeleteEvent } from './api';
import Dashboard from './Dashboard';
import Calendar from './Calendar';
import Properties from './Properties';
import Clients from './Clients';

export default function App() {
  const [active, setActive] = useState('dashboard');
  const [clientToOpen, setClientToOpen] = useState(null);
  const [globalPopover, setGlobalPopover] = useState(null);

  const updateEventMut = useUpdateEvent();
  const deleteEventMut = useDeleteEvent();

  const navTo = (view) => {
    setGlobalPopover(null);
    setActive(view);
  };

  const openClient = (client) => {
    setClientToOpen(client);
    setActive('clients');
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
      <Sidebar active={active} onNav={navTo} />
      <div className="main">
        <Topbar onNew={() => pushToast({ text: 'Usá el calendario para crear eventos.' })} />
        <div className="canvas">
          {active === 'dashboard' && (
            <Dashboard onNav={navTo} onOpenEvent={openEvent} onOpenClient={openClient} />
          )}
          {active === 'calendar' && <Calendar />}
          {active === 'properties' && <Properties onOpenClient={openClient} />}
          {active === 'clients' && (
            <Clients
              initialClient={clientToOpen}
              onOpenProperty={() => setActive('properties')}
              onOpenEvent={openEvent}
            />
          )}
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
          onOpenProperty={() => setActive('properties')}
        />
      )}
      <ToastStack />
    </div>
  );
}

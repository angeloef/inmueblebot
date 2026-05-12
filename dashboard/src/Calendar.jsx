import React, { useState } from 'react';
import { Button, IconButton, pushToast } from './Primitives';
import { parseTime, padDate, fmtTime12 } from './data';
import { useEvents, useCreateEvent, useUpdateEvent, useDeleteEvent, useCalendarStatus, useProperties, useClients } from './api';
import { EventPopover, EventEditor } from './EventPopover';

const DOWS = ['DOM','LUN','MAR','MIÉ','JUE','VIE','SÁB'];
const KIND_LABEL = { visit: 'Visita', call: 'Llamada' };

/** Devuelve true si fecha+hora ya pasaron (margen 1 min). */
function isPast(dateISO, timeStr = '00:00') {
  if (!dateISO) return false;
  return new Date(`${dateISO}T${timeStr}:00`).getTime() < Date.now() - 60_000;
}

const ROW_H = 56;
const GUTTER_W = 60;

function snapHours(h, snapMin = 15) {
  const factor = 60 / snapMin;
  return Math.max(0, Math.min(23.75, Math.round(h * factor) / factor));
}

function hoursToStr(h) {
  const totalMin = Math.round(h * 60);
  const hr = Math.floor(totalMin / 60) % 24;
  const min = totalMin % 60;
  return `${String(hr).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
}

function buildMonthMatrix(year, month) {
  const first = new Date(year, month, 1);
  const startDow = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrev = new Date(year, month, 0).getDate();
  const cells = [];
  for (let i = 0; i < startDow; i++) {
    const d = daysInPrev - startDow + 1 + i;
    cells.push({ y: month === 0 ? year - 1 : year, m: month === 0 ? 12 : month, d, other: true });
  }
  for (let i = 1; i <= daysInMonth; i++) {
    cells.push({ y: year, m: month + 1, d: i, other: false });
  }
  while (cells.length < 35) {
    const i = cells.length - daysInMonth - startDow + 1;
    cells.push({ y: month === 11 ? year + 1 : year, m: month === 11 ? 1 : month + 2, d: i, other: true });
  }
  return cells.map(c => ({ ...c, iso: `${c.y}-${String(c.m).padStart(2, '0')}-${String(c.d).padStart(2, '0')}` }));
}

function MonthView({ events, onEventClick, today, onDayClick, year, month }) {
  const cells = buildMonthMatrix(year, month);
  return (
    <div className="cal-month">
      {DOWS.map(d => <div key={d} className="cal-dow">{d}</div>)}
      {cells.map((c, i) => {
        const dayEvents = events.filter(e => e.date === c.iso).sort((a, b) => a.start.localeCompare(b.start));
        const isToday = c.iso === today;
        const isDayPast = c.iso < today;
        return (
          <div key={i} className={`cal-day ${c.other ? 'other' : ''} ${isToday ? 'today' : ''} ${isDayPast ? 'past' : ''}`}
               style={isDayPast ? { cursor: 'default' } : undefined}
               onClick={() => !isDayPast && onDayClick && onDayClick(c.iso)}>
            <span className="num">{c.d}</span>
            {dayEvents.slice(0, 4).map(e => {
              const label = KIND_LABEL[e.kind] ?? e.kind;
              const sub   = e.title ? e.title.replace(/^(Visita|Llamada)\s·\s/, '').trim() : '';
              return (
                <span key={e.id}
                      className={`cal-event ev-${e.kind} ${e.status === 'cancelled' ? 'cancelled' : ''}`}
                      onClick={(ev) => { ev.stopPropagation(); onEventClick(e, ev.currentTarget.getBoundingClientRect()); }}
                      title={e.title || label}>
                  <span className="t">{fmtTime12(e.start)}</span> <b>{label}</b>{sub ? ` · ${sub}` : ''}
                </span>
              );
            })}
            {dayEvents.length > 4 && <span className="cal-more">+{dayEvents.length - 4} más</span>}
          </div>
        );
      })}
    </div>
  );
}

function layoutDayEvents(dayEvents) {
  const evs = [...dayEvents].sort((a, b) => parseTime(a.start) - parseTime(b.start));
  const result = [];
  let cluster = [];
  let clusterEnd = 0;

  function flushCluster() {
    if (cluster.length === 0) return;
    const cols = [];
    const placements = cluster.map(e => {
      const s = parseTime(e.start);
      const en = parseTime(e.end);
      let col = 0;
      while (col < cols.length && cols[col] > s) col++;
      cols[col] = en;
      return { e, col };
    });
    const total = cols.length;
    placements.forEach(({ e, col }) => result.push({ ...e, _col: col, _total: total }));
    cluster = [];
    clusterEnd = 0;
  }

  evs.forEach(e => {
    const s = parseTime(e.start);
    const en = parseTime(e.end);
    if (cluster.length === 0 || s < clusterEnd) {
      cluster.push(e);
      clusterEnd = Math.max(clusterEnd, en);
    } else {
      flushCluster();
      cluster.push(e);
      clusterEnd = en;
    }
  });
  flushCluster();
  return result;
}

function TimeGrid({ days, events, onEventClick, today, view, onSlotInteract, onMoveEvent, tzLabel, properties, clients }) {
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const cols = days.length;
  const template = `${GUTTER_W}px repeat(${cols}, minmax(0, 1fr))`;

  const bodyRef = React.useRef(null);
  const gridRef = React.useRef(null);
  const dragRef = React.useRef(null);
  const [drag, setDrag] = React.useState(null);

  const now = new Date();
  const nowHour = now.getHours() + now.getMinutes() / 60;
  const todayCol = days.indexOf(today);

  React.useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 7 * ROW_H;
  }, [view]);

  function yToHours(clientY) {
    const r = gridRef.current ? gridRef.current.getBoundingClientRect() : null;
    return r ? (clientY - r.top) / ROW_H : 0;
  }

  function xToColIdx(clientX) {
    const r = gridRef.current ? gridRef.current.getBoundingClientRect() : null;
    if (!r) return 0;
    const colW = (r.width - GUTTER_W) / cols;
    return Math.max(0, Math.min(cols - 1, Math.floor((clientX - r.left - GUTTER_W) / colW)));
  }

  const onGridMouseDown = React.useCallback((e) => {
    if (e.button !== 0) return;
    if (e.target.closest && e.target.closest('.cal-tg-event')) return;
    const r = gridRef.current ? gridRef.current.getBoundingClientRect() : null;
    if (!r || e.clientX - r.left < GUTTER_W) return;
    e.preventDefault();

    const h = snapHours(yToHours(e.clientY));
    const colIdx = xToColIdx(e.clientX);

    dragRef.current = { type: 'create', startH: h, curH: h, col: colIdx, moved: false };
    setDrag({ ...dragRef.current });
  }, []);

  const onEventMouseDown = React.useCallback((e, ev) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();

    const colIdx = days.indexOf(ev.date);
    const startH = parseTime(ev.start);
    const endH = parseTime(ev.end);

    dragRef.current = {
      type: 'move',
      event: ev,
      startClientX: e.clientX,
      startClientY: e.clientY,
      moved: false,
      offsetH: yToHours(e.clientY) - startH,
      durationH: endH - startH,
      col: colIdx,
      curCol: colIdx,
      curStartH: startH,
      elemRect: e.currentTarget.getBoundingClientRect(),
    };
    setDrag({ ...dragRef.current });
  }, [days]);

  React.useEffect(() => {
    if (!drag) return;

    const handleMove = (e) => {
      const d = dragRef.current;
      if (!d) return;

      if (d.type === 'create') {
        const h = snapHours(yToHours(e.clientY));
        const newCol = xToColIdx(e.clientX);
        const moved = Math.abs(h - d.startH) >= 0.1;
        dragRef.current = { ...d, curH: h, col: newCol, moved };
        setDrag({ ...dragRef.current });

      } else if (d.type === 'move') {
        const didMove = !d.moved && (
          Math.abs(e.clientY - d.startClientY) > 6 ||
          Math.abs(e.clientX - d.startClientX) > 6
        );
        if (!didMove && !d.moved) return;
        const newStartH = snapHours(yToHours(e.clientY) - d.offsetH);
        const newCol = xToColIdx(e.clientX);
        dragRef.current = { ...d, curStartH: newStartH, curCol: newCol, moved: true };
        setDrag({ ...dragRef.current });
      }
    };

    const handleUp = (e) => {
      const d = dragRef.current;
      if (!d) return;
      dragRef.current = null;
      setDrag(null);

      if (d.type === 'create') {
        const h = snapHours(yToHours(e.clientY));
        const finalStart = snapHours(Math.min(d.startH, h));
        const rawEnd   = d.moved ? snapHours(Math.max(d.startH, h)) : d.startH + 1;
        const finalEnd = Math.max(finalStart + 0.25, Math.min(23.75, rawEnd));
        const date = days[Math.max(0, Math.min(cols - 1, xToColIdx(e.clientX)))];
        onSlotInteract && onSlotInteract(date, hoursToStr(finalStart), hoursToStr(finalEnd));

      } else if (d.type === 'move') {
        if (!d.moved) {
          onEventClick && onEventClick(d.event, d.elemRect);
        } else {
          const date = days[d.curCol];
          const newEndH = Math.min(23.75, d.curStartH + d.durationH);
          onMoveEvent && onMoveEvent(d.event, date, hoursToStr(d.curStartH), hoursToStr(newEndH));
        }
      }
    };

    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleUp);
    return () => {
      document.removeEventListener('mousemove', handleMove);
      document.removeEventListener('mouseup', handleUp);
    };
  }, [!!drag]); // eslint-disable-line react-hooks/exhaustive-deps

  const draggingId = drag && drag.type === 'move' ? drag.event.id : null;

  let ghostCreate = null;
  if (drag && drag.type === 'create') {
    const topH   = drag.moved ? Math.min(drag.startH, drag.curH) : drag.startH;
    const endH   = drag.moved ? Math.max(drag.startH, drag.curH) : drag.startH + 1;
    ghostCreate  = {
      col: drag.col,
      top: topH * ROW_H,
      height: Math.max(ROW_H * 0.25, (endH - topH) * ROW_H),
      labelStart: hoursToStr(topH),
      labelEnd: hoursToStr(endH),
    };
  }

  let ghostMove = null;
  if (drag && drag.type === 'move' && drag.moved) {
    ghostMove = {
      col: drag.curCol,
      top: drag.curStartH * ROW_H + 1,
      height: Math.max(18, drag.durationH * ROW_H - 2),
      event: drag.event,
      labelStart: hoursToStr(drag.curStartH),
      labelEnd: hoursToStr(Math.min(23.75, drag.curStartH + drag.durationH)),
    };
  }

  return (
    <div className={`cal-tg-wrap${drag ? ' is-dragging' : ''}`}>
      <div className="cal-tg-head" style={{ gridTemplateColumns: template }}>
        <div className="cal-tg-gmt">{tzLabel}</div>
        {days.map((d) => {
          const [yr, mo, dy] = d.split('-').map(Number);
          const dt = new Date(yr, mo - 1, dy);
          const isToday = d === today;
          return (
            <div key={d} className={`cal-tg-dow ${isToday ? 'today' : ''}`}>
              <span className="dlabel">{DOWS[dt.getDay()]}</span>
              <span className="dnum">{dy}</span>
            </div>
          );
        })}
      </div>

      <div className="cal-tg-body" ref={bodyRef}>
        <div className="cal-tg" ref={gridRef}
             style={{ gridTemplateColumns: template, gridTemplateRows: `repeat(${hours.length}, ${ROW_H}px)` }}
             onMouseDown={onGridMouseDown}>

          {hours.map((h, hi) => (
            <div key={`g-${h}`} className="cal-tg-gutter" style={{ gridRow: hi + 1, gridColumn: 1 }}>
              {hi === 0 ? '' : <span>{h < 12 ? h : h === 12 ? 12 : h - 12} {h < 12 ? 'AM' : 'PM'}</span>}
            </div>
          ))}

          {days.map((d, di) => (
            hours.map((h, hi) => (
              <div key={`c-${d}-${h}`}
                   className="cal-tg-cell"
                   style={{ gridColumn: di + 2, gridRow: hi + 1 }}>
                <span className="cal-tg-half" />
              </div>
            ))
          ))}

          {todayCol >= 0 && (
            <div className="cal-tg-now"
                 style={{ gridColumn: todayCol + 2, gridRow: '1 / -1', top: nowHour * ROW_H }}>
              <span className="dot" />
            </div>
          )}

          {days.map((d, di) => {
            const dayEvents = events.filter(ev => ev.date === d);
            const laid = layoutDayEvents(dayEvents);

            const colGhostCreate = ghostCreate && ghostCreate.col === di ? ghostCreate : null;
            const colGhostMove   = ghostMove   && ghostMove.col   === di ? ghostMove   : null;

            return (
              <div key={`col-${d}`}
                   style={{
                     gridColumn: di + 2,
                     gridRow: `1 / ${hours.length + 1}`,
                     position: 'relative',
                     pointerEvents: 'none',
                   }}>

                {laid.map(ev => {
                  const startF = parseTime(ev.start);
                  const endF = parseTime(ev.end);
                  const top = startF * ROW_H + 1;
                  const height = Math.max(18, (endF - startF) * ROW_H - 2);
                  const widthPct = 100 / ev._total;
                  const leftPct = ev._col * widthPct;
                  const rightPct = 100 - leftPct - widthPct;
                  const isBeingDragged = ev.id === draggingId;
                  return (
                    <div key={ev.id}
                         className={`cal-tg-event ev-${ev.kind} ${ev.status === 'cancelled' ? 'cancelled' : ''} ${height < 36 ? 'compact' : ''} ${isBeingDragged ? 'dragging' : ''}`}
                         style={{
                           top,
                           height,
                           left: `calc(${leftPct}% + 2px)`,
                           right: `calc(${rightPct}% + 2px)`,
                           width: 'auto',
                           pointerEvents: 'auto',
                         }}
                         onMouseDown={(me) => onEventMouseDown(me, ev)}>
                      <div className="et">
                        {ev.status === 'cancelled' ? <span className="cancel-prefix">Cancelado: </span> : null}
                        {(() => {
                          const label = KIND_LABEL[ev.kind] ?? ev.kind;
                          let sub = ev.title ? ev.title.replace(/^(Visita|Llamada)\s·\s/, '').trim() : '';
                          if (!sub) {
                            if (ev.kind === 'visit' && ev.propId) {
                              const p = properties.find(p => String(p.id) === String(ev.propId));
                              if (p) sub = p.addr ?? p.title ?? '';
                            } else if (ev.kind === 'call' && ev.clientId) {
                              const c = clients.find(c => c.id === ev.clientId);
                              if (c) sub = c.name ?? '';
                            }
                          }
                          return sub ? <>{label} <span style={{opacity:0.75}}>· {sub}</span></> : label;
                        })()}
                      </div>
                      <div className="es">{fmtTime12(ev.start)} – {fmtTime12(ev.end)}</div>
                    </div>
                  );
                })}

                {colGhostCreate && (
                  <div className="cal-tg-ghost ghost-create"
                       style={{
                         top: colGhostCreate.top,
                         height: colGhostCreate.height,
                         left: 4, right: 4, width: 'auto',
                         pointerEvents: 'none',
                       }}>
                    <span>{colGhostCreate.labelStart} – {colGhostCreate.labelEnd}</span>
                  </div>
                )}

                {colGhostMove && (
                  <div className={`cal-tg-ghost cal-tg-event ev-${colGhostMove.event.kind}`}
                       style={{
                         top: colGhostMove.top,
                         height: colGhostMove.height,
                         left: 4, right: 4, width: 'auto',
                         opacity: 0.88,
                         zIndex: 10,
                         pointerEvents: 'none',
                         boxShadow: '0 4px 14px rgba(0,0,0,0.18)',
                       }}>
                    <div className="et">{(() => { const e = colGhostMove.event; const label = KIND_LABEL[e.kind] ?? e.kind; const sub = e.title ? e.title.replace(/^(Visita|Llamada)\s·\s/, '').trim() : ''; return sub ? `${label} · ${sub}` : label; })()}</div>
                    <div className="es">{colGhostMove.labelStart} – {colGhostMove.labelEnd}</div>
                  </div>
                )}

              </div>
            );
          })}

        </div>
      </div>
    </div>
  );
}

export default function Calendar({ onOpenClient, onOpenProperty }) {
  const { data: events = [] }                 = useEvents();
  const createEventMut                        = useCreateEvent();
  const updateEventMut                        = useUpdateEvent();
  const deleteEventMut                        = useDeleteEvent();
  const { data: calStatus }                   = useCalendarStatus();
  const { data: properties = [] }             = useProperties();
  const { data: clients = [] }                = useClients();

  const tzLabel = calStatus?.label ?? 'GMT-3';

  const mobileQuery = window.matchMedia('(max-width: 768px)');
  const tabletQuery = window.matchMedia('(min-width: 769px) and (max-width: 1280px)');

  const [view, setView] = useState(() => {
    if (mobileQuery.matches) return 'day';
    if (tabletQuery.matches) return 'week';
    return 'month';
  });

  // Ajustar vista automáticamente al cambiar tamaño de ventana
  React.useEffect(() => {
    const handleMobile = (e) => { if (e.matches) setView('day'); };
    const handleTablet = (e) => {
      if (e.matches) {
        // Entrando a tablet: si estaba en mes, bajar a semana
        setView(v => v === 'month' ? 'week' : v);
      }
      // Saliendo de tablet (→ desktop): no forzar, dejar la vista actual
    };

    mobileQuery.addEventListener('change', handleMobile);
    tabletQuery.addEventListener('change', handleTablet);

    // Forzar en mount por si matchMedia tardó en evaluarse
    if (mobileQuery.matches) setView('day');
    else if (tabletQuery.matches) setView(v => v === 'month' ? 'week' : v);

    return () => {
      mobileQuery.removeEventListener('change', handleMobile);
      tabletQuery.removeEventListener('change', handleTablet);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const [popover, setPopover] = useState(null);
  const [editor, setEditor] = useState(null);
  const today = new Date().toISOString().slice(0, 10);

  const MONTH_NAMES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

  // Single navigation cursor — all views derive from this date
  const [navDate, setNavDate] = useState(() => new Date());

  const goBack = () => setNavDate(d => {
    const nd = new Date(d);
    if (view === 'month') nd.setMonth(nd.getMonth() - 1);
    else if (view === 'week') nd.setDate(nd.getDate() - 7);
    else nd.setDate(nd.getDate() - 1);
    return nd;
  });

  const goForward = () => setNavDate(d => {
    const nd = new Date(d);
    if (view === 'month') nd.setMonth(nd.getMonth() + 1);
    else if (view === 'week') nd.setDate(nd.getDate() + 7);
    else nd.setDate(nd.getDate() + 1);
    return nd;
  });

  const openEvent = (event, rect) => setPopover({ event, anchor: rect });
  const closePopover = () => setPopover(null);

  const handleEdit = (e) => { setPopover(null); setEditor({ event: e, mode: 'edit' }); };
  const handleReschedule = (e) => { setPopover(null); setEditor({ event: e, mode: 'reschedule' }); };
  const handleCancel = (e) => {
    updateEventMut.mutate({ ...e, status: 'cancelled' });
    setPopover(null);
    pushToast({ text: 'Visita cancelada — se notificó al cliente.', kind: 'danger' });
  };
  const handleDelete = (e) => {
    deleteEventMut.mutate(e.id);
    setPopover(null);
    pushToast({ text: 'Evento eliminado.', kind: 'danger' });
  };
  const handleSave = (form) => {
    const mode    = editor.mode;
    const eventId = editor.event?.id;
    setEditor(null);
    if (mode === 'create') {
      createEventMut.mutate(form, {
        onSuccess: () => pushToast({ text: 'Evento creado.' }),
        onError:   () => pushToast({ text: 'Error al crear el evento.', kind: 'danger' }),
      });
    } else {
      updateEventMut.mutate({ id: eventId, ...form }, {
        onSuccess: () => pushToast({ text: mode === 'reschedule' ? 'Evento reprogramado — cliente notificado.' : 'Cambios guardados.' }),
        onError:   () => pushToast({ text: 'Error al guardar los cambios.', kind: 'danger' }),
      });
    }
  };

  const handleSlotInteract = (date, start, end) => {
    if (isPast(date, start)) return;
    setEditor({
      mode: 'create',
      event: { title: 'Visita · ', kind: 'visit', date, start, end, agent: 'M. Pereyra', status: 'pending' },
    });
  };

  const handleMoveEvent = React.useCallback((event, newDate, newStart, newEnd) => {
    if (isPast(newDate, newStart)) {
      pushToast({ text: 'No se puede mover un evento al pasado.', kind: 'danger' });
      return;
    }
    updateEventMut.mutate({ ...event, date: newDate, start: newStart, end: newEnd }, {
      onSuccess: () => pushToast({ text: 'Evento movido.' }),
    });
  }, [updateEventMut]);

  // Derived values from navDate
  const navYear  = navDate.getFullYear();
  const navMonth = navDate.getMonth(); // 0-indexed

  const weekStart = new Date(navDate);
  weekStart.setDate(navDate.getDate() - navDate.getDay());
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const x = new Date(weekStart);
    x.setDate(weekStart.getDate() + i);
    return padDate(x.getFullYear(), x.getMonth() + 1, x.getDate());
  });

  const navDayISO = padDate(navDate.getFullYear(), navDate.getMonth() + 1, navDate.getDate());

  // Week label handles cross-month ranges (e.g. "29 abr – 5 may 2026")
  const weekLabelStart = weekDays[0];
  const weekLabelEnd   = weekDays[6];
  const wStartDate = new Date(weekLabelStart);
  const wEndDate   = new Date(weekLabelEnd);
  const weekLabel  = wStartDate.getMonth() === wEndDate.getMonth()
    ? `${wStartDate.getDate()} – ${wEndDate.getDate()} ${MONTH_NAMES[wEndDate.getMonth()]} ${wEndDate.getFullYear()}`
    : `${wStartDate.getDate()} ${MONTH_NAMES[wStartDate.getMonth()].slice(0,3)} – ${wEndDate.getDate()} ${MONTH_NAMES[wEndDate.getMonth()].slice(0,3)} ${wEndDate.getFullYear()}`;

  const navLabel = view === 'day'  ? `${navDate.getDate()} de ${MONTH_NAMES[navMonth]}, ${navYear}` :
                   view === 'week' ? weekLabel :
                   `${MONTH_NAMES[navMonth]} ${navYear}`;

  return (
    <div className="cal-page">
      <div className="page-h">
        <div>
          <h1>Calendario</h1>
          <div className="sub">Visitas, firmas, vencimientos y llamadas</div>
        </div>
        <div className="page-h-actions">
          <Button kind="primary" icon="plus" size="sm" onClick={() => setEditor({ mode: 'create', event: { title: 'Visita · ', kind: 'visit', date: today, start: '10:00', end: '11:00', agent: 'M. Pereyra', status: 'pending' } })}>Nuevo evento</Button>
        </div>
      </div>

      <div className="surface cal-surface">
        <div className="cal-toolbar">
          <Button kind="secondary" size="sm" onClick={() => setNavDate(new Date())}>Hoy</Button>
          <div className="nav">
            <IconButton name="chevronLeft" onClick={goBack} />
            <IconButton name="chevronRight" onClick={goForward} />
          </div>
          <h2>{navLabel}</h2>
          <div className="views">
            <button className={`cal-view-month ${view === 'month' ? 'active' : ''}`} onClick={() => setView('month')}>Mes</button>
            <button className={`cal-view-week ${view === 'week' ? 'active' : ''}`} onClick={() => setView('week')}>Semana</button>
            <button className={view === 'day' ? 'active' : ''} onClick={() => setView('day')}>Día</button>
          </div>
        </div>

        {view === 'month' && (
          <MonthView
            events={events}
            onEventClick={openEvent}
            today={today}
            year={navYear}
            month={navMonth}
            onDayClick={(iso) => {
              setNavDate(new Date(iso + 'T12:00:00'));
              setEditor({
                mode: 'create',
                event: { title: 'Visita · ', kind: 'visit', date: iso, start: '10:00', end: '11:00', agent: 'M. Pereyra', status: 'pending' },
              });
            }}
          />
        )}
        {view === 'week' && (
          <TimeGrid
            key={`week-${weekDays[0]}`}
            days={weekDays}
            events={events}
            onEventClick={openEvent}
            today={today}
            view="week"
            onSlotInteract={handleSlotInteract}
            onMoveEvent={handleMoveEvent}
            tzLabel={tzLabel}
            properties={properties}
            clients={clients}
          />
        )}
        {view === 'day' && (
          <TimeGrid
            key={`day-${navDayISO}`}
            days={[navDayISO]}
            events={events}
            onEventClick={openEvent}
            today={today}
            view="day"
            onSlotInteract={handleSlotInteract}
            onMoveEvent={handleMoveEvent}
            tzLabel={tzLabel}
            properties={properties}
            clients={clients}
          />
        )}
      </div>

      {popover && (
        <EventPopover
          event={popover.event}
          anchor={popover.anchor}
          onClose={closePopover}
          onEdit={handleEdit}
          onReschedule={handleReschedule}
          onCancel={handleCancel}
          onDelete={handleDelete}
          onOpenClient={onOpenClient}
          onOpenProperty={onOpenProperty}
        />
      )}
      {editor && (
        <EventEditor
          event={editor.event}
          mode={editor.mode}
          onClose={() => setEditor(null)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}

/**
 * api.js — Capa de datos: axios client + React Query hooks.
 *
 * Conecta con la API del bot (inmueblebot-api) mediante los endpoints /admin/*.
 *
 * Variables de entorno (.env):
 *   VITE_API_BASE_URL  — URL base (default: "/api" → proxy Vite → localhost:8000)
 *   VITE_API_TOKEN     — Admin API key (enviada como header x-api-key)
 */

import axios from 'axios';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

// ─── Cliente HTTP ─────────────────────────────────────────────────────────────

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  headers: { 'Content-Type': 'application/json' },
});

// Interceptor: adjunta la admin API key como x-api-key
http.interceptors.request.use((config) => {
  const token = import.meta.env.VITE_API_TOKEN;
  if (token) config.headers['x-api-key'] = token;
  return config;
});

// ─── Query keys ───────────────────────────────────────────────────────────────

export const keys = {
  properties:      ['properties'],
  property:        (id) => ['properties', id],
  clients:         ['clients'],
  client:          (id) => ['clients', id],
  events:          ['events'],
  event:           (id) => ['events', id],
  calendarStatus:  ['calendar', 'status'],
  calendarEvents:  ['calendar', 'events'],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function timeAgo(dateStr) {
  if (!dateStr) return '—';
  const diff  = Date.now() - new Date(dateStr).getTime();
  const mins  = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days  = Math.floor(diff / 86_400_000);
  if (mins  <  1)  return 'ahora';
  if (mins  < 60)  return `hace ${mins} min`;
  if (hours < 24)  return `hace ${hours} h`;
  if (days  < 30)  return `hace ${days} día${days > 1 ? 's' : ''}`;
  return new Date(dateStr).toLocaleDateString('es-AR');
}

/**
 * Returns the date portion in Argentina timezone (America/Argentina/Buenos_Aires).
 * This is the canonical timezone for the entire dashboard.
 */
const AR_TZ = 'America/Argentina/Buenos_Aires';

function toDateStr(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  // Use en-CA locale which formats as YYYY-MM-DD
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: AR_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(d);
  const get = (t) => parts.find(p => p.type === t)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}
function toTimeStr(iso) {
  if (!iso) return '';
  return new Intl.DateTimeFormat('es-AR', { timeZone: AR_TZ, hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(iso));
}
function addHoursTimeStr(iso, h = 1) {
  if (!iso) return '';
  const d = new Date(new Date(iso).getTime() + h * 3_600_000);
  return new Intl.DateTimeFormat('es-AR', { timeZone: AR_TZ, hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
}
// Build an ISO string with the local timezone offset so the backend stores the correct UTC value.
// e.g. "2026-05-05" + "10:00" in UTC-3 → "2026-05-05T10:00:00-03:00"
function toLocalISO(dateStr, timeStr) {
  const d = new Date(`${dateStr}T${timeStr}:00`);
  const off = -d.getTimezoneOffset(); // minutes ahead of UTC
  const sign = off >= 0 ? '+' : '-';
  const hh = String(Math.floor(Math.abs(off) / 60)).padStart(2, '0');
  const mm = String(Math.abs(off) % 60).padStart(2, '0');
  return `${dateStr}T${timeStr}:00${sign}${hh}:${mm}`;
}

// ─── Transformadores: API → Dashboard ─────────────────────────────────────────


// ─── Lookup tables ────────────────────────────────────────────────────────────

const PROP_TYPE_TO_LABEL = {
  apartment: 'Departamento',
  house:     'Casa',
  ph:        'PH',
  local:     'Local',
  office:    'Oficina',
  land:      'Terreno',
};

const PROP_LABEL_TO_TYPE = Object.fromEntries(
  Object.entries(PROP_TYPE_TO_LABEL).map(([k, v]) => [v, k])
);

const STATUS_TO_ROLE = {
  new:       'prospect',
  contacted: 'contact',
  qualified: 'lead',
  converted: 'client',
  lost:      'lost',
};

/** Normalize an image URL: if it's raw base64 (no data: prefix), add it so <img> can render it */
function normalizeImgUrl(url) {
  if (!url) return '';
  if (url.startsWith('data:') || url.startsWith('http') || url.startsWith('/')) return url;
  // Raw base64 — detect mime from first few decoded bytes if possible, default to JPEG
  try {
    const first = url.slice(0, 100);
    const raw = atob(first.replace(/[^A-Za-z0-9+/=]/g, '').slice(0, 12));
    if (raw.charCodeAt(0) === 0xff && raw.charCodeAt(1) === 0xd8) return `data:image/jpeg;base64,${url}`;
    if (raw.charCodeAt(0) === 0x89 && raw.slice(1, 4) === 'PNG') return `data:image/png;base64,${url}`;
    if (raw.charCodeAt(0) === 0x52 && raw.charCodeAt(1) === 0x49 && raw.slice(8, 12) === 'WEBP') return `data:image/webp;base64,${url}`;
  } catch {}
  return `data:image/jpeg;base64,${url}`;
}

function toProperty(p) {
  const bedrooms = p.bedrooms ?? 0;
  let photo = '';
  if (Array.isArray(p.images) && p.images.length > 0) {
    photo = normalizeImgUrl(p.images[0]);
  } else if (typeof p.images === 'string' && p.images) {
    try { photo = normalizeImgUrl(JSON.parse(p.images)[0] ?? p.images); } catch { photo = normalizeImgUrl(p.images); }
  }
  return {
    id:        String(p.id),
    addr:      p.location ?? p.address ?? '',
    neigh:     p.neigh ?? p.city ?? '',
    city:      p.city ?? p.neigh ?? '',
    // building type lives in property_type (from _prop_to_dict.extra_data.building_type)
    type:      PROP_TYPE_TO_LABEL[p.property_type] ?? p.property_type ?? '—',
    rooms:     bedrooms > 0 ? `${bedrooms} amb` : '—',
    m2:        p.area_m2 ?? p.area ?? 0,
    status:    p.status ?? 'available',
    price:     p.price ?? 0,
    currency:  p.currency ?? 'USD',
    // operation: 'venta' or 'alquiler' from DB type field
    operation: p.type === 'alquiler' ? 'rent' : 'sale',
    agent:     '',
    baths:     p.bathrooms ?? 0,
    parking:   0,
    photo,
    images:    p.images ? p.images.map(normalizeImgUrl) : (photo ? [photo] : []),
    notes:     p.description ?? '',
    desc:      p.description ?? '',
    _createdAt: p.created_at ?? null,
  };
}

function fromProperty(d) {
  // building_type → stored in Property.extra_data by admin.py
  // operation → maps to Property.type ('venta'/'alquiler') via PropertyCreate.operation
  // city → stored in Property.extra_data['city'] by admin.py
  const cityStr = d.city || d.neigh || '';
  return {
    title:         d.addr ?? '',
    description:   (d.desc || d.notes) ?? '',
    building_type: PROP_LABEL_TO_TYPE[d.type] ?? 'apartment',
    operation:     d.operation === 'rent' ? 'alquiler' : 'venta',
    location:      [d.addr, d.neigh].filter(Boolean).join(', ') || d.addr || '',
    city:          cityStr,
    price:         Number(d.price) || 0,
    currency:      d.currency ?? 'USD',
    bedrooms:      d.rooms ? parseInt(d.rooms) || null : null,
    bathrooms:     d.baths != null ? Number(d.baths) || null : null,
    area_m2:       d.m2 ? Number(d.m2) || null : null,
    status:        d.status === 'rented' ? 'rented' : (d.status ?? 'available'),
    images:        d.images && d.images.length > 0 ? d.images.map(normalizeImgUrl) : (d.photo ? [normalizeImgUrl(d.photo)] : []),
  };
}

function toClient(l) {
  return {
    id:          String(l.id),
    name:        l.name ?? 'Sin nombre',
    // l.status comes from _user_to_dict: 'new','contacted','qualified','converted','lost'
    role:        STATUS_TO_ROLE[l.status] ?? 'prospect',
    tags:        Array.isArray(l.tags) ? l.tags : [],
    phone:       l.phone ?? l.whatsapp_phone ?? '',
    email:       l.email ?? '',
    dni:         '',
    since:       l.created_at ? new Date(l.created_at).toLocaleDateString('es-AR') : '—',
    agent:       '',
    notes:       l.notes ?? '',
    interest:    [],
    visits:      0,
    lastContact: timeAgo(l.last_interaction ?? l.updated_at ?? l.created_at),
    _createdAt:  l.created_at ?? null,
    _rawStatus:  l.status ?? 'new',
  };
}

function fromClient(d) {
  // LeadCreate schema: { name, phone, email, role, notes }
  return {
    name:  d.name  ?? null,
    phone: d.phone || null,   // → User.whatsapp_phone (admin.py generates placeholder if null)
    email: d.email ?? null,
    role:  d.role  ?? 'prospect',
    notes: d.notes ?? null,
  };
}

function toEvent(a) {
  const startTime = a.start_time ?? null;
  // Title is packed into notes as "title|||notes" to avoid schema changes
  const rawNotes = a.notes ?? '';
  const sepIdx = rawNotes.indexOf('|||');
  const title = sepIdx >= 0 ? rawNotes.slice(0, sepIdx) : '';
  const notes = sepIdx >= 0 ? rawNotes.slice(sepIdx + 3) : rawNotes;
  return {
    id:         String(a.id),
    date:       toDateStr(startTime),
    start:      toTimeStr(startTime),
    end:        a.end_time ? toTimeStr(a.end_time) : (startTime ? addHoursTimeStr(startTime) : ''),
    kind:       a.type ?? 'visit',
    title,
    clientId:   a.user_id != null ? String(a.user_id) : null,
    propId:     a.property_id != null ? String(a.property_id) : null,
    agent:      '',
    status:     a.status === 'completed' ? 'confirmed' : (a.status ?? 'confirmed'),
    notes,
    calendarEventId: a.calendar_event_id ?? null,
    _createdAt: a.created_at ?? null,
  };
}

// Convierte el shape del formulario (EventEditor) al shape que espera la API.
// EventEditor usa: { date, start, end, kind, title, clientId, propId, agent, status, notes }
// La API acepta:   { start_time, end_time, user_id, property_id, type, status, notes }
// El título se empaqueta en notes como "title|||notes" para evitar cambios de esquema.
function fromEvent(d) {
  let startTime = null;
  let endTime = null;
  if (d.date) {
    const start = d.start || '09:00';
    const end = d.end || '10:00';
    startTime = `${d.date}T${start}:00`;
    endTime = `${d.date}T${end}:00`;
  }
  const packedNotes = d.title ? `${d.title}|||${d.notes ?? ''}` : (d.notes ?? '');
  return {
    start_time:  d.date && d.start ? toLocalISO(d.date, d.start || '09:00') : startTime,
    end_time:    d.date && d.end   ? toLocalISO(d.date, d.end   || '10:00') : endTime,
    user_id:     d.clientId || null,
    property_id: d.propId ? Number(d.propId) : null,
    type:        d.kind ?? 'visit',
    status:      d.status ?? 'confirmed',
    notes:       packedNotes,
  };
}

// ─── Propiedades ──────────────────────────────────────────────────────────────

const propertyApi = {
  list:   ()         => http.get('/admin/properties').then(r => (r.data.properties ?? r.data).map(toProperty)),
  get:    (id)       => http.get(`/admin/properties/${id}`).then(r => toProperty(r.data)),
  create: (data)     => http.post('/admin/properties', fromProperty(data)).then(r => r.data),
  update: (id, data) => http.patch(`/admin/properties/${id}`, fromProperty(data)).then(r => r.data),
  remove: (id)       => http.delete(`/admin/properties/${id}`).then(r => r.data),
};

export const useProperties = () =>
  useQuery({ queryKey: keys.properties, queryFn: propertyApi.list });

export const useProperty = (id) =>
  useQuery({ queryKey: keys.property(id), queryFn: () => propertyApi.get(id), enabled: !!id });

export const useCreateProperty = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: propertyApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: keys.properties }) });
};

export const useUpdateProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => propertyApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: keys.properties });
      qc.invalidateQueries({ queryKey: keys.property(id) });
    },
  });
};

export const useDeleteProperty = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: propertyApi.remove, onSuccess: () => qc.invalidateQueries({ queryKey: keys.properties }) });
};

// ─── Clientes (Leads) ─────────────────────────────────────────────────────────

const clientApi = {
  list:   ()         => http.get('/admin/leads').then(r => (r.data.leads ?? r.data).map(toClient)),
  get:    (id)       => http.get(`/admin/leads/${id}`).then(r => toClient(r.data)),
  create: (data)     => http.post('/admin/leads', fromClient(data)).then(r => r.data),
  update: (id, data) => http.patch(`/admin/leads/${id}`, fromClient(data)).then(r => r.data),
  remove: (id)       => http.delete(`/admin/leads/${id}`).then(r => r.data),
};

export const useClients = () =>
  useQuery({ queryKey: keys.clients, queryFn: clientApi.list });

export const useClient = (id) =>
  useQuery({ queryKey: keys.client(id), queryFn: () => clientApi.get(id), enabled: !!id });

export const useCreateClient = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: clientApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: keys.clients }) });
};

export const useUpdateClient = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => clientApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: keys.clients });
      qc.invalidateQueries({ queryKey: keys.client(id) });
    },
  });
};

export const useDeleteClient = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: clientApi.remove, onSuccess: () => qc.invalidateQueries({ queryKey: keys.clients }) });
};

// ─── Eventos (Citas / Appointments) ──────────────────────────────────────────

const eventApi = {
  list:   ()         => http.get('/admin/appointments').then(r => (r.data.appointments ?? r.data).map(toEvent)),
  get:    (id)       => http.get(`/admin/appointments/${id}`).then(r => toEvent(r.data)),
  create: (data)     => http.post('/admin/appointments', fromEvent(data)).then(r => r.data),
  update: (id, data) => http.patch(`/admin/appointments/${id}`, fromEvent(data)).then(r => r.data),
  remove: (id)       => http.delete(`/admin/appointments/${id}`).then(r => r.data),
};

export const useEvents = () =>
  useQuery({ queryKey: keys.events, queryFn: eventApi.list });

export const useCreateEvent = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: eventApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: keys.events }) });
};

export const useUpdateEvent = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => eventApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.events }),
  });
};

export const useDeleteEvent = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: eventApi.remove, onSuccess: () => qc.invalidateQueries({ queryKey: keys.events }) });
};

// ─── Google Calendar ──────────────────────────────────────────────────────────

export const useCalendarStatus = () =>
  useQuery({
    queryKey: keys.calendarStatus,
    queryFn: () => http.get('/admin/calendar/status').then(r => r.data),
    staleTime: 60_000,       // re-check every minute
    refetchOnWindowFocus: true,
  });

export const useCalendarEvents = (daysAhead = 30, maxResults = 50) =>
  useQuery({
    queryKey: [...keys.calendarEvents, daysAhead, maxResults],
    queryFn: () => http.get('/admin/calendar/events', { params: { days_ahead: daysAhead, max_results: maxResults } }).then(r => r.data),
    staleTime: 120_000,       // re-check every 2 minutes
    refetchOnWindowFocus: true,
  });

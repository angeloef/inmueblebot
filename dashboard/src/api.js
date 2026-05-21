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
  botSettings:     ['bot-settings'],
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
  // Old English codes (extra_data.building_type) — kept for backward compat
  apartment: 'Departamento',
  house:     'Casa',
  ph:        'PH',
  local:     'Local',
  office:    'Oficina',
  land:      'Terreno',
  // New Spanish codes (category column) — listed last so reverse mapping prefers these
  casa:         'Casa',
  departamento: 'Departamento',
  terreno:      'Terreno',
};

// Reverse map: display label → API value (new Spanish codes win over old English ones)
const PROP_LABEL_TO_TYPE = Object.fromEntries(
  Object.entries(PROP_TYPE_TO_LABEL).map(([k, v]) => [v, k])
);

// Map: display label → category column value (Spanish, lowercase)
// Only the 4 bot-searchable types are included; Local/Oficina → null (no category)
const PROP_LABEL_TO_CATEGORY = {
  'Departamento': 'departamento',
  'Casa':         'casa',
  'PH':           'ph',
  'Terreno':      'terreno',
};

const STATUS_TO_ROLE = {
  new:       'prospect',
  contacted: 'contact',
  qualified: 'lead',
  converted: 'client',
  lost:      'lost',
};

/** Reverse map: raw role from backend → dashboard pill kind */
const ROLE_TO_PILL = {
  prospect:  'prospect',
  contact:   'prospect',
  lead:      'prospect',
  client:    'tenant',
  tenant:    'tenant',
  owner:     'owner',
  buyer:     'owner',
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
    // Prefer category (new column), fall back to property_type (extra_data.building_type)
    type:      PROP_TYPE_TO_LABEL[p.category] ?? PROP_TYPE_TO_LABEL[p.property_type] ?? p.property_type ?? '—',
    rooms:     bedrooms > 0 ? `${bedrooms} amb` : '—',
    m2:        p.area_m2 ?? p.area ?? 0,
    status:    p.status ?? 'available',
    price:     p.price ?? 0,
    currency:  p.currency || 'ARS',
    // operation: 'venta' or 'alquiler' from DB type field
    operation: p.type === 'alquiler' ? 'rent' : 'sale',
    agent:     '',
    baths:     p.bathrooms ?? 0,
    parking:   0,
    photo,
    images:    p.images ? p.images.map(normalizeImgUrl) : (photo ? [photo] : []),
    notes:     p.description ?? '',
    desc:      p.description ?? '',
    buyer_id:  p.buyer_id ?? null,
    tenant_id: p.tenant_id ?? null,
    _createdAt: p.created_at ?? null,
  };
}

function fromProperty(d) {
  // category    → stored in Property.category column (new, Spanish lowercase)
  // building_type → stored in Property.extra_data by admin.py (legacy, kept for compat)
  // operation → maps to Property.type ('venta'/'alquiler') via PropertyCreate.operation
  // city → stored in Property.extra_data['city'] by admin.py
  const cityStr = d.city || d.neigh || '';
  const categoryVal = PROP_LABEL_TO_CATEGORY[d.type] ?? null;
  return {
    title:         d.addr ?? '',
    description:   (d.desc || d.notes) ?? '',
    category:      categoryVal,
    building_type: PROP_LABEL_TO_TYPE[d.type] ?? 'apartment',
    operation:     d.operation === 'rent' ? 'alquiler' : 'venta',
    location:      [d.addr, d.neigh].filter(Boolean).join(', ') || d.addr || '',
    city:          cityStr,
    price:         Number(d.price) || 0,
    currency:      d.currency || 'ARS',
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
    // Prefer raw role from backend (avoids round-trip loss), fallback to legacy status mapping
    role:        l.role ? ROLE_TO_PILL[l.role] ?? 'prospect' : (STATUS_TO_ROLE[l.status] ?? 'prospect'),
    tags:        Array.isArray(l.tags) ? l.tags : [],
    phone:       l.phone ?? l.whatsapp_phone ?? '',
    email:       l.email ?? '',
    dni:         '',
    since:       l.created_at ? new Date(l.created_at).toLocaleDateString('es-AR') : '—',
    agent:       '',
    notes:       l.notes ?? '',
    interest:    [],
    property_relations: l.property_relations ?? [],
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
    mutationFn: ({ id, ...rest }) => propertyApi.update(id, rest),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.properties }),
  });
};

export const useDeleteProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: propertyApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.properties }),
  });
};

// ── Property Status (quick update) ──────────────────────────────────────────────

export const useUpdatePropertyStatus = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }) => http.patch(`/admin/properties/${id}/status`, { status }),
    onMutate: async ({ id, status }) => {
      await qc.cancelQueries({ queryKey: keys.properties });
      const prev = qc.getQueryData(keys.properties);
      qc.setQueryData(keys.properties, (old) => {
        if (!old) return old;
        return old.map(p => String(p.id) === String(id) ? { ...p, status } : p);
      });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.properties, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.properties }),
  });
};

// ── Client-Property Relationship ────────────────────────────────────────────────

export const useRelateClientToProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ prop_id, client_id, relation, update_status = true }) =>
      http.post(`/admin/properties/${prop_id}/relate-client`, { client_id, relation, update_status }),
    onMutate: async ({ prop_id, relation }) => {
      // Map relations to status changes
      const relationToStatus = { buyer: 'sold', tenant: 'rented' };
      const newStatus = relationToStatus[relation];
      await qc.cancelQueries({ queryKey: keys.properties });
      await qc.cancelQueries({ queryKey: keys.clients });
      const prevProps = qc.getQueryData(keys.properties);
      const prevClients = qc.getQueryData(keys.clients);
      // Optimistically update property status
      if (newStatus && prevProps) {
        qc.setQueryData(keys.properties, (old) =>
          old ? old.map(p => String(p.id) === String(prop_id) ? { ...p, status: newStatus } : p) : old
        );
      }
      return { prevProps, prevClients };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prevProps) qc.setQueryData(keys.properties, ctx.prevProps);
      if (ctx?.prevClients) qc.setQueryData(keys.clients, ctx.prevClients);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.properties });
      qc.invalidateQueries({ queryKey: keys.clients });
    },
  });
};

export const useToggleClientPropertyInterest = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ lead_id, property_id, interested }) =>
      http.patch(`/admin/leads/${lead_id}/property-interest`, { property_id, interested }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.properties });
      qc.invalidateQueries({ queryKey: keys.clients });
    },
  });
};

// ─── Clients ──────────────────────────────────────────────────────────────────

const clientApi = {
  list:   ()         => http.get('/admin/leads').then(r => (r.data.leads ?? r.data).map(toClient)),
  get:    (id)       => http.get(`/admin/leads/${id}`).then(r => toClient(r.data)),
  create: (data)     => http.post('/admin/leads', fromClient(data)).then(r => r.data),
  update: (id, data) => http.patch(`/admin/leads/${id}`, fromClient(data)).then(r => r.data),
  remove: (id)       => http.delete(`/admin/leads/${id}`).then(r => r.data),
  reset:  (phone)    => http.post(`/admin/users/${phone}/reset`).then(r => r.data),
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
    mutationFn: ({ id, ...rest }) => clientApi.update(id, rest),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.clients }),
  });
};

export const useDeleteClient = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: clientApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.clients }),
  });
};

export const useResetClient = () =>
  useMutation({ mutationFn: clientApi.reset });

// ─── Events / Appointments ────────────────────────────────────────────────────

const eventApi = {
  list:   (params = {}) => http.get('/admin/appointments', { params }).then(r => (r.data.appointments ?? r.data).map(toEvent)),
  get:    (id)           => http.get(`/admin/appointments/${id}`).then(r => toEvent(r.data)),
  create: (data)         => http.post('/admin/appointments', fromEvent(data)).then(r => r.data),
  update: (data)         => http.patch(`/admin/appointments/${data.id}`, fromEvent(data)).then(r => r.data),
  remove: (id)           => http.delete(`/admin/appointments/${id}`).then(r => r.data),
};

export const useEvents = (params) =>
  useQuery({
    queryKey: keys.events,
    queryFn: () => eventApi.list(params),
    refetchInterval: 30_000,   // poll every 30s — catches WhatsApp-created appointments
  });

export const useEvent = (id) =>
  useQuery({ queryKey: keys.event(id), queryFn: () => eventApi.get(id), enabled: !!id });

// Alias used by Calendar.jsx
export const useEventById = useEvent;

export const useCreateEvent = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: eventApi.create, onSuccess: () => qc.refetchQueries({ queryKey: keys.events }) });
};

export const useUpdateEvent = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: eventApi.update,
    onSuccess: () => qc.refetchQueries({ queryKey: keys.events }),
  });
};

export const useDeleteEvent = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: eventApi.remove,
    onSuccess: () => qc.refetchQueries({ queryKey: keys.events }),
  });
};

// ─── Calendar ─────────────────────────────────────────────────────────────────

export const useCalendarStatus = () =>
  useQuery({
    queryKey: keys.calendarStatus,
    queryFn:  () => http.get('/admin/calendar/status').then(r => r.data),
    staleTime: 60_000,
  });

export const useCalendarEvents = (params = {}) =>
  useQuery({
    queryKey: [...keys.calendarEvents, params],
    queryFn:  () => http.get('/admin/calendar/events', { params }).then(r => r.data),
    staleTime: 30_000,
  });

// ─── FAQs ─────────────────────────────────────────────────────────────────────

const faqApi = {
  list:   (params = {}) => http.get('/admin/faqs', { params }).then(r => r.data.faqs ?? r.data),
  get:    (id)           => http.get(`/admin/faqs/${id}`).then(r => r.data),
  create: (data)         => http.post('/admin/faqs', data).then(r => r.data),
  update: ({ id, ...data }) => http.patch(`/admin/faqs/${id}`, data).then(r => r.data),
  remove: (id)           => http.delete(`/admin/faqs/${id}`).then(r => r.data),
};

export const useFaqs = (params) =>
  useQuery({ queryKey: ['faqs', params], queryFn: () => faqApi.list(params) });

export const useCreateFaq = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: faqApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['faqs'] }) });
};

export const useUpdateFaq = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: faqApi.update, onSuccess: () => qc.invalidateQueries({ queryKey: ['faqs'] }) });
};

export const useDeleteFaq = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: faqApi.remove, onSuccess: () => qc.invalidateQueries({ queryKey: ['faqs'] }) });
};

// ─── Notifications ────────────────────────────────────────────────────────────

const notifApi = {
  list:    (params = {}) => http.get('/admin/notifications', { params }).then(r => r.data),
  read:    (id)          => http.patch(`/admin/notifications/${id}/read`).then(r => r.data),
  readAll: ()            => http.post('/admin/notifications/read-all').then(r => r.data),
  remove:  (id)          => http.delete(`/admin/notifications/${id}`).then(r => r.data),
};

export const useNotifications = () =>
  useQuery({
    queryKey: ['notifications'],
    queryFn:  () => notifApi.list({ limit: 30 }),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

export const useMarkNotificationRead = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: notifApi.read,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  });
};

export const useMarkAllRead = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: notifApi.readAll,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  });
};

export const useDeleteNotification = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: notifApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  });
};

// ─── Bot Settings ─────────────────────────────────────────────────────────────

const settingsApi = {
  get:    () => http.get('/admin/settings').then(r => r.data),
  update: (data) => http.patch('/admin/settings', data).then(r => r.data),
};

export const useBotSettings = () =>
  useQuery({
    queryKey: keys.botSettings,
    queryFn:  settingsApi.get,
    staleTime: 30_000,
  });

export const useUpdateBotSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: settingsApi.update,
    onSuccess:  () => qc.invalidateQueries({ queryKey: keys.botSettings }),
  });
};

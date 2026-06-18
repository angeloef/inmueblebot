/**
 * api.js — Capa de datos: axios client + React Query hooks.
 *
 * Conecta con la API del bot (inmueblebot-api) mediante los endpoints /admin/*.
 *
 * Auth (Fase 4): JWT por cookie httpOnly (mismo origen vía el proxy /api). El
 * browser nunca ve el token; se envía solo con `withCredentials`. Un 401 dispara
 * un refresh transparente (single-flight) y reintenta; si el refresh falla, se
 * emite el evento `auth:expired` para que el AuthProvider muestre el login.
 *
 * Variables de entorno (.env):
 *   VITE_API_BASE_URL  — URL base (default: "/api" → proxy Vite/nginx → FastAPI)
 */

import axios from 'axios';
import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api';

// ─── Cliente HTTP ─────────────────────────────────────────────────────────────

export const http = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,   // envía/recibe las cookies httpOnly de sesión
});

// ─── Sucursal activa (Enterprise multi-sucursal) ──────────────────────────────
// El dueño de una org elige "entrar" a una sucursal: ese id viaja en el header
// X-Branch-Id y el backend scopea TODO el dashboard a ese tenant hijo. Sin sucursal
// seleccionada (null) → vista consolidada de la org. Persistido en localStorage para
// sobrevivir recargas. Para gerentes/standalone se ignora (el backend lo descarta).
const ACTIVE_BRANCH_KEY = 'vivienda_active_branch';
let _activeBranchId = null;
try { _activeBranchId = localStorage.getItem(ACTIVE_BRANCH_KEY) || null; } catch { /* SSR/denied */ }

export function getActiveBranchId() { return _activeBranchId; }

export function setActiveBranchId(id) {
  _activeBranchId = id || null;
  try {
    if (_activeBranchId) localStorage.setItem(ACTIVE_BRANCH_KEY, _activeBranchId);
    else localStorage.removeItem(ACTIVE_BRANCH_KEY);
  } catch { /* ignore */ }
}

http.interceptors.request.use((config) => {
  if (_activeBranchId) config.headers['X-Branch-Id'] = _activeBranchId;
  return config;
});

// Refresh single-flight: varios 401 concurrentes comparten un único POST /auth/refresh.
let _refreshPromise = null;
function refreshSession() {
  if (!_refreshPromise) {
    _refreshPromise = http.post('/auth/refresh').finally(() => { _refreshPromise = null; });
  }
  return _refreshPromise;
}

// Las rutas de auth no se reintentan (evita bucles si el refresh devuelve 401).
function isAuthPath(url = '') {
  return url.includes('/auth/login') || url.includes('/auth/refresh') || url.includes('/auth/logout');
}

http.interceptors.response.use(
  (res) => res,
  async (error) => {
    const { response, config } = error;
    if (response?.status === 401 && config && !config._retried && !isAuthPath(config.url)) {
      config._retried = true;
      try {
        await refreshSession();
        return http(config);   // reintenta con la cookie ya rotada
      } catch {
        window.dispatchEvent(new CustomEvent('auth:expired'));
        return Promise.reject(error);
      }
    }
    if (response?.status === 401 && !isAuthPath(config?.url)) {
      window.dispatchEvent(new CustomEvent('auth:expired'));
    }
    if (response?.status === 402) {
      window.dispatchEvent(new CustomEvent('subscription:required', { detail: response.data ?? {} }));
    }
    return Promise.reject(error);
  },
);

// ─── Auth API (Fase 4) ────────────────────────────────────────────────────────

export const authApi = {
  me:      ()                 => http.get('/auth/me').then(r => r.data),
  login:   (email, password)  => http.post('/auth/login', { email, password }).then(r => r.data),
  logout:  ()                 => http.post('/auth/logout').then(r => r.data),
  refresh: ()                 => http.post('/auth/refresh').then(r => r.data),
  // Login con Google: navegación top-level (no XHR) hacia el endpoint que redirige
  // a la pantalla de consentimiento. El callback vuelve con las cookies ya seteadas.
  googleLoginUrl: ()          => `${API_BASE}/auth/google/login`,
};

/**
 * URL hacia el endpoint que sirve una imagen de propiedad como recurso HTTP
 * cacheable (no base64 inline). La auth viaja por la cookie httpOnly de sesión,
 * que <img src> envía automáticamente al ser mismo origen. `ver` (image_ver del
 * backend) busta la caché al editar.
 * @param {string|number} id  property id
 * @param {number} index      índice de la imagen (0 = portada)
 * @param {string|number} ver image_ver para cache-busting
 * @returns {string}
 */
export function propertyImageUrl(id, index = 0, ver = '') {
  const params = new URLSearchParams();
  if (ver) params.set('v', String(ver));
  const qs = params.toString();
  return `${API_BASE}/admin/properties/${id}/image/${index}${qs ? `?${qs}` : ''}`;
}

// ─── Query keys ───────────────────────────────────────────────────────────────

export const keys = {
  billingStatus:   ['billing', 'status'],
  billingPlans:    ['billing', 'plans'],
  properties:      ['properties'],
  property:        (id) => ['properties', id],
  clients:         ['clients'],
  client:          (id) => ['clients', id],
  events:          ['events'],
  event:           (id) => ['events', id],
  calendarStatus:  ['calendar', 'status'],
  calendarEvents:  ['calendar', 'events'],
  botSettings:     ['bot-settings'],
  conversations:   ['conversations'],
  conversation:    (id) => ['conversations', id],
  contracts:       ['contracts'],
  contract:        (id) => ['contracts', id],
  cobranzasSummary:['cobranzas', 'summary'],
  indices:         (code) => ['indices', code],
  tenants:         ['tenants'],
  tenantSettings:  (id) => ['tenant-settings', id],
  activity:        (entityType, id) => ['activity', entityType, String(id)],
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

export function toDateStr(iso) {
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

  // Imágenes inline (base64): presentes en respuestas optimistas (crear/editar) y
  // en el GET de una sola propiedad. La lista liviana NO las trae.
  let inlineImages = [];
  if (Array.isArray(p.images) && p.images.length > 0) {
    inlineImages = p.images.map(normalizeImgUrl);
  } else if (typeof p.images === 'string' && p.images) {
    try { inlineImages = (JSON.parse(p.images) || []).map(normalizeImgUrl); }
    catch { inlineImages = [normalizeImgUrl(p.images)]; }
  }

  // Sin inline → armar URLs hacia el endpoint de imágenes para carga diferida.
  // La portada (índice 0) se muestra en la grilla; el resto carga al abrir el drawer.
  const imageCount = p.image_count ?? inlineImages.length;
  const imageVer   = p.image_ver ?? '';
  const lazyImages = (inlineImages.length === 0 && imageCount > 0)
    ? Array.from({ length: imageCount }, (_, i) => propertyImageUrl(p.id, i, imageVer))
    : [];

  const images = inlineImages.length > 0 ? inlineImages : lazyImages;
  const photo  = images[0] ?? '';
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
    images,
    imageCount,
    notes:     p.description ?? '',
    desc:      p.description ?? '',
    buyer_id:  p.buyer_id ?? null,
    tenant_id: p.tenant_id ?? null,
    refs:      Array.isArray(p.reference_points) ? p.reference_points : [],
    place_id:  p.place_id ?? '',
    _createdAt: p.created_at ?? null,
  };
}

function fromProperty(d) {
  // category    → stored in Property.category column (new, Spanish lowercase)
  // building_type → stored in Property.extra_data by admin.py (legacy, kept for compat)
  // operation → maps to Property.type ('venta'/'alquiler') via PropertyCreate.operation
  // city → stored in Property.extra_data['city'] by admin.py
  // zone → stored in Property.extra_data['zone'] by admin.py
  const zoneStr = d.neigh || '';
  const cityStr = d.city || d.neigh || '';
  const categoryVal = PROP_LABEL_TO_CATEGORY[d.type] ?? null;
  const desc = d.desc || d.notes || '';
  const beds = d.rooms ? parseInt(d.rooms) || 0 : 0;

  // Generate a sensible title from category + beds + zone (not the address)
  const typeLabel = d.type || 'Propiedad';
  const shortZone = zoneStr.split(',')[0].trim();
  const title = beds > 0
    ? `${typeLabel} ${beds} dormitorios ${shortZone}`
    : `${typeLabel} en ${shortZone || 'Oberá'}`;

  return {
    title:         title,
    description:   desc,
    category:      categoryVal,
    building_type: PROP_LABEL_TO_TYPE[d.type] ?? 'apartment',
    operation:     d.operation === 'rent' ? 'alquiler' : 'venta',
    location:      [d.addr, d.neigh].filter(Boolean).join(', ') || d.addr || '',
    city:          cityStr,
    zone:          zoneStr,
    price:         Number(d.price) || 0,
    currency:      d.currency || 'ARS',
    bedrooms:      beds || null,
    bathrooms:     d.baths != null ? Number(d.baths) || null : null,
    area_m2:       d.m2 ? Number(d.m2) || null : null,
    status:        d.status === 'rented' ? 'rented' : (d.status ?? 'available'),
    // images === null  → "sin cambios": el backend conserva las imágenes existentes
    // (no las pisa con las URLs diferidas que tiene el dashboard en memoria).
    images:        Array.isArray(d.images) && d.images.length > 0
                     ? d.images.map(normalizeImgUrl)
                     : (d.images === null ? null : (d.photo ? [normalizeImgUrl(d.photo)] : [])),
    reference_points: Array.isArray(d.refs) ? d.refs.filter(Boolean) : [],
    place_id: d.place_id || '',
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
    agentId:    a.agent_id != null ? String(a.agent_id) : '',
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
    agent_id:    d.agentId || null,
    type:        d.kind ?? 'visit',
    status:      d.status ?? 'confirmed',
    notes:       packedNotes,
  };
}

// ─── Propiedades ──────────────────────────────────────────────────────────────

export const propertyApi = {
  list:   ()         => http.get('/admin/properties').then(r => (r.data.properties ?? r.data).map(toProperty)),
  get:    (id)       => http.get(`/admin/properties/${id}`).then(r => toProperty(r.data)),
  create: (data)     => http.post('/admin/properties', fromProperty(data)).then(r => r.data),
  update: (id, data) => http.patch(`/admin/properties/${id}`, fromProperty(data)).then(r => r.data),
  remove: (id)       => http.delete(`/admin/properties/${id}`).then(r => r.data),
  autocompleteCity: (q) =>
    http.get('/admin/properties/city-autocomplete', { params: { q } })
        .then(r => r.data.suggestions ?? [])
        .catch(() => []),
};

export const useProperties = () =>
  useQuery({ queryKey: keys.properties, queryFn: propertyApi.list });

export const useProperty = (id) =>
  useQuery({ queryKey: keys.property(id), queryFn: () => propertyApi.get(id), enabled: !!id });

// Merge a form-shaped edit (the payload passed by Properties.jsx, same shape as
// toProperty() output) into a cached property so the UI reflects it instantly.
function applyPropertyEdit(prop, edit) {
  const merged = { ...prop, ...edit };
  // Keep number/derived fields in the shape the cards & drawer expect.
  if (edit.m2 != null) merged.m2 = Number(edit.m2) || 0;
  if (edit.notes != null) merged.desc = edit.notes;   // toProperty() keeps notes≡desc
  if (edit.photo) merged.photo = edit.photo;
  if (Array.isArray(edit.images)) merged.images = edit.images;
  return merged;
}

export const useCreateProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: propertyApi.create,
    onMutate: async (data) => {
      await qc.cancelQueries({ queryKey: keys.properties });
      const prev = qc.getQueryData(keys.properties);
      // Temp card rendered immediately; replaced by the real row on refetch.
      const optimistic = applyPropertyEdit(
        { id: `temp-${Date.now()}`, _optimistic: true, photo: '', images: [], desc: '', agent: '', baths: 0, parking: 0 },
        data,
      );
      qc.setQueryData(keys.properties, (old) => (old ? [optimistic, ...old] : [optimistic]));
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.properties, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.properties }),
  });
};

export const useUpdateProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...rest }) => propertyApi.update(id, rest),
    onMutate: async ({ id, ...rest }) => {
      await qc.cancelQueries({ queryKey: keys.properties });
      const prev = qc.getQueryData(keys.properties);
      qc.setQueryData(keys.properties, (old) =>
        old ? old.map(p => (String(p.id) === String(id) ? applyPropertyEdit(p, rest) : p)) : old
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.properties, ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.properties });
      qc.invalidateQueries({ queryKey: ['activity'] });
    },
  });
};

export const useDeleteProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: propertyApi.remove,
    // Backend hard-deletes; remove the card from the list immediately.
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: keys.properties });
      const prev = qc.getQueryData(keys.properties);
      qc.setQueryData(keys.properties, (old) =>
        old ? old.filter(p => String(p.id) !== String(id)) : old
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.properties, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.properties }),
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
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.properties });
      qc.invalidateQueries({ queryKey: ['activity'] });
    },
  });
};

// ── Client-Property Relationship ────────────────────────────────────────────────

export const useRelateClientToProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ prop_id, client_id, relation, update_status = true, agent_id = null }) =>
      http.post(`/admin/properties/${prop_id}/relate-client`, { client_id, relation, update_status, agent_id }),
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
      qc.invalidateQueries({ queryKey: ['activity'] });
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

// ── Activity log (timeline unificado: vínculos, estado, ediciones, reasignaciones) ──
export const useActivity = (entityType, id) =>
  useQuery({
    queryKey: keys.activity(entityType, id),
    queryFn: () => http
      .get('/admin/activity', { params: { entity_type: entityType, entity_id: id } })
      .then(r => r.data.activity ?? []),
    enabled: !!entityType && !!id,
  });

export const useEvent = (id) =>
  useQuery({ queryKey: keys.event(id), queryFn: () => eventApi.get(id), enabled: !!id });

// Alias used by Calendar.jsx
export const useEventById = useEvent;

export const useCreateEvent = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: eventApi.create,
    // Insert the event into the calendar immediately (EventEditor's form shape
    // matches toEvent()); the temp row is replaced by the real one on refetch.
    onMutate: async (form) => {
      await qc.cancelQueries({ queryKey: keys.events });
      const prev = qc.getQueryData(keys.events);
      const optimistic = {
        id:        `temp-${Date.now()}`,
        _optimistic: true,
        title:     form.title ?? '',
        kind:      form.kind ?? 'visit',
        date:      form.date ?? '',
        start:     form.start ?? '',
        end:       form.end ?? '',
        clientId:  form.clientId || null,
        propId:    form.propId || null,
        agent:     form.agent ?? '',
        status:    form.status ?? 'confirmed',
        notes:     form.notes ?? '',
        calendarEventId: null,
        _createdAt: new Date().toISOString(),
      };
      qc.setQueryData(keys.events, (old) => (old ? [...old, optimistic] : [optimistic]));
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.events, ctx.prev);
    },
    onSettled: () => qc.refetchQueries({ queryKey: keys.events }),
  });
};

export const useUpdateEvent = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: eventApi.update,
    onMutate: async (data) => {
      await qc.cancelQueries({ queryKey: keys.events });
      const prev = qc.getQueryData(keys.events);
      qc.setQueryData(keys.events, (old) => {
        if (!old) return old;
        return old.map(e => String(e.id) === String(data.id)
          ? { ...e, date: data.date, start: data.start, end: data.end }
          : e
        );
      });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.events, ctx.prev);
    },
    onSettled: () => qc.refetchQueries({ queryKey: keys.events }),
  });
};

export const useDeleteEvent = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: eventApi.remove,
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: keys.events });
      const prev = qc.getQueryData(keys.events);
      qc.setQueryData(keys.events, (old) => {
        if (!old) return old;
        return old.filter(e => String(e.id) !== String(id));
      });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.events, ctx.prev);
    },
    onSettled: () => {
      qc.refetchQueries({ queryKey: keys.events });
    },
  });
};

// "Eliminar evento" = cancel-if-needed + permanent delete, in a single action.
// Takes the full event object. The card is removed from the UI immediately; the
// cancel (which notifies the client) and the delete run sequentially on the server
// — sequenced so we never DELETE a row mid-cancel. Rolls back on failure.
export const useRemoveEvent = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (event) => {
      if (event.status !== 'cancelled') {
        await eventApi.update({ ...event, status: 'cancelled' });
      }
      return eventApi.remove(event.id);
    },
    onMutate: async (event) => {
      await qc.cancelQueries({ queryKey: keys.events });
      const prev = qc.getQueryData(keys.events);
      qc.setQueryData(keys.events, (old) =>
        old ? old.filter(e => String(e.id) !== String(event.id)) : old
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.events, ctx.prev);
    },
    onSettled: () => qc.refetchQueries({ queryKey: keys.events }),
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

export const useDeleteReadNotifications = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => http.post('/admin/notifications/delete-read').then(r => r.data),
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

// ─── Tenants (inmobiliarias / SaaS tenants — V3 Phase 1) ─────────────────────

const tenantApi = {
  list:   ()             => http.get('/admin/tenants').then(r => r.data.tenants ?? []),
  create: (data)         => http.post('/admin/tenants', data).then(r => r.data),
  update: ({ id, ...d }) => http.patch(`/admin/tenants/${id}`, d).then(r => r.data),
  remove: (id)           => http.delete(`/admin/tenants/${id}`).then(r => r.data),
};

export const useTenants = () =>
  useQuery({ queryKey: keys.tenants, queryFn: tenantApi.list, staleTime: 30_000 });

export const useCreateTenant = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: tenantApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: keys.tenants }) });
};

export const useUpdateTenant = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: tenantApi.update, onSuccess: () => qc.invalidateQueries({ queryKey: keys.tenants }) });
};

export const useDeleteTenant = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: tenantApi.remove, onSuccess: () => qc.invalidateQueries({ queryKey: keys.tenants }) });
};

// ─── Per-tenant settings (V3 Phase 2: active_router) ─────────────────────────

const tenantSettingsApi = {
  update: ({ id, ...d }) => http.patch(`/admin/tenants/${id}/settings`, d).then(r => r.data),
};

export const useUpdateTenantSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: tenantSettingsApi.update,
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: keys.tenantSettings(vars.id) });
      // Also invalidate the tenant list so active_router badge refreshes.
      qc.invalidateQueries({ queryKey: keys.tenants });
    },
  });
};

// ─── Explorador global cross-tenant (super-admin, plan 05) ───────────────────
// Pega a /admin/global/*: lista y edita entidades de TODAS las inmobiliarias.
// El backend gateado por require_superadmin; el GUC RLS expone el cross-tenant.

const globalKeys = {
  clients:      (params) => ['global', 'clients', params],
  properties:   (params) => ['global', 'properties', params],
  appointments: (params) => ['global', 'appointments', params],
};

const globalApi = {
  list:   (entity, params = {}) =>
    http.get(`/admin/global/${entity}`, { params }).then(r => r.data),
  update: (entity, id, data) =>
    http.patch(`/admin/global/${entity}/${id}`, data).then(r => r.data),
};

// `enabled` permite que GlobalExplorer llame los 3 hooks incondicionalmente (Rules of
// Hooks) y solo deje activo el de la entidad visible. placeholderData=keepPreviousData
// (v5) evita el parpadeo a vacío al paginar/buscar.
export const useGlobalClients = (params = {}, enabled = true) =>
  useQuery({ queryKey: globalKeys.clients(params), queryFn: () => globalApi.list('clients', params), enabled, placeholderData: keepPreviousData });

export const useGlobalProperties = (params = {}, enabled = true) =>
  useQuery({ queryKey: globalKeys.properties(params), queryFn: () => globalApi.list('properties', params), enabled, placeholderData: keepPreviousData });

export const useGlobalAppointments = (params = {}, enabled = true) =>
  useQuery({ queryKey: globalKeys.appointments(params), queryFn: () => globalApi.list('appointments', params), enabled, placeholderData: keepPreviousData });

export const useUpdateGlobalEntity = (entity) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => globalApi.update(entity, id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['global', entity] }),
  });
};

// ─── Analítica de plataforma (super-admin, plan 06) ──────────────────────────
// Pega a /admin/analytics/*: agregados cross-tenant de TODAS las inmobiliarias.
// Gateado por require_superadmin; el GUC RLS expone el cross-tenant.

const analyticsApi = {
  overview: () => http.get('/admin/analytics/overview').then(r => r.data),
  tenants:  () => http.get('/admin/analytics/tenants').then(r => r.data),
};

export const useAnalyticsOverview = (enabled = true) =>
  useQuery({ queryKey: ['analytics', 'overview'], queryFn: analyticsApi.overview, enabled, staleTime: 60_000 });

export const useAnalyticsTenants = (enabled = true) =>
  useQuery({ queryKey: ['analytics', 'tenants'], queryFn: analyticsApi.tenants, enabled, staleTime: 60_000 });

// ─── Reporte de errores in-app + triage super-admin (plan 07) ────────────────
// POST /admin/error-reports lo crea cualquier usuario autenticado; GET/PATCH son
// super-admin (gateado en el backend; el GUC RLS expone el cross-tenant).

const errorReportsApi = {
  create: (data) => http.post('/admin/error-reports', data).then(r => r.data),
  list:   (params = {}) => http.get('/admin/error-reports', { params }).then(r => r.data),
  update: (id, data) => http.patch(`/admin/error-reports/${id}`, data).then(r => r.data),
};

export const useCreateErrorReport = () =>
  useMutation({ mutationFn: errorReportsApi.create });

export const useErrorReports = (params = {}, enabled = true) =>
  useQuery({
    queryKey: ['error-reports', params],
    queryFn: () => errorReportsApi.list(params),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });

export const useUpdateErrorReport = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => errorReportsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['error-reports'] }),
  });
};

// ─── WhatsApp Conversations ─────────────────────────────────────────────────

const conversationApi = {
  list:   (params = {}) => http.get('/admin/conversations', { params }).then(r => r.data),
  get:    (id)           => http.get(`/admin/conversations/${id}`).then(r => r.data),
  reply:  ({ id, text }) => http.post(`/admin/conversations/${id}/reply`, { text }).then(r => r.data),
  toggleBot: (id)        => http.patch(`/admin/conversations/${id}/toggle-bot`).then(r => r.data),
};

export const useConversations = () =>
  useQuery({
    queryKey: keys.conversations,
    queryFn:  () => conversationApi.list({ limit: 50, offset: 0 }),
    refetchInterval: 15_000,
  });

export const useConversation = (id) =>
  useQuery({
    queryKey: keys.conversation(id),
    queryFn:  () => conversationApi.get(id),
    enabled:  !!id,
    refetchInterval: 10_000,
  });

export const useReplyToConversation = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: conversationApi.reply,
    onMutate: async ({ id, text }) => {
      await qc.cancelQueries({ queryKey: keys.conversation(id) });
      const prev = qc.getQueryData(keys.conversation(id));
      // Optimistically append admin message to conversation cache
      qc.setQueryData(keys.conversation(id), (old) => {
        if (!old) return old;
        const optimistic = {
          id:            `temp-${Date.now()}`,
          role:          'admin',
          sender:        'admin',
          content:       text,
          timestamp:     new Date().toISOString(),
          metadata:      null,
        };
        return { ...old, messages: [...(old.messages ?? []), optimistic] };
      });
      return { prev };
    },
    onError: (_err, vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.conversation(vars.id), ctx.prev);
    },
    onSettled: (_data, _err, vars) => {
      qc.invalidateQueries({ queryKey: keys.conversation(vars.id) });
    },
  });
};

export const useToggleBot = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }) => conversationApi.toggleBot(id),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: keys.conversation(id) });
      await qc.cancelQueries({ queryKey: keys.conversations });
      const prevConv = qc.getQueryData(keys.conversation(id));
      const prevList = qc.getQueryData(keys.conversations);
      // Optimistically flip bot_paused in single conversation cache
      if (prevConv) {
        qc.setQueryData(keys.conversation(id), (old) =>
          old ? { ...old, bot_paused: !old.bot_paused } : old
        );
      }
      // Also flip in the conversations list
      if (prevList) {
        qc.setQueryData(keys.conversations, (old) => {
          if (!old?.conversations) return old;
          return {
            ...old,
            conversations: old.conversations.map(c =>
              String(c.id) === String(id) ? { ...c, bot_paused: !c.bot_paused } : c
            ),
          };
        });
      }
      return { prevConv, prevList };
    },
    onError: (_err, vars, ctx) => {
      if (ctx?.prevConv) qc.setQueryData(keys.conversation(vars.id), ctx.prevConv);
      if (ctx?.prevList) qc.setQueryData(keys.conversations, ctx.prevList);
    },
    onSettled: (_data, _err, vars) => {
      qc.invalidateQueries({ queryKey: keys.conversation(vars.id) });
      qc.invalidateQueries({ queryKey: keys.conversations });
    },
  });
};

// ─── Cobranzas (contratos, cobros, gastos, índices) ──────────────────────────

const cobranzasApi = {
  contracts:        ()             => http.get('/admin/contracts').then(r => r.data.contracts ?? []),
  contract:         (id)           => http.get(`/admin/contracts/${id}`).then(r => r.data),
  createContract:   (data)         => http.post('/admin/contracts', data).then(r => r.data),
  updateContract:   ({ id, ...d }) => http.patch(`/admin/contracts/${id}`, d).then(r => r.data),
  deleteContract:   (id)           => http.delete(`/admin/contracts/${id}`).then(r => r.data),
  generateCharges:  (id)           => http.post(`/admin/contracts/${id}/charges/generate`).then(r => r.data),
  updateCharge:     ({ id, ...d }) => http.patch(`/admin/charges/${id}`, d).then(r => r.data),
  payCharge:        ({ id, ...d }) => http.post(`/admin/charges/${id}/pay`, d).then(r => r.data),
  remindCharge:     (id)           => http.post(`/admin/charges/${id}/remind`).then(r => r.data),
  createExpense:    ({ contractId, ...d }) => http.post(`/admin/contracts/${contractId}/expenses`, d).then(r => r.data),
  deleteExpense:    (id)           => http.delete(`/admin/expenses/${id}`).then(r => r.data),
  liquidacion:      ({ id, period }) => http.get(`/admin/contracts/${id}/liquidacion`, { params: { period } }).then(r => r.data),
  summary:          ()             => http.get('/admin/cobranzas/summary').then(r => r.data),
  indices:          (code = 'IPC') => http.get('/admin/indices', { params: { code } }).then(r => r.data.indices ?? []),
  upsertIndex:      (data)         => http.post('/admin/indices', data).then(r => r.data),
};

export const useContracts = () =>
  useQuery({ queryKey: keys.contracts, queryFn: cobranzasApi.contracts });

export const useContract = (id) =>
  useQuery({ queryKey: keys.contract(id), queryFn: () => cobranzasApi.contract(id), enabled: !!id });

export const useCobranzasSummary = () =>
  useQuery({ queryKey: keys.cobranzasSummary, queryFn: cobranzasApi.summary, staleTime: 30_000 });

export const useIndices = (code = 'IPC') =>
  useQuery({ queryKey: keys.indices(code), queryFn: () => cobranzasApi.indices(code) });

// Invalidate the whole cobranzas surface after any mutation that changes money.
function invalidateCobranzas(qc, contractId) {
  qc.invalidateQueries({ queryKey: keys.contracts });
  qc.invalidateQueries({ queryKey: keys.cobranzasSummary });
  if (contractId) qc.invalidateQueries({ queryKey: keys.contract(contractId) });
}

export const useCreateContract = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.createContract, onSuccess: () => invalidateCobranzas(qc) });
};

export const useUpdateContract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cobranzasApi.updateContract,
    onSuccess: (_d, vars) => invalidateCobranzas(qc, vars.id),
  });
};

export const useDeleteContract = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.deleteContract, onSuccess: () => invalidateCobranzas(qc) });
};

export const useGenerateCharges = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.generateCharges, onSuccess: (_d, id) => invalidateCobranzas(qc, id) });
};

export const useUpdateCharge = (contractId) => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.updateCharge, onSuccess: () => invalidateCobranzas(qc, contractId) });
};

export const usePayCharge = (contractId) => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.payCharge, onSuccess: () => invalidateCobranzas(qc, contractId) });
};

export const useRemindCharge = (contractId) => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.remindCharge, onSuccess: () => invalidateCobranzas(qc, contractId) });
};

export const useCreateExpense = (contractId) => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.createExpense, onSuccess: () => invalidateCobranzas(qc, contractId) });
};

export const useDeleteExpense = (contractId) => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: cobranzasApi.deleteExpense, onSuccess: () => invalidateCobranzas(qc, contractId) });
};

export const useUpsertIndex = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: cobranzasApi.upsertIndex,
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: keys.indices(d?.code ?? 'IPC') });
      qc.invalidateQueries({ queryKey: keys.contracts });
      qc.invalidateQueries({ queryKey: keys.cobranzasSummary });
    },
  });
};

// ─── Team / Seats ─────────────────────────────────────────────────────────────

const teamApi = {
  list:   ()              => http.get('/team/members').then(r => r.data),
  invite: (data)          => http.post('/team/members', data).then(r => r.data),
  remove: (memberId)      => http.delete(`/team/members/${memberId}`).then(r => r.data),
};

export const useTeamMembers = () =>
  useQuery({
    queryKey: ['team', 'members'],
    queryFn:  teamApi.list,
    staleTime: 30_000,
  });

export const useInviteMember = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: teamApi.invite,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team', 'members'] }),
  });
};

export const useRemoveMember = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: teamApi.remove,
    onMutate: async (memberId) => {
      await qc.cancelQueries({ queryKey: ['team', 'members'] });
      const prev = qc.getQueryData(['team', 'members']);
      qc.setQueryData(['team', 'members'], (old) =>
        old ? old.filter(m => String(m.id) !== String(memberId)) : old
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(['team', 'members'], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['team', 'members'] }),
  });
};

// ─── Operaciones: ventas + garantes (fase crítica) ────────────────────────────
const salesApi = {
  list:   (propertyId) => http.get('/admin/sales', { params: propertyId ? { property_id: propertyId } : {} }).then(r => r.data.sales ?? []),
  create: (data)       => http.post('/admin/sales', data).then(r => r.data),
  update: ({ id, ...rest }) => http.patch(`/admin/sales/${id}`, rest).then(r => r.data),
  remove: (id)         => http.delete(`/admin/sales/${id}`).then(r => r.data),
};

export const useSales = (propertyId) =>
  useQuery({ queryKey: ['sales', propertyId ?? 'all'], queryFn: () => salesApi.list(propertyId) });

export const useCreateSale = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: salesApi.create, onSuccess: () => qc.invalidateQueries({ queryKey: ['sales'] }) });
};

export const useUpdateSale = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: salesApi.update, onSuccess: () => qc.invalidateQueries({ queryKey: ['sales'] }) });
};

export const useDeleteSale = () => {
  const qc = useQueryClient();
  return useMutation({ mutationFn: salesApi.remove, onSuccess: () => qc.invalidateQueries({ queryKey: ['sales'] }) });
};

const guarantorApi = {
  list:   (contractId)        => http.get(`/admin/contracts/${contractId}/guarantors`).then(r => r.data.guarantors ?? []),
  create: ({ contractId, ...data }) => http.post(`/admin/contracts/${contractId}/guarantors`, data).then(r => r.data),
  remove: (id)                => http.delete(`/admin/guarantors/${id}`).then(r => r.data),
};

export const useGuarantors = (contractId) =>
  useQuery({ queryKey: ['guarantors', contractId], queryFn: () => guarantorApi.list(contractId), enabled: !!contractId });

export const useCreateGuarantor = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: guarantorApi.create,
    onSuccess: (_d, vars) => qc.invalidateQueries({ queryKey: ['guarantors', vars.contractId] }),
  });
};

export const useDeleteGuarantor = (contractId) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: guarantorApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['guarantors', contractId] }),
  });
};

// ─── Org / Sucursales (Enterprise multi-sucursal) ─────────────────────────────

export const orgApi = {
  branches:    ()        => http.get('/org/branches').then(r => r.data),
  summary:     ()        => http.get('/org/summary').then(r => r.data),
  createBranch:(data)    => http.post('/org/branches', data).then(r => r.data),
  updateBranch:({ id, ...d }) => http.patch(`/org/branches/${id}`, d).then(r => r.data),
  createManager:({ branchId, ...d }) => http.post(`/org/branches/${branchId}/manager`, d).then(r => r.data),
  reassignProperty:({ propId, branchId }) => http.post(`/admin/properties/${propId}/reassign`, { branch_id: branchId }).then(r => r.data),
  reassignLead:({ leadId, branchId }) => http.post(`/admin/leads/${leadId}/reassign`, { branch_id: branchId }).then(r => r.data),
};

export const useBranches = (enabled = true) =>
  useQuery({ queryKey: ['org', 'branches'], queryFn: orgApi.branches, staleTime: 60_000, enabled });

export const useConsolidatedSummary = (enabled = true) =>
  useQuery({ queryKey: ['org', 'summary'], queryFn: orgApi.summary, staleTime: 30_000, enabled });

export const useCreateBranch = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: orgApi.createBranch,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org', 'branches'] });
      qc.invalidateQueries({ queryKey: ['org', 'summary'] });
      qc.invalidateQueries({ queryKey: ['auth', 'me'] });
    },
  });
};

export const useUpdateBranch = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: orgApi.updateBranch,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org', 'branches'] });
      qc.invalidateQueries({ queryKey: ['auth', 'me'] });
    },
  });
};

export const useCreateManager = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: orgApi.createManager,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['org', 'branches'] }),
  });
};

export const useReassignProperty = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: orgApi.reassignProperty,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys?.properties ?? ['properties'] });
      qc.invalidateQueries({ queryKey: ['org', 'summary'] });
    },
  });
};

export const useReassignLead = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: orgApi.reassignLead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys?.clients ?? ['clients'] });
      qc.invalidateQueries({ queryKey: ['org', 'summary'] });
    },
  });
};

// ─── Documentos (Enterprise — adjuntos a clientes/contratos) ──────────────────

export const documentsApi = {
  list:   (params)  => http.get('/documents', { params }).then(r => r.data),
  upload: (data)    => http.post('/documents', data).then(r => r.data),
  remove: (id)      => http.delete(`/documents/${id}`).then(r => r.data),
  // URL de descarga/visualización (mismo origen, cookie httpOnly se envía sola).
  downloadUrl: (id) => `${API_BASE}/documents/${id}/download`,
};

export const useDocuments = ({ clientId, contractId } = {}) =>
  useQuery({
    queryKey: ['documents', clientId || null, contractId || null],
    queryFn: () => documentsApi.list({
      ...(clientId ? { client_id: clientId } : {}),
      ...(contractId ? { contract_id: contractId } : {}),
    }),
    staleTime: 30_000,
    enabled: !!(clientId || contractId),
  });

// Lista global (sin filtro) → todos los documentos del tenant/sucursal vía RLS.
export const useAllDocuments = () =>
  useQuery({ queryKey: ['documents', 'all'], queryFn: () => documentsApi.list(), staleTime: 30_000 });

export const useUploadDocument = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: documentsApi.upload,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
};

export const useDeleteDocument = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: documentsApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['documents'] }),
  });
};

// ─── Billing / SaaS (plan 09) ────────────────────────────────────────────────

const billingApi = {
  status:    () => http.get('/billing/status').then(r => r.data),
  plans:     () => http.get('/billing/plans').then(r => r.data.plans ?? []),
  subscribe: (plan) => http.post('/billing/subscribe', { plan }).then(r => r.data),
};

export const useBillingStatus = () =>
  useQuery({
    queryKey: keys.billingStatus,
    queryFn:  billingApi.status,
    staleTime: 30_000,
    retry: false,
  });

export const useBillingPlans = () =>
  useQuery({ queryKey: keys.billingPlans, queryFn: billingApi.plans, staleTime: 5 * 60_000 });

export const useSubscribe = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (plan) => billingApi.subscribe(plan),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.billingStatus });
    },
  });
};

// ─── Reportes ejecutivos (Enterprise — métricas mensuales) ────────────────────

export const reportsApi = {
  get:     (period) => http.get('/reports', { params: period ? { period } : {} }).then(r => r.data),
  periods: ()       => http.get('/reports/periods').then(r => r.data),
};

export const useReport = (period) =>
  useQuery({ queryKey: ['reports', period || 'current'], queryFn: () => reportsApi.get(period), staleTime: 60_000 });

export const useReportPeriods = () =>
  useQuery({ queryKey: ['reports', 'periods'], queryFn: reportsApi.periods, staleTime: 5 * 60_000 });

// ─── Exportación CSV (Enterprise) ─────────────────────────────────────────────
// Descarga vía axios (no <a href>) para que viaje el header X-Branch-Id y el CSV
// respete el scope de sucursal (consolidado vs. sucursal entrada).
export async function downloadCsv(dataset, { from, to } = {}) {
  const params = {};
  if (from) params.from = from;
  if (to) params.to = to;
  const res = await http.get(`/exports/${dataset}.csv`, { params, responseType: 'blob' });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${dataset}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


// ─── Email a cliente ───────────────────────────────────────────────────────────
export const useSendClientEmail = (clientId) => {
  return useMutation({
    mutationFn: ({ subject, body }) =>
      http.post(`/admin/clients/${clientId}/email`, { subject, body }).then(r => r.data),
  });
};

// ─── Importación asistida de propiedades (plan 15) ─────────────────────────────
const propertyImportsApi = {
  create: (data) => http.post('/admin/property-imports', data).then(r => r.data),
  mine:   ()     => http.get('/admin/property-imports/mine').then(r => r.data),
  all:    (params = {}) => http.get('/admin/property-imports/all', { params }).then(r => r.data),
  update: (id, data) => http.patch(`/admin/property-imports/${id}`, data).then(r => r.data),
  fileUrl: (requestId, fileId) => `/admin/property-imports/${requestId}/files/${fileId}`,
};

export const useCreatePropertyImport = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: propertyImportsApi.create,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['property-imports-mine'] }),
  });
};

export const useMyPropertyImports = (enabled = true) =>
  useQuery({
    queryKey: ['property-imports-mine'],
    queryFn: propertyImportsApi.mine,
    enabled,
    staleTime: 15_000,
  });

export const useAllPropertyImports = (params = {}, enabled = true) =>
  useQuery({
    queryKey: ['property-imports-all', params],
    queryFn: () => propertyImportsApi.all(params),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });

export const useUpdatePropertyImport = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => propertyImportsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['property-imports-all'] }),
  });
};

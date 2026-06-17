/**
 * GlobalExplorer.jsx — pestaña "Datos" de /superadmin (plan 05).
 *
 * Tablas globales cross-tenant (todas las inmobiliarias) para clientes, propiedades y
 * citas, con columna "Inmobiliaria", buscador, filtro por tenant (selector del shell) y
 * paginación. Edición full vía un editor lateral con confirmación explícita antes de
 * guardar datos ajenos — cada cambio queda auditado en el backend (activity_log).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useSuperadminTenant } from './TenantContext';
import {
  useGlobalClients,
  useGlobalProperties,
  useGlobalAppointments,
  useUpdateGlobalEntity,
} from '../api';

const NAVY = '#164a71';
const PAGE_SIZE = 50;

// Configuración por entidad: hook de listado, columnas de tabla y campos editables.
const ENTITIES = {
  clients: {
    label: 'Clientes',
    columns: [
      { key: 'name', label: 'Nombre' },
      { key: 'phone', label: 'Teléfono' },
      { key: 'email', label: 'Email' },
      { key: 'role', label: 'Rol' },
    ],
    fields: [
      { key: 'name', label: 'Nombre', type: 'text' },
      { key: 'email', label: 'Email', type: 'text' },
      { key: 'role', label: 'Rol', type: 'text' },
      { key: 'notes', label: 'Notas', type: 'textarea' },
    ],
  },
  properties: {
    label: 'Propiedades',
    columns: [
      { key: 'title', label: 'Título' },
      { key: 'type', label: 'Operación' },
      { key: 'status', label: 'Estado' },
      { key: 'price', label: 'Precio' },
    ],
    fields: [
      { key: 'title', label: 'Título', type: 'text' },
      { key: 'description', label: 'Descripción', type: 'textarea' },
      { key: 'price', label: 'Precio', type: 'number' },
      { key: 'currency', label: 'Moneda', type: 'text' },
      { key: 'status', label: 'Estado', type: 'text' },
      { key: 'location', label: 'Ubicación', type: 'text' },
      { key: 'bedrooms', label: 'Dormitorios', type: 'number' },
      { key: 'bathrooms', label: 'Baños', type: 'number' },
      { key: 'area_m2', label: 'Superficie (m²)', type: 'number' },
    ],
  },
  appointments: {
    label: 'Citas',
    columns: [
      { key: 'type', label: 'Tipo' },
      { key: 'status', label: 'Estado' },
      { key: 'start_time', label: 'Inicio' },
      { key: 'notes', label: 'Notas' },
    ],
    fields: [
      { key: 'type', label: 'Tipo', type: 'text' },
      { key: 'status', label: 'Estado', type: 'text' },
      { key: 'notes', label: 'Notas', type: 'textarea' },
    ],
  },
};

const SUB_TABS = [
  { id: 'clients', label: 'Clientes' },
  { id: 'properties', label: 'Propiedades' },
  { id: 'appointments', label: 'Citas-Contratos' },
];

const S = {
  toolbar: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' },
  subTabs: { display: 'flex', gap: 4 },
  subTab: (active) => ({
    appearance: 'none', border: '1px solid var(--border-subtle, #e6e9ee)', cursor: 'pointer',
    padding: '8px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600,
    color: active ? '#fff' : 'var(--fg-secondary, #344054)',
    background: active ? NAVY : 'var(--surface-raised, #fff)',
  }),
  spacer: { flex: 1 },
  search: {
    padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border-subtle, #d0d5dd)',
    fontSize: 13, minWidth: 220, outline: 'none',
  },
  card: {
    border: '1px solid var(--border-subtle, #e6e9ee)', borderRadius: 12, overflow: 'hidden',
    background: 'var(--surface-raised, #fff)',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: {
    textAlign: 'left', padding: '10px 12px', background: 'var(--surface-base, #f6f8fa)',
    color: 'var(--fg-tertiary, #667085)', fontWeight: 600, fontSize: 12,
    borderBottom: '1px solid var(--border-subtle, #e6e9ee)', whiteSpace: 'nowrap',
  },
  td: {
    padding: '10px 12px', borderBottom: '1px solid var(--border-subtle, #f0f2f5)',
    color: 'var(--fg-secondary, #344054)', verticalAlign: 'top',
  },
  tenantPill: {
    display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
    background: 'rgba(22,74,113,0.10)', color: NAVY,
  },
  editBtn: {
    appearance: 'none', border: '1px solid var(--border-subtle, #d0d5dd)', cursor: 'pointer',
    padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: '#fff', color: NAVY,
  },
  empty: { padding: '40px 16px', textAlign: 'center', color: 'var(--fg-tertiary, #667085)' },
  pager: { display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'flex-end', padding: '12px' },
  pagerBtn: (disabled) => ({
    appearance: 'none', border: '1px solid var(--border-subtle, #d0d5dd)', borderRadius: 6,
    padding: '6px 12px', fontSize: 13, fontWeight: 600, background: '#fff',
    color: disabled ? '#aab' : NAVY, cursor: disabled ? 'not-allowed' : 'pointer',
  }),
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(16,24,40,0.45)',
    display: 'flex', justifyContent: 'flex-end', zIndex: 50,
  },
  drawer: {
    width: 'min(440px, 100%)', height: '100%', background: '#fff', boxShadow: '-8px 0 24px rgba(0,0,0,0.12)',
    display: 'flex', flexDirection: 'column',
  },
  drawerHead: { padding: '18px 20px', borderBottom: '1px solid var(--border-subtle, #e6e9ee)' },
  drawerBody: { padding: '18px 20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 14 },
  drawerFoot: { padding: '16px 20px', borderTop: '1px solid var(--border-subtle, #e6e9ee)', display: 'flex', gap: 10, justifyContent: 'flex-end' },
  label: { display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--fg-tertiary, #667085)', marginBottom: 6 },
  input: { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-subtle, #d0d5dd)', fontSize: 13, outline: 'none', boxSizing: 'border-box' },
  warn: { fontSize: 12, color: '#b54708', background: '#fffaeb', border: '1px solid #fedf89', borderRadius: 8, padding: '8px 10px' },
  primary: { appearance: 'none', border: 'none', cursor: 'pointer', padding: '9px 16px', borderRadius: 8, fontSize: 13, fontWeight: 700, background: NAVY, color: '#fff' },
  ghost: { appearance: 'none', border: '1px solid var(--border-subtle, #d0d5dd)', cursor: 'pointer', padding: '9px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, background: '#fff', color: 'var(--fg-secondary, #344054)' },
  err: { fontSize: 12, color: '#d92d20', marginTop: 8 },
};

function cellText(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string' && value.length > 60) return `${value.slice(0, 60)}…`;
  return String(value);
}

function EditDrawer({ entity, row, onClose }) {
  const cfg = ENTITIES[entity];
  const update = useUpdateGlobalEntity(entity);
  const [form, setForm] = useState(() => {
    const init = {};
    cfg.fields.forEach((f) => { init[f.key] = row[f.key] ?? ''; });
    return init;
  });
  const [confirming, setConfirming] = useState(false);
  const drawerRef = useRef(null);

  // Foco modal: al abrir, mover el foco al primer campo y devolverlo al disparador al
  // cerrar. Escape cierra. (Trap completo de Tab quedaría para una lib; esto cubre lo
  // esencial de accesibilidad para un drawer simple.)
  useEffect(() => {
    const opener = document.activeElement;
    const firstField = drawerRef.current?.querySelector('input, textarea, button');
    firstField?.focus();
    function onKey(e) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, [onClose]);

  const changed = useMemo(
    () => cfg.fields.filter((f) => String(form[f.key] ?? '') !== String(row[f.key] ?? '')),
    [cfg.fields, form, row],
  );

  function handleSave() {
    const payload = { id: row.id };
    changed.forEach((f) => {
      const raw = form[f.key];
      payload[f.key] = f.type === 'number' && raw !== '' ? Number(raw) : raw;
    });
    update.mutate(payload, { onSuccess: onClose });
  }

  return (
    <div style={S.overlay} onMouseDown={onClose}>
      <div ref={drawerRef} style={S.drawer} role="dialog" aria-modal="true" aria-label={`Editar ${cfg.label}`} onMouseDown={(e) => e.stopPropagation()}>
        <div style={S.drawerHead}>
          <strong style={{ fontSize: 15, color: NAVY }}>Editar {cfg.label.toLowerCase()}</strong>
          <div style={{ fontSize: 12, color: 'var(--fg-tertiary, #667085)', marginTop: 4 }}>
            Inmobiliaria: <strong>{row.tenant_name || '—'}</strong>
          </div>
        </div>
        <div style={S.drawerBody}>
          {cfg.fields.map((f) => (
            <div key={f.key}>
              <label style={S.label} htmlFor={`f-${f.key}`}>{f.label}</label>
              {f.type === 'textarea' ? (
                <textarea
                  id={`f-${f.key}`}
                  style={{ ...S.input, minHeight: 80, resize: 'vertical' }}
                  value={form[f.key] ?? ''}
                  onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                />
              ) : (
                <input
                  id={`f-${f.key}`}
                  type={f.type === 'number' ? 'number' : 'text'}
                  style={S.input}
                  value={form[f.key] ?? ''}
                  onChange={(e) => setForm((s) => ({ ...s, [f.key]: e.target.value }))}
                />
              )}
            </div>
          ))}
          {confirming && changed.length > 0 && (
            <div style={S.warn}>
              Vas a modificar <strong>{changed.length}</strong> campo(s) de datos reales de
              <strong> {row.tenant_name || 'otra inmobiliaria'}</strong>. Esta acción queda auditada.
            </div>
          )}
          {update.isError && <div style={S.err}>No se pudo guardar. Reintentá.</div>}
        </div>
        <div style={S.drawerFoot}>
          <button type="button" style={S.ghost} onClick={onClose}>Cancelar</button>
          {!confirming ? (
            <button
              type="button"
              style={{ ...S.primary, opacity: changed.length === 0 ? 0.5 : 1 }}
              disabled={changed.length === 0}
              onClick={() => setConfirming(true)}
            >
              Guardar cambios
            </button>
          ) : (
            <button type="button" style={S.primary} disabled={update.isPending} onClick={handleSave}>
              {update.isPending ? 'Guardando…' : 'Confirmar y guardar'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function GlobalExplorer() {
  const { selectedTenantId } = useSuperadminTenant();
  const [entity, setEntity] = useState('clients');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(null);

  const cfg = ENTITIES[entity];
  const params = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ...(selectedTenantId ? { tenant_id: selectedTenantId } : {}),
      ...(search.trim() ? { q: search.trim() } : {}),
    }),
    [page, selectedTenantId, search],
  );
  // Los tres hooks se llaman SIEMPRE (Rules of Hooks); solo el de la entidad visible
  // queda `enabled`. Así cambiar de sub-tab no altera el orden ni la identidad de hooks.
  const clientsQuery = useGlobalClients(params, entity === 'clients');
  const propertiesQuery = useGlobalProperties(params, entity === 'properties');
  const appointmentsQuery = useGlobalAppointments(params, entity === 'appointments');
  const activeQuery =
    entity === 'clients' ? clientsQuery
      : entity === 'properties' ? propertiesQuery
        : appointmentsQuery;
  const { data, isLoading, isError } = activeQuery;

  // Al cambiar el tenant del selector global, volver a la página 1 (otro tenant puede
  // tener menos páginas y dejaría la grilla en "Sin resultados").
  useEffect(() => { setPage(1); }, [selectedTenantId]);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function switchEntity(id) {
    setEntity(id);
    setPage(1);
    setSearch('');
  }

  return (
    <div>
      <div style={S.toolbar}>
        <div style={S.subTabs} role="tablist" aria-label="Entidad">
          {SUB_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`explorer-tab-${t.id}`}
              aria-selected={t.id === entity}
              aria-controls={t.id === entity ? 'explorer-panel' : undefined}
              style={S.subTab(t.id === entity)}
              onClick={() => switchEntity(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <span style={S.spacer} />
        <input
          style={S.search}
          type="search"
          placeholder={`Buscar ${cfg.label.toLowerCase()}…`}
          value={search}
          aria-label={`Buscar ${cfg.label.toLowerCase()}`}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
      </div>

      <div
        style={S.card}
        role="tabpanel"
        id="explorer-panel"
        aria-labelledby={`explorer-tab-${entity}`}
      >
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>Inmobiliaria</th>
              {cfg.columns.map((c) => <th key={c.key} style={S.th}>{c.label}</th>)}
              <th style={S.th} aria-label="Acciones" />
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td style={S.td}><span style={S.tenantPill}>{row.tenant_name || '—'}</span></td>
                {cfg.columns.map((c) => <td key={c.key} style={S.td}>{cellText(row[c.key])}</td>)}
                <td style={S.td}>
                  <button type="button" style={S.editBtn} onClick={() => setEditing(row)}>Editar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <div style={S.empty}>Cargando…</div>}
        {isError && <div style={S.empty}>No se pudieron cargar los datos.</div>}
        {!isLoading && !isError && items.length === 0 && (
          <div style={S.empty}>Sin resultados.</div>
        )}
        {total > 0 && (
          <div style={S.pager}>
            <span style={{ fontSize: 12, color: 'var(--fg-tertiary, #667085)' }}>
              {total} registro(s) · página {page} de {totalPages}
            </span>
            <button type="button" style={S.pagerBtn(page <= 1)} disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              Anterior
            </button>
            <button type="button" style={S.pagerBtn(page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
              Siguiente
            </button>
          </div>
        )}
      </div>

      {editing && <EditDrawer entity={entity} row={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

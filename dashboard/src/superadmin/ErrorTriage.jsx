/**
 * ErrorTriage.jsx — pestaña "Errores" de /superadmin (plan 07).
 *
 * Lista cross-tenant de los reportes de error enviados desde la app, con filtros por
 * estado/gravedad (chips) y por inmobiliaria (selector global del shell). Al abrir un
 * reporte se ve su `context` (ruta, versión, user-agent) y se hace triage: cambiar
 * estado/gravedad y dejar una nota. El backend (require_superadmin) gatea el acceso.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useSuperadminTenant } from './TenantContext';
import { useErrorReports, useUpdateErrorReport } from '../api';
import { useFocusTrap } from '../useFocusTrap';

const NAVY = '#164a71';
const PAGE_SIZE = 50;

const STATUS_OPTIONS = [
  { value: 'open', label: 'Abierto' },
  { value: 'in_progress', label: 'En curso' },
  { value: 'resolved', label: 'Resuelto' },
  { value: 'wont_fix', label: 'No se corrige' },
];
const SEVERITY_OPTIONS = [
  { value: 'low', label: 'Baja' },
  { value: 'med', label: 'Media' },
  { value: 'high', label: 'Alta' },
];

const STATUS_LABEL = Object.fromEntries(STATUS_OPTIONS.map((o) => [o.value, o.label]));
const SEVERITY_LABEL = Object.fromEntries(SEVERITY_OPTIONS.map((o) => [o.value, o.label]));

const SEVERITY_COLOR = {
  high: { bg: '#fee4e2', fg: '#b42318' },
  med: { bg: '#fef0c7', fg: '#b54708' },
  low: { bg: '#edf3ff', fg: NAVY },
};

const S = {
  toolbar: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' },
  chips: { display: 'flex', gap: 6, flexWrap: 'wrap' },
  chip: (active) => ({
    appearance: 'none', border: '1px solid var(--border-subtle, #e6e9ee)', cursor: 'pointer',
    padding: '6px 12px', borderRadius: 999, fontSize: 12, fontWeight: 600,
    color: active ? '#fff' : 'var(--fg-secondary, #344054)',
    background: active ? NAVY : 'var(--surface-raised, #fff)',
  }),
  spacer: { flex: 1 },
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
  rowBtn: {
    appearance: 'none', border: '1px solid var(--border-subtle, #d0d5dd)', cursor: 'pointer',
    padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, background: '#fff', color: NAVY,
  },
  tenantPill: {
    display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
    background: 'rgba(22,74,113,0.10)', color: NAVY,
  },
  sevPill: (sev) => ({
    display: 'inline-block', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
    background: (SEVERITY_COLOR[sev] || SEVERITY_COLOR.low).bg,
    color: (SEVERITY_COLOR[sev] || SEVERITY_COLOR.low).fg,
  }),
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
    width: 'min(480px, 100%)', height: '100%', background: '#fff', boxShadow: '-8px 0 24px rgba(0,0,0,0.12)',
    display: 'flex', flexDirection: 'column',
  },
  drawerHead: { padding: '18px 20px', borderBottom: '1px solid var(--border-subtle, #e6e9ee)' },
  drawerBody: { padding: '18px 20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 14 },
  drawerFoot: { padding: '16px 20px', borderTop: '1px solid var(--border-subtle, #e6e9ee)', display: 'flex', gap: 10, justifyContent: 'flex-end' },
  label: { display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--fg-tertiary, #667085)', marginBottom: 6 },
  input: { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-subtle, #d0d5dd)', fontSize: 13, outline: 'none', boxSizing: 'border-box' },
  message: { fontSize: 14, color: 'var(--fg-primary, #111)', whiteSpace: 'pre-wrap', lineHeight: 1.5 },
  ctx: {
    fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    background: 'var(--surface-base, #f6f8fa)', border: '1px solid var(--border-subtle, #e6e9ee)',
    borderRadius: 8, padding: '10px 12px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0,
  },
  primary: { appearance: 'none', border: 'none', cursor: 'pointer', padding: '9px 16px', borderRadius: 8, fontSize: 13, fontWeight: 700, background: NAVY, color: '#fff' },
  ghost: { appearance: 'none', border: '1px solid var(--border-subtle, #d0d5dd)', cursor: 'pointer', padding: '9px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, background: '#fff', color: 'var(--fg-secondary, #344054)' },
  err: { fontSize: 12, color: '#d92d20', marginTop: 8 },
};

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

function truncate(value, max = 70) {
  if (!value) return '—';
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

function TriageDrawer({ report, onClose }) {
  const update = useUpdateErrorReport();
  const [status, setStatus] = useState(report.status);
  const [severity, setSeverity] = useState(report.severity);
  const [notes, setNotes] = useState(report.triage_notes ?? '');
  // Foco accesible: mueve foco al drawer, atrapa Tab/Shift+Tab adentro, Escape cierra y
  // devuelve el foco al disparador. (WCAG 2.1.2/2.4.3). El call-site remonta por `key`.
  const drawerRef = useFocusTrap(onClose);

  const changed =
    status !== report.status ||
    severity !== report.severity ||
    (notes ?? '') !== (report.triage_notes ?? '');

  function handleSave() {
    update.mutate(
      { id: report.id, status, severity, triage_notes: notes },
      { onSuccess: onClose },
    );
  }

  return (
    <div style={S.overlay} onMouseDown={onClose}>
      <div ref={drawerRef} style={S.drawer} role="dialog" aria-modal="true" aria-label="Triage del reporte" onMouseDown={(e) => e.stopPropagation()}>
        <div style={S.drawerHead}>
          <strong style={{ fontSize: 15, color: NAVY }}>Reporte de error</strong>
          <div style={{ fontSize: 12, color: 'var(--fg-tertiary, #667085)', marginTop: 4 }}>
            {report.tenant_name || '—'} · {report.reporter_email || 'sin email'} · {fmtDate(report.created_at)}
          </div>
        </div>
        <div style={S.drawerBody}>
          <div>
            <span style={S.label}>Mensaje</span>
            <div style={S.message}>{report.message}</div>
          </div>
          <div>
            <span style={S.label}>Contexto</span>
            <pre style={S.ctx}>{JSON.stringify(report.context || {}, null, 2)}</pre>
          </div>
          <div>
            <label style={S.label} htmlFor="triage-status">Estado</label>
            <select id="triage-status" style={S.input} value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label style={S.label} htmlFor="triage-severity">Gravedad</label>
            <select id="triage-severity" style={S.input} value={severity} onChange={(e) => setSeverity(e.target.value)}>
              {SEVERITY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label style={S.label} htmlFor="triage-notes">Notas de triage</label>
            <textarea
              id="triage-notes"
              style={{ ...S.input, minHeight: 80, resize: 'vertical' }}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Diagnóstico, causa, siguiente paso…"
            />
          </div>
          {update.isError && <div style={S.err}>No se pudo guardar el triage. Reintentá.</div>}
        </div>
        <div style={S.drawerFoot}>
          <button type="button" style={S.ghost} onClick={onClose}>Cerrar</button>
          <button
            type="button"
            style={{ ...S.primary, opacity: changed ? 1 : 0.5 }}
            disabled={!changed || update.isPending}
            onClick={handleSave}
          >
            {update.isPending ? 'Guardando…' : 'Guardar triage'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ErrorTriage() {
  const { selectedTenantId } = useSuperadminTenant();
  const [statusFilter, setStatusFilter] = useState('open');
  const [severityFilter, setSeverityFilter] = useState('');
  const [page, setPage] = useState(1);
  const [active, setActive] = useState(null);

  const params = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      ...(statusFilter ? { status: statusFilter } : {}),
      ...(severityFilter ? { severity: severityFilter } : {}),
      ...(selectedTenantId ? { tenant_id: selectedTenantId } : {}),
    }),
    [page, statusFilter, severityFilter, selectedTenantId],
  );
  const { data, isLoading, isError } = useErrorReports(params);

  // Al cambiar un filtro se vuelve a página 1 en el mismo handler (sin effect-derivado,
  // evita el doble render + query con page stale).
  function setStatus(v) { setStatusFilter(v); setPage(1); }
  function setSeverity(v) { setSeverityFilter(v); setPage(1); }

  // El tenant llega del selector global del shell (valor externo, no un handler local):
  // al cambiarlo volvemos a página 1 para no quedar fuera de rango.
  useEffect(() => { setPage(1); }, [selectedTenantId]);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <div style={S.toolbar}>
        <div style={S.chips} role="group" aria-label="Filtrar por estado">
          <button type="button" aria-pressed={statusFilter === ''} style={S.chip(statusFilter === '')} onClick={() => setStatus('')}>Todos</button>
          {STATUS_OPTIONS.map((o) => (
            <button key={o.value} type="button" aria-pressed={statusFilter === o.value} style={S.chip(statusFilter === o.value)} onClick={() => setStatus(o.value)}>
              {o.label}
            </button>
          ))}
        </div>
        <span style={S.spacer} />
        <div style={S.chips} role="group" aria-label="Filtrar por gravedad">
          <button type="button" aria-pressed={severityFilter === ''} style={S.chip(severityFilter === '')} onClick={() => setSeverity('')}>Toda gravedad</button>
          {SEVERITY_OPTIONS.map((o) => (
            <button key={o.value} type="button" aria-pressed={severityFilter === o.value} style={S.chip(severityFilter === o.value)} onClick={() => setSeverity(o.value)}>
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div style={S.card}>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>Inmobiliaria</th>
              <th style={S.th}>Gravedad</th>
              <th style={S.th}>Estado</th>
              <th style={S.th}>Mensaje</th>
              <th style={S.th}>Fecha</th>
              <th style={S.th} aria-label="Acciones" />
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id}>
                <td style={S.td}><span style={S.tenantPill}>{row.tenant_name || '—'}</span></td>
                <td style={S.td}><span style={S.sevPill(row.severity)}>{SEVERITY_LABEL[row.severity] || row.severity}</span></td>
                <td style={S.td}>{STATUS_LABEL[row.status] || row.status}</td>
                <td style={S.td}>{truncate(row.message)}</td>
                <td style={S.td}>{fmtDate(row.created_at)}</td>
                <td style={S.td}>
                  <button type="button" style={S.rowBtn} onClick={() => setActive(row)}>Ver / triage</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <div style={S.empty}>Cargando…</div>}
        {isError && <div style={S.empty}>No se pudieron cargar los reportes.</div>}
        {!isLoading && !isError && items.length === 0 && (
          <div style={S.empty}>Sin reportes para este filtro.</div>
        )}
        {total > 0 && (
          <div style={S.pager}>
            <span style={{ fontSize: 12, color: 'var(--fg-tertiary, #667085)' }}>
              {total} reporte(s) · página {page} de {totalPages}
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

      {active && <TriageDrawer key={active.id} report={active} onClose={() => setActive(null)} />}
    </div>
  );
}

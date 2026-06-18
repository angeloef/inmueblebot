/**
 * PropertyImports.jsx — pestaña "Importaciones" de /superadmin (plan 15).
 *
 * Lista cross-tenant de los pedidos de importación asistida de propiedades.
 * Permite ver archivos adjuntos (descarga base64), cambiar estado y dejar notas.
 * Espeja el patrón de ErrorTriage.jsx.
 */
import React, { useState } from 'react';
import { useSuperadminTenant } from './TenantContext';
import { useAllPropertyImports, useUpdatePropertyImport } from '../api';
import { useFocusTrap } from '../useFocusTrap';

const NAVY = 'var(--accent-600)';
const PAGE_SIZE = 50;

const STATUS_OPTIONS = [
  { value: 'received',    label: 'Recibido' },
  { value: 'in_progress', label: 'En proceso' },
  { value: 'completed',   label: 'Cargadas' },
  { value: 'cancelled',   label: 'Cancelado' },
];
const STATUS_LABEL = Object.fromEntries(STATUS_OPTIONS.map(o => [o.value, o.label]));

const STATUS_COLOR = {
  received:    { bg: 'var(--accent-50)',            fg: NAVY },
  in_progress: { bg: 'var(--state-warning-bg)',     fg: 'var(--warning-700)' },
  completed:   { bg: 'var(--state-success-bg)',     fg: 'var(--state-success-fg)' },
  cancelled:   { bg: 'var(--surface-base)',         fg: 'var(--fg-muted)' },
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
    padding: '5px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
    background: 'var(--surface-raised)', color: NAVY,
  },
  tenantPill: {
    display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
    background: 'var(--accent-50)', color: NAVY,
  },
  statusPill: (status) => ({
    display: 'inline-block', fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
    background: (STATUS_COLOR[status] || STATUS_COLOR.received).bg,
    color: (STATUS_COLOR[status] || STATUS_COLOR.received).fg,
  }),
  empty: { padding: '40px 16px', textAlign: 'center', color: 'var(--fg-tertiary, #667085)' },
  pager: { display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'flex-end', padding: '12px' },
  pagerBtn: (disabled) => ({
    appearance: 'none', border: '1px solid var(--border-subtle, #d0d5dd)', borderRadius: 6,
    padding: '6px 12px', fontSize: 13, fontWeight: 600, background: 'var(--surface-raised)',
    color: disabled ? 'var(--fg-muted)' : NAVY, cursor: disabled ? 'not-allowed' : 'pointer',
  }),
  backdrop: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.38)', zIndex: 300,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  detailBox: {
    background: 'var(--surface-raised, #fff)', borderRadius: 14, boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
    width: 560, maxWidth: '95vw', maxHeight: '85vh', overflow: 'auto', display: 'flex', flexDirection: 'column',
  },
  detailHeader: {
    padding: '18px 20px 14px', borderBottom: '1px solid var(--border-subtle)',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  },
  detailBody: { padding: '16px 20px', flex: 1, display: 'flex', flexDirection: 'column', gap: 14 },
  detailFooter: {
    padding: '14px 20px', borderTop: '1px solid var(--border-subtle)',
    display: 'flex', justifyContent: 'flex-end', gap: 10,
  },
  label: { fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--fg-tertiary)', marginBottom: 4 },
  select: { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-subtle)', background: 'var(--surface-base)', fontSize: 13, color: 'var(--fg-primary)' },
  textarea: { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-subtle)', background: 'var(--surface-base)', fontSize: 13, color: 'var(--fg-primary)', resize: 'vertical', fontFamily: 'inherit', boxSizing: 'border-box' },
  btn: (primary) => ({
    appearance: 'none', cursor: 'pointer', padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600,
    border: primary ? 'none' : '1px solid var(--border-subtle)',
    background: primary ? NAVY : 'var(--surface-raised)',
    color: primary ? '#fff' : 'var(--fg-secondary)',
  }),
  fileRow: {
    display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, padding: '6px 10px',
    background: 'var(--surface-base)', borderRadius: 8, border: '1px solid var(--border-subtle)',
  },
};

function downloadBase64(filename, contentType, data) {
  const a = document.createElement('a');
  a.href = `data:${contentType};base64,${data}`;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function DetailModal({ req, onClose, onSave }) {
  const trapRef = useFocusTrap();
  const [status, setStatus] = useState(req.status);
  const [adminNotes, setAdminNotes] = useState(req.admin_notes || '');
  const [downloading, setDownloading] = useState(null);
  const update = useUpdatePropertyImport();

  const handleSave = () => {
    onSave({ id: req.id, status, admin_notes: adminNotes || null });
  };

  const handleDownload = async (file) => {
    setDownloading(file.id);
    try {
      const token = localStorage.getItem('auth_token') || sessionStorage.getItem('auth_token') || '';
      const res = await fetch(
        `/admin/property-imports/${req.id}/files/${file.id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error('Error al descargar');
      const json = await res.json();
      downloadBase64(json.filename, json.content_type, json.data);
    } catch {
      alert('Error al descargar el archivo');
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div style={S.backdrop} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={S.detailBox} ref={trapRef} role="dialog" aria-modal="true" aria-labelledby="import-detail-title">
        <div style={S.detailHeader}>
          <div>
            <div id="import-detail-title" style={{ fontWeight: 700, fontSize: 15 }}>
              Pedido de importación
            </div>
            <div style={{ fontSize: 12, color: 'var(--fg-muted)', marginTop: 2 }}>
              {req.tenant_name || req.tenant_id} · {req.requester_email}
            </div>
          </div>
          <button style={{ ...S.btn(false), padding: '4px 10px' }} onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
        <div style={S.detailBody}>
          {req.note && (
            <div>
              <div style={S.label}>Nota del cliente</div>
              <div style={{ fontSize: 13, color: 'var(--fg-secondary)', whiteSpace: 'pre-wrap' }}>{req.note}</div>
            </div>
          )}
          {req.files?.length > 0 && (
            <div>
              <div style={S.label}>Archivos ({req.files.length})</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {req.files.map(f => (
                  <div key={f.id} style={S.fileRow}>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.filename}
                    </span>
                    <span style={{ color: 'var(--fg-muted)', flexShrink: 0 }}>
                      {(f.size_bytes / 1024).toFixed(0)} KB
                    </span>
                    <button
                      style={{ ...S.btn(false), padding: '3px 8px', fontSize: 11, flexShrink: 0 }}
                      onClick={() => handleDownload(f)}
                      disabled={downloading === f.id}
                    >
                      {downloading === f.id ? '…' : 'Descargar'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div>
            <label htmlFor="import-status" style={S.label}>Estado</label>
            <select id="import-status" style={S.select} value={status} onChange={e => setStatus(e.target.value)}>
              {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="import-notes" style={S.label}>Notas internas</label>
            <textarea
              id="import-notes"
              style={S.textarea}
              rows={3}
              value={adminNotes}
              onChange={e => setAdminNotes(e.target.value)}
              placeholder="Notas para el equipo (no visibles al cliente)"
              maxLength={4000}
            />
          </div>
          <div style={{ fontSize: 12, color: 'var(--fg-muted)' }}>
            Creado: {new Date(req.created_at).toLocaleString('es-AR')}
            {req.completed_at && ` · Completado: ${new Date(req.completed_at).toLocaleString('es-AR')}`}
          </div>
        </div>
        <div style={S.detailFooter}>
          <button style={S.btn(false)} onClick={onClose}>Cancelar</button>
          <button
            style={S.btn(true)}
            onClick={handleSave}
            disabled={update.isPending}
          >
            {update.isPending ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PropertyImports() {
  const { selectedTenantId } = useSuperadminTenant();
  const [statusFilter, setStatusFilter] = useState(null);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState(null);
  const update = useUpdatePropertyImport();

  const params = { page, page_size: PAGE_SIZE };
  if (statusFilter) params.status = statusFilter;
  if (selectedTenantId) params.tenant_id = selectedTenantId;

  const { data, isLoading } = useAllPropertyImports(params, true);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const receivedTotal = data?.received_total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleSave = (updateData) => {
    update.mutate(updateData, {
      onSuccess: () => {
        setDetail(null);
      },
    });
  };

  return (
    <div>
      <div style={S.toolbar}>
        <div style={S.chips} role="group" aria-label="Filtrar por estado">
          <button style={S.chip(!statusFilter)} onClick={() => { setStatusFilter(null); setPage(1); }}>
            Todos {total > 0 && `(${total})`}
          </button>
          {STATUS_OPTIONS.map(o => (
            <button key={o.value} style={S.chip(statusFilter === o.value)}
              onClick={() => { setStatusFilter(o.value); setPage(1); }}>
              {o.label}
              {o.value === 'received' && receivedTotal > 0 && ` (${receivedTotal})`}
            </button>
          ))}
        </div>
        <div style={S.spacer} />
      </div>

      <div style={S.card}>
        {isLoading ? (
          <div style={S.empty}>Cargando…</div>
        ) : items.length === 0 ? (
          <div style={S.empty}>No hay pedidos de importación.</div>
        ) : (
          <>
            <table style={S.table} aria-label="Pedidos de importación">
              <thead>
                <tr>
                  <th style={S.th}>Inmobiliaria</th>
                  <th style={S.th}>Email</th>
                  <th style={S.th}>Fecha</th>
                  <th style={S.th}>Archivos</th>
                  <th style={S.th}>Estado</th>
                  <th style={S.th}></th>
                </tr>
              </thead>
              <tbody>
                {items.map(req => (
                  <tr key={req.id}>
                    <td style={S.td}>
                      <span style={S.tenantPill}>{req.tenant_name || req.tenant_id?.slice(0, 8)}</span>
                    </td>
                    <td style={S.td}>{req.requester_email}</td>
                    <td style={{ ...S.td, whiteSpace: 'nowrap' }}>
                      {new Date(req.created_at).toLocaleDateString('es-AR')}
                    </td>
                    <td style={S.td}>{req.file_count}</td>
                    <td style={S.td}>
                      <span style={S.statusPill(req.status)}>{STATUS_LABEL[req.status] || req.status}</span>
                    </td>
                    <td style={S.td}>
                      <button style={S.rowBtn} onClick={() => setDetail(req)}>Ver / gestionar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {totalPages > 1 && (
              <div style={S.pager}>
                <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>
                  Pág. {page} de {totalPages}
                </span>
                <button style={S.pagerBtn(page <= 1)} disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                  ← Anterior
                </button>
                <button style={S.pagerBtn(page >= totalPages)} disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                  Siguiente →
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {detail && (
        <DetailModal
          req={detail}
          onClose={() => setDetail(null)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import { useDocuments, useUploadDocument, useDeleteDocument, documentsApi } from './api';

const CATEGORIES = [
  { value: 'dni', label: 'DNI' },
  { value: 'recibo', label: 'Recibo de sueldo' },
  { value: 'contrato_firmado', label: 'Contrato firmado' },
  { value: 'garantia', label: 'Garantía' },
  { value: 'otros', label: 'Otros' },
];
const CAT_LABEL = Object.fromEntries(CATEGORIES.map(c => [c.value, c.label]));
const MAX_BYTES = 5 * 1024 * 1024;

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Dropdown custom que reemplaza el <select> nativo para matchear el design
 * system (la lista nativa del SO no es estilable). El trigger imita un
 * `.field` input y el menú reutiliza las clases `.status-dropdown-*`.
 * @param {{ value: string, options: {value:string,label:string}[], onChange: (v:string)=>void }} props
 */
function DocTypeSelect({ value, options, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const current = options.find(o => o.value === value) ?? options[0];

  const triggerStyle = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
    width: '100%', boxSizing: 'border-box', fontSize: 13, fontFamily: 'inherit',
    padding: '7px 10px', borderRadius: 7, cursor: 'pointer', textAlign: 'left',
    color: 'var(--fg-primary)',
    border: `1px solid ${open ? 'var(--accent-400)' : 'var(--border-default)'}`,
    background: open ? 'var(--surface-raised)' : 'var(--gray-25)',
    boxShadow: open ? 'var(--shadow-focus)' : 'none',
  };

  return (
    <span ref={ref} className={`status-dropdown ${open ? 'open' : ''}`} style={{ position: 'relative', display: 'block' }}>
      <button
        type="button"
        style={triggerStyle}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false); }}
      >
        {current?.label}
        <svg width="9" height="9" viewBox="0 0 8 8" style={{ opacity: 0.5, flexShrink: 0 }} aria-hidden="true">
          <path d="M2 3l2 2 2-2" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>
      {open && (
        <div className="status-dropdown-menu" role="menu" style={{ left: 0, right: 0, minWidth: 0 }}>
          {options.map(opt => (
            <button
              key={opt.value}
              type="button"
              role="menuitemradio"
              aria-checked={opt.value === value}
              className={`status-dropdown-item ${opt.value === value ? 'active' : ''}`}
              onClick={() => { onChange(opt.value); setOpen(false); }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}

/**
 * Panel reusable de documentos. Pasar clientId y/o contractId.
 * @param {{ clientId?: string, contractId?: string, title?: string }} props
 */
export default function DocumentsPanel({ clientId, contractId, title = 'Documentos' }) {
  const { data: docs = [], isLoading } = useDocuments({ clientId, contractId });
  const upload = useUploadDocument();
  const remove = useDeleteDocument();
  const fileRef = useRef(null);

  const [category, setCategory] = useState('dni');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [deleteDocTarget, setDeleteDocTarget] = useState(null);

  async function handleFile(e) {
    setError('');
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError('El archivo supera el máximo de 5 MB.');
      if (fileRef.current) fileRef.current.value = '';
      return;
    }
    try {
      const dataUri = await readAsDataURL(file);
      await upload.mutateAsync({
        ...(clientId ? { client_id: clientId } : {}),
        ...(contractId ? { contract_id: contractId } : {}),
        category,
        filename: file.name,
        content_type: file.type || 'application/octet-stream',
        data: dataUri,
        note: note.trim() || undefined,
      });
      setNote('');
      if (fileRef.current) fileRef.current.value = '';
    } catch (err) {
      setError(err?.response?.data?.detail || 'No se pudo subir el archivo.');
    }
  }

  function handleDelete(doc) {
    setDeleteDocTarget(doc);
  }

  async function confirmDelete() {
    if (!deleteDocTarget) return;
    try {
      await remove.mutateAsync(deleteDocTarget.id);
      setDeleteDocTarget(null);
    } catch (err) {
      setError(err?.response?.data?.detail || 'No se pudo eliminar.');
      setDeleteDocTarget(null);
    }
  }

  return (
    <div className="detail-block">
      <h3>{title}</h3>

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 12 }}>
        <div className="field" style={{ marginBottom: 0, minWidth: 150 }}>
          <label>Tipo de documento</label>
          <DocTypeSelect value={category} options={CATEGORIES} onChange={setCategory} />
        </div>
        <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 140 }}>
          <label>Nota opcional</label>
          <input
            type="text"
            placeholder="p. ej. Enero 2025"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <label className="btn btn-secondary" style={{ cursor: 'pointer', margin: 0, flexShrink: 0 }}>
          {upload.isPending ? 'Subiendo…' : '+ Subir archivo'}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp,image/*,application/pdf"
            onChange={handleFile}
            disabled={upload.isPending}
            style={{ display: 'none' }}
          />
        </label>
      </div>
      {error && <p style={{ color: 'var(--danger-600, #dc2626)', fontSize: 13, marginTop: 0 }}>{error}</p>}

      {isLoading ? (
        <div className="muted" style={{ fontSize: 12 }}>Cargando documentos…</div>
      ) : docs.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>Sin documentos todavía.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {docs.map(d => (
            <div key={d.id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 10px', borderRadius: 8,
              border: '1px solid var(--border)', background: 'var(--surface)',
            }}>
              <span style={{
                fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
                background: 'var(--surface-2, #f3f4f6)', color: 'var(--fg-secondary, #475467)',
                flexShrink: 0,
              }}>{CAT_LABEL[d.category] || d.category}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {d.filename}
                </div>
                <div style={{ fontSize: 11, color: 'var(--muted, #6b7280)' }}>
                  {fmtSize(d.size_bytes)}{d.note ? ` · ${d.note}` : ''}
                </div>
              </div>
              <a
                className="btn btn-ghost btn-sm"
                href={documentsApi.downloadUrl(d.id)}
                target="_blank"
                rel="noopener noreferrer"
                style={{ textDecoration: 'none' }}
              >
                Ver
              </a>
              <button
                className="btn btn-danger btn-sm"
                type="button"
                onClick={() => handleDelete(d)}
                disabled={remove.isPending}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      {deleteDocTarget && (
        <div className="modal-backdrop" onClick={() => setDeleteDocTarget(null)} aria-hidden="true">
          <div className="modal" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Eliminar documento</h3>
              <button className="btn btn-ghost btn-sm close" type="button" onClick={() => setDeleteDocTarget(null)}>✕</button>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0 }}>¿Eliminar <b>{deleteDocTarget.filename}</b>?</p>
              <p style={{ fontSize: 12, color: 'var(--fg-tertiary)', margin: '6px 0 0' }}>Esta acción no se puede deshacer.</p>
            </div>
            <div className="modal-foot">
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => setDeleteDocTarget(null)}>
                Cancelar
              </button>
              <button
                className="btn btn-danger btn-sm"
                type="button"
                disabled={remove.isPending}
                onClick={confirmDelete}
              >
                {remove.isPending ? 'Eliminando…' : 'Eliminar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

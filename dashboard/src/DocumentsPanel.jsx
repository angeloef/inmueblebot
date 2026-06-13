import { useRef, useState } from 'react';
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

  async function handleDelete(doc) {
    if (!window.confirm(`¿Eliminar "${doc.filename}"?`)) return;
    try {
      await remove.mutateAsync(doc.id);
    } catch (err) {
      alert(err?.response?.data?.detail || 'No se pudo eliminar.');
    }
  }

  return (
    <div className="detail-block">
      <h3>{title}</h3>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ minWidth: 150 }}>
          {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
        <input
          type="text"
          placeholder="Nota (opcional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          style={{ flex: 1, minWidth: 140 }}
        />
        <label className="btn btn-secondary" style={{ cursor: 'pointer', margin: 0 }}>
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
    </div>
  );
}

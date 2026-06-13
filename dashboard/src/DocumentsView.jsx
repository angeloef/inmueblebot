import { useAllDocuments, useDeleteDocument, documentsApi } from './api';

const CAT_LABEL = {
  dni: 'DNI', recibo: 'Recibo de sueldo', contrato_firmado: 'Contrato firmado',
  garantia: 'Garantía', otros: 'Otros',
};

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(s) {
  if (!s) return '';
  try { return new Date(s).toLocaleDateString('es-AR'); } catch { return s; }
}

export default function DocumentsView() {
  const { data: docs = [], isLoading } = useAllDocuments();
  const remove = useDeleteDocument();

  async function handleDelete(doc) {
    if (!window.confirm(`¿Eliminar "${doc.filename}"?`)) return;
    try {
      await remove.mutateAsync(doc.id);
    } catch (err) {
      alert(err?.response?.data?.detail || 'No se pudo eliminar.');
    }
  }

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Documentos</h1>
          <p className="sub">
            Todos los archivos cargados (DNI, recibos, contratos firmados). Para subir,
            entrá a la ficha del cliente o del contrato.
          </p>
        </div>
      </div>

      {isLoading ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>Cargando documentos…</p>
      ) : docs.length === 0 ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>
          Todavía no hay documentos. Subí el primero desde la ficha de un cliente o contrato.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {docs.map(d => (
            <div key={d.id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 12px', borderRadius: 8,
              border: '1px solid var(--border)', background: 'var(--surface)',
            }}>
              <span style={{
                fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
                background: 'var(--surface-2, #f3f4f6)', color: 'var(--fg-secondary, #475467)', flexShrink: 0,
              }}>{CAT_LABEL[d.category] || d.category}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {d.filename}
                </div>
                <div style={{ fontSize: 11, color: 'var(--muted, #6b7280)' }}>
                  {fmtSize(d.size_bytes)} · {fmtDate(d.created_at)}{d.uploaded_by ? ` · ${d.uploaded_by}` : ''}
                  {d.note ? ` · ${d.note}` : ''}
                </div>
              </div>
              <a className="btn btn-ghost btn-sm" href={documentsApi.downloadUrl(d.id)}
                 target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                Ver
              </a>
              <button className="btn btn-danger btn-sm" type="button"
                      onClick={() => handleDelete(d)} disabled={remove.isPending}>
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

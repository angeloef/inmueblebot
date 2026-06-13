import { useEffect, useRef, useState } from 'react';
import { Icon, pushToast } from './Primitives';
import { downloadCsv } from './api';

/**
 * Botón de exportación a CSV con rango de fechas opcional.
 * @param {{ dataset: 'leads'|'cobranzas', label?: string }} props
 */
export default function ExportCsv({ dataset, label = 'Exportar CSV' }) {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  async function handleDownload() {
    setBusy(true);
    try {
      await downloadCsv(dataset, { from: from || undefined, to: to || undefined });
      setOpen(false);
    } catch {
      pushToast({ text: 'No se pudo exportar.', kind: 'danger' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button type="button" className="btn btn-secondary" onClick={() => setOpen(v => !v)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <Icon name="download" size={15} />
        {label}
      </button>
      {open && (
        <div className="notif-panel" style={{ right: 0, left: 'auto', minWidth: 240, padding: 14 }}
             onClick={e => e.stopPropagation()}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Rango de fechas (opcional)</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
            <label style={{ fontSize: 12 }}>
              Desde
              <input type="date" value={from} onChange={e => setFrom(e.target.value)}
                     style={{ width: '100%', boxSizing: 'border-box', marginTop: 2 }} />
            </label>
            <label style={{ fontSize: 12 }}>
              Hasta
              <input type="date" value={to} onChange={e => setTo(e.target.value)}
                     style={{ width: '100%', boxSizing: 'border-box', marginTop: 2 }} />
            </label>
          </div>
          <button type="button" className="btn btn-primary" style={{ width: '100%' }}
                  onClick={handleDownload} disabled={busy}>
            {busy ? 'Generando…' : 'Descargar CSV'}
          </button>
        </div>
      )}
    </div>
  );
}

import { useAuth } from './auth';
import { Icon } from './Primitives';
import { useConsolidatedSummary } from './api';

const CARD = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 10, padding: 16,
};

function Stat({ label, value, accent }) {
  return (
    <div style={{ ...CARD, textAlign: 'center' }}>
      <div style={{ fontSize: 28, fontWeight: 800, color: accent || 'var(--fg, #111827)' }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--muted, #6b7280)', marginTop: 2 }}>{label}</div>
    </div>
  );
}

function BranchRow({ b, onEnter }) {
  return (
    <div style={{ ...CARD, display: 'flex', alignItems: 'center', gap: 14 }}>
      <div style={{ width: 36, height: 36, borderRadius: 8, background: 'var(--surface-2, #f3f4f6)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name="building" size={18} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.name}</span>
          <span style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                         background: b.wa_connected ? 'var(--success-500, #16a34a)' : 'var(--border-300, #d0d5dd)' }}
                title={b.wa_connected ? 'WhatsApp conectado' : 'Sin WhatsApp'} />
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted, #6b7280)' }}>
          {b.properties} props · {b.leads} clientes · {b.visits_upcoming} visitas · {b.charges_overdue} morosos
        </div>
      </div>
      <button className="btn btn-secondary" type="button" onClick={() => onEnter(b.id)}>Entrar</button>
    </div>
  );
}

export default function Consolidated({ onNav }) {
  const { me, selectBranch } = useAuth();
  const { data, isLoading } = useConsolidatedSummary();

  const totals = data?.totals || {};
  const branches = data?.branches || [];

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>{me?.org_name || 'Consolidado'}</h1>
          <p className="sub">Resumen de todas tus sucursales. Entrá a una para gestionarla en detalle.</p>
        </div>
        {onNav && (
          <button className="btn btn-primary" type="button" onClick={() => onNav('sucursales')}>
            Gestionar sucursales
          </button>
        )}
      </div>

      {isLoading ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>Cargando consolidado…</p>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 20 }}>
            <Stat label="Sucursales" value={data?.branch_count ?? 0} accent="#155f6f" />
            <Stat label="Propiedades" value={totals.properties ?? 0} />
            <Stat label="Disponibles" value={totals.properties_available ?? 0} accent="#16a34a" />
            <Stat label="Clientes" value={totals.leads ?? 0} />
            <Stat label="Visitas próximas" value={totals.visits_upcoming ?? 0} accent="#3a5fa8" />
            <Stat label="Cobros vencidos" value={totals.charges_overdue ?? 0} accent="#dc2626" />
          </div>

          <h2 style={{ fontSize: 15, margin: '8px 0 12px' }}>Por sucursal</h2>
          {branches.length === 0 ? (
            <p style={{ color: 'var(--muted, #6b7280)' }}>
              No tenés sucursales todavía. {onNav && (
                <button className="btn-link" style={{ background: 'none', border: 'none', color: 'var(--primary-600, #155f6f)', cursor: 'pointer', padding: 0, textDecoration: 'underline' }} onClick={() => onNav('sucursales')}>
                  Creá la primera
                </button>
              )}
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {branches.map(b => <BranchRow key={b.id} b={b} onEnter={selectBranch} />)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

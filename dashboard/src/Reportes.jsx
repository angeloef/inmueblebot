import { useState } from 'react';
import { useAuth } from './auth';
import { useReport, useReportPeriods } from './api';

const CARD = {
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 12, padding: 18,
};

function money(n) { return `$${Number(n || 0).toLocaleString('es-AR')}`; }
function periodLabel(p) {
  const [y, m] = (p || '').split('-');
  const months = ['', 'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  return m ? `${months[parseInt(m, 10)]} ${y}` : p;
}

// Delta vs mes anterior. inverse=true → subir es malo (morosidad, no-show…).
function Delta({ cur, prev, inverse = false, suffix = '' }) {
  const d = Math.round(((cur || 0) - (prev || 0)) * 10) / 10;
  if (!d) return <span style={{ fontSize: 11, color: 'var(--muted, #9ca3af)' }}>=</span>;
  const good = inverse ? d < 0 : d > 0;
  const color = good ? 'var(--success-600, #16a34a)' : 'var(--danger-600, #dc2626)';
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color }}>
      {d > 0 ? '▲' : '▼'} {Math.abs(d)}{suffix}
    </span>
  );
}

function Stat({ label, value, cur, prev, inverse, suffix }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ fontSize: 12, color: 'var(--muted, #6b7280)' }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 22, fontWeight: 700 }}>{value}</span>
        {cur !== undefined && <Delta cur={cur} prev={prev} inverse={inverse} suffix={suffix} />}
      </div>
    </div>
  );
}

function GroupCard({ title, children }) {
  return (
    <div style={CARD}>
      <h3 style={{ margin: '0 0 14px', fontSize: 14 }}>{title}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 16 }}>
        {children}
      </div>
    </div>
  );
}

function MetricGroups({ m, prev }) {
  const f = m.funnel, c = m.cobranzas, ca = m.cartera, de = m.demanda;
  const pf = prev?.funnel, pc = prev?.cobranzas, pca = prev?.cartera;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <GroupCard title="Embudo y conversión">
        <Stat label="Interesados" value={f.leads} cur={f.leads} prev={pf?.leads} />
        <Stat label="Visitas agendadas" value={f.visits_scheduled} cur={f.visits_scheduled} prev={pf?.visits_scheduled} />
        <Stat label="Visitas realizadas" value={f.visits_done} cur={f.visits_done} prev={pf?.visits_done} />
        <Stat label="No-show" value={f.no_show} cur={f.no_show} prev={pf?.no_show} inverse />
        <Stat label="Cierres" value={f.closings} cur={f.closings} prev={pf?.closings} />
        <Stat label="Conv. interesado→visita" value={`${f.rates.lead_to_visit}%`} cur={f.rates.lead_to_visit} prev={pf?.rates?.lead_to_visit} suffix="%" />
        <Stat label="Asistencia" value={`${f.rates.show_rate}%`} cur={f.rates.show_rate} prev={pf?.rates?.show_rate} suffix="%" />
        <Stat label="Cierre/visita" value={`${f.rates.visit_to_close}%`} cur={f.rates.visit_to_close} prev={pf?.rates?.visit_to_close} suffix="%" />
      </GroupCard>

      <GroupCard title="Cobranzas y financiero">
        <Stat label="Cobrado" value={money(c.paid)} cur={c.paid} prev={pc?.paid} />
        <Stat label="Facturado" value={money(c.billed)} />
        <Stat label="% cobrado" value={`${c.pct_cobrado}%`} cur={c.pct_cobrado} prev={pc?.pct_cobrado} suffix="%" />
        <Stat label="Morosidad" value={money(c.morosidad_amount)} cur={c.morosidad_amount} prev={pc?.morosidad_amount} inverse />
        <Stat label="Cobros vencidos" value={c.overdue_count} cur={c.overdue_count} prev={pc?.overdue_count} inverse />
        <Stat label="Contratos por vencer" value={c.contracts_expiring} />
      </GroupCard>

      <GroupCard title="Cartera de propiedades">
        <Stat label="Disponibles" value={ca.available} cur={ca.available} prev={pca?.available} />
        <Stat label="Reservadas" value={ca.reserved} />
        <Stat label="Cerradas" value={ca.closed} cur={ca.closed} prev={pca?.closed} />
        <Stat label="Sin consultas" value={ca.dead} cur={ca.dead} prev={pca?.dead} inverse />
        <Stat label="Antigüedad media" value={`${ca.avg_age_days}d`} cur={ca.avg_age_days} prev={pca?.avg_age_days} inverse suffix="d" />
      </GroupCard>

      <GroupCard title="Demanda de mercado">
        <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 18 }}>
          <DemandaList title="Zonas más buscadas"
            rows={de.top_zones.map(z => ({ k: z.zone, v: `${z.searches} búsq · ${z.inventory} props` }))} />
          <DemandaList title="Demanda sin oferta (gap)"
            rows={de.supply_gaps.map(z => ({ k: z.zone, v: `${z.searches} búsquedas` }))} />
          <DemandaList title="Búsquedas sin resultado"
            rows={de.dead_end_searches.map(s => ({ k: [s.operation, s.type, s.zone].filter(Boolean).join(' · ') || '—', v: `${s.count}` }))} />
        </div>
      </GroupCard>
    </div>
  );
}

function DemandaList({ title, rows }) {
  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--fg-secondary, #475467)' }}>{title}</div>
      {rows.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--muted, #9ca3af)' }}>Sin datos.</div>
      ) : rows.map((r, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12, padding: '3px 0' }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.k}</span>
          <span className="tabular" style={{ color: 'var(--muted, #6b7280)', flexShrink: 0 }}>{r.v}</span>
        </div>
      ))}
    </div>
  );
}

function BranchComparison({ branches }) {
  return (
    <div style={{ ...CARD, overflowX: 'auto' }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14 }}>Comparativa por sucursal</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: 'left', color: 'var(--muted, #6b7280)', fontSize: 12 }}>
            <th style={{ padding: '6px 8px' }}>Sucursal</th>
            <th style={{ padding: '6px 8px' }}>Interesados</th>
            <th style={{ padding: '6px 8px' }}>Visitas</th>
            <th style={{ padding: '6px 8px' }}>Cierres</th>
            <th style={{ padding: '6px 8px' }}>% cobrado</th>
            <th style={{ padding: '6px 8px' }}>Morosos</th>
            <th style={{ padding: '6px 8px' }}>Disponibles</th>
          </tr>
        </thead>
        <tbody>
          {branches.map(b => (
            <tr key={b.branch_id} style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '8px', fontWeight: 600 }}>{b.name}</td>
              <td style={{ padding: '8px' }}>{b.metrics.funnel.leads}</td>
              <td style={{ padding: '8px' }}>{b.metrics.funnel.visits_scheduled}</td>
              <td style={{ padding: '8px' }}>{b.metrics.funnel.closings}</td>
              <td style={{ padding: '8px' }}>{b.metrics.cobranzas.pct_cobrado}%</td>
              <td style={{ padding: '8px' }}>{b.metrics.cobranzas.overdue_count}</td>
              <td style={{ padding: '8px' }}>{b.metrics.cartera.available}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Reportes() {
  const { me } = useAuth();
  const { data: periodsData } = useReportPeriods();
  const [period, setPeriod] = useState('');
  const { data, isLoading } = useReport(period);

  const periods = periodsData?.periods || [];
  const isOrg = data?.scope === 'org';

  return (
    <div className="page-view">
      <div className="page-h">
        <div>
          <h1>Reportes ejecutivos</h1>
          <p className="sub">
            {isOrg ? 'Consolidado de todas las sucursales' : (me?.org_name || 'Tu inmobiliaria')} · comparado con el mes anterior.
          </p>
        </div>
        <select value={period} onChange={(e) => setPeriod(e.target.value)} style={{ minWidth: 150 }}>
          {periods.map(p => (
            <option key={p.period} value={p.is_current ? '' : p.period}>
              {periodLabel(p.period)}{p.is_current ? ' (en curso)' : ''}
            </option>
          ))}
        </select>
      </div>

      {isLoading || !data ? (
        <p style={{ color: 'var(--muted, #6b7280)' }}>Cargando reporte…</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {isOrg ? (
            <>
              <MetricGroups m={data.totals} prev={data.totals_prev} />
              {data.branches?.length > 0 && <BranchComparison branches={data.branches} />}
            </>
          ) : (
            <MetricGroups m={data.metrics} prev={data.prev} />
          )}
        </div>
      )}
    </div>
  );
}

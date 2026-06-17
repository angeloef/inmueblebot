/**
 * PlatformAnalytics.jsx — pestaña "Analítica" de /superadmin (plan 06).
 *
 * Vista visual (charts SVG/CSS a mano, sin librería, consistente con Reportes.jsx) +
 * textual (resumen narrativo determinístico + tablas) de los datos agregados de TODAS
 * las inmobiliarias: negocio/SaaS, uso de producto, salud técnica/ops (fase 2) y
 * drilldown por tenant (tabla ordenable + export CSV client-side). Cada sección maneja
 * sus estados vacío/cargando/error. La alternativa textual a cada chart es a11y por diseño.
 */
import React, { useMemo, useState } from 'react';
import { useAnalyticsOverview, useAnalyticsTenants } from '../api';

// Chart fills must be concrete colors (SVG presentation attributes don't resolve
// CSS var()); these mirror the brand tokens 1:1. UI chrome uses var() directly.
const ACCENT = 'var(--accent-500)';
const DANGER = 'var(--danger-500)';
const MUTED = 'var(--fg-tertiary)';

const S = {
  section: { marginBottom: 28 },
  h2: { fontSize: 12, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--fg-tertiary)', margin: '0 0 12px' },
  narrative: {
    background: 'var(--surface-raised)', border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-xl)', padding: '16px 18px', fontSize: 14, lineHeight: 1.5,
    color: 'var(--fg-secondary)', marginBottom: 20, textWrap: 'pretty',
  },
  kpiGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 },
  kpiCard: {
    background: 'var(--surface-raised)', border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)', padding: '14px 16px', boxShadow: 'var(--shadow-xs)',
  },
  kpiLabel: { fontSize: 12, color: 'var(--fg-tertiary)', fontWeight: 600, marginBottom: 6 },
  kpiValue: { fontSize: 24, fontWeight: 700, color: 'var(--fg-primary)', lineHeight: 1.1, letterSpacing: '-0.01em', fontVariantNumeric: 'tabular-nums' },
  kpiSub: { fontSize: 12, color: 'var(--fg-tertiary)', marginTop: 4 },
  card: {
    background: 'var(--surface-raised)', border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)', padding: 16,
  },
  chartTitle: { fontSize: 13, fontWeight: 600, color: 'var(--fg-secondary)', marginBottom: 10 },
  phase2: {
    background: 'var(--warning-50)', border: '1px solid var(--warning-100)', borderRadius: 'var(--radius-lg)',
    padding: '14px 16px', color: 'var(--warning-700)', fontSize: 13,
  },
  toolbar: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' },
  spacer: { flex: 1 },
  tableCard: { border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', overflow: 'hidden', background: 'var(--surface-raised)' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: (active) => ({
    textAlign: 'left', padding: '10px 12px', background: 'var(--surface-base)',
    color: active ? 'var(--accent-600)' : 'var(--fg-tertiary)', fontWeight: 600, fontSize: 12, cursor: 'pointer',
    borderBottom: '1px solid var(--border-default)', whiteSpace: 'nowrap', userSelect: 'none',
  }),
  thButton: {
    appearance: 'none', background: 'none', border: 'none', padding: 0, margin: 0,
    font: 'inherit', color: 'inherit', cursor: 'pointer', fontWeight: 600,
  },
  td: { padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', color: 'var(--fg-secondary)', fontVariantNumeric: 'tabular-nums' },
  tenantPill: { display: 'inline-block', fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999, background: 'var(--accent-50)', color: 'var(--accent-700)' },
  empty: { padding: '40px 16px', textAlign: 'center', color: 'var(--fg-tertiary)' },
  statusBadge: (ok) => ({
    fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
    background: ok ? 'var(--state-success-bg)' : 'var(--state-neutral-bg)',
    color: ok ? 'var(--state-success-fg)' : 'var(--state-neutral-fg)',
  }),
};

// ── Charts SVG a mano (patrón Reportes.jsx) ──────────────────────────────────

/** Barras verticales simples para una serie [{month,count}]. */
function BarChart({ series, color = ACCENT }) {
  const width = 320;
  const height = 120;
  const pad = 8;
  const max = Math.max(1, ...series.map((d) => d.count));
  const barW = (width - pad * 2) / series.length;
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img"
         aria-label={`Serie mensual: ${series.map((d) => `${d.month}=${d.count}`).join(', ')}`}>
      {series.map((d, i) => {
        const h = (d.count / max) * (height - 28);
        const x = pad + i * barW;
        const y = height - 18 - h;
        return (
          // aria-hidden: el <svg> ya expone la serie completa vía aria-label (fuente única
          // para AT); evita doble lectura de cada etiqueta de barra.
          <g key={d.month} aria-hidden="true">
            <rect x={x + 3} y={y} width={Math.max(2, barW - 6)} height={h} rx={3} style={{ fill: color }} />
            <text x={x + barW / 2} y={height - 5} textAnchor="middle" fontSize="9" style={{ fill: MUTED }}>
              {d.month.slice(5)}
            </text>
            {d.count > 0 && (
              <text x={x + barW / 2} y={y - 3} textAnchor="middle" fontSize="9" style={{ fill: MUTED }}>{d.count}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtMrr(byCurrency) {
  const entries = Object.entries(byCurrency || {});
  if (entries.length === 0) return '—';
  return entries.map(([cur, amt]) => `${cur} ${Number(amt).toLocaleString('es-AR')}`).join(' · ');
}

function pct(rate) {
  return rate == null ? '—' : `${(rate * 100).toFixed(1)}%`;
}

function toCsv(rows) {
  const cols = ['tenant_name', 'subscription_status', 'plan', 'properties', 'appointments',
    'conversations', 'messages', 'conversion_rate', 'mrr_amount', 'currency'];
  const head = cols.join(',');
  const body = rows.map((r) => cols.map((c) => {
    const v = r[c];
    const s = v == null ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(',')).join('\n');
  return `${head}\n${body}`;
}

function downloadCsv(rows) {
  const blob = new Blob([toCsv(rows)], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `analitica-tenants-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  // Revocar diferido: a.click() inicia la descarga async; revocar en el mismo tick puede
  // matar la URL antes de que el navegador la lea (Firefox/Safari).
  setTimeout(() => URL.revokeObjectURL(url), 100);
}

const SORT_COLS = [
  { key: 'tenant_name', label: 'Inmobiliaria' },
  { key: 'subscription_status', label: 'Suscripción' },
  { key: 'properties', label: 'Propiedades', num: true },
  { key: 'appointments', label: 'Citas', num: true },
  { key: 'conversations', label: 'Conversaciones', num: true },
  { key: 'conversion_rate', label: 'Conversión', num: true },
  { key: 'mrr_amount', label: 'MRR', num: true },
];

// ── Secciones ─────────────────────────────────────────────────────────────────

function SaasSection({ saas }) {
  const status = saas.tenants_by_status || {};
  return (
    <section style={S.section}>
      <h2 style={S.h2}>SaaS / Negocio</h2>
      <div style={S.kpiGrid}>
        <div style={S.kpiCard}>
          <div style={S.kpiLabel}>Inmobiliarias</div>
          <div style={S.kpiValue}>{saas.total_tenants}</div>
          <div style={S.kpiSub}>{status.active || 0} activas · {status.trial || 0} trial</div>
        </div>
        <div style={S.kpiCard}>
          <div style={S.kpiLabel}>MRR</div>
          <div style={{ ...S.kpiValue, fontSize: 18 }}>{fmtMrr(saas.mrr_by_currency)}</div>
          <div style={S.kpiSub}>suscripciones activas</div>
        </div>
        <div style={S.kpiCard}>
          <div style={S.kpiLabel}>Bajas (churn)</div>
          <div style={S.kpiValue}>{status.cancelled || 0}</div>
          <div style={S.kpiSub}>canceladas en total</div>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12, marginTop: 12 }}>
        <div style={S.card}>
          <div style={S.chartTitle}>Altas por mes</div>
          <BarChart series={saas.signups_by_month || []} color={ACCENT} />
        </div>
        <div style={S.card}>
          <div style={S.chartTitle}>Bajas por mes</div>
          <BarChart series={saas.churn_by_month || []} color={DANGER} />
        </div>
      </div>
    </section>
  );
}

function UsageSection({ usage }) {
  return (
    <section style={S.section}>
      <h2 style={S.h2}>Uso de producto</h2>
      <div style={S.kpiGrid}>
        <div style={S.kpiCard}><div style={S.kpiLabel}>Propiedades</div><div style={S.kpiValue}>{usage.properties}</div></div>
        <div style={S.kpiCard}><div style={S.kpiLabel}>Citas</div><div style={S.kpiValue}>{usage.appointments}</div></div>
        <div style={S.kpiCard}><div style={S.kpiLabel}>Conversaciones</div><div style={S.kpiValue}>{usage.conversations}</div></div>
        <div style={S.kpiCard}><div style={S.kpiLabel}>Mensajes</div><div style={S.kpiValue}>{usage.messages}</div></div>
        <div style={S.kpiCard}>
          <div style={S.kpiLabel}>Conversión</div>
          <div style={S.kpiValue}>{pct(usage.conversion_rate)}</div>
          <div style={S.kpiSub}>citas / conversaciones</div>
        </div>
      </div>
    </section>
  );
}

function OpsSection({ ops }) {
  return (
    <section style={S.section}>
      <h2 style={S.h2}>Salud técnica / Ops</h2>
      <div style={S.phase2}>
        <strong>Fase 2.</strong> {ops?.note || 'Métricas de ops aún no disponibles.'}
      </div>
    </section>
  );
}

function DrilldownSection() {
  const { data, isLoading, isError } = useAnalyticsTenants();
  const [sort, setSort] = useState({ key: 'properties', dir: 'desc' });
  const items = data?.items ?? [];

  const sorted = useMemo(() => {
    const col = SORT_COLS.find((c) => c.key === sort.key);
    const arr = [...items];
    arr.sort((a, b) => {
      const va = a[sort.key];
      const vb = b[sort.key];
      let cmp;
      if (col?.num) cmp = (va ?? -1) - (vb ?? -1);
      else cmp = String(va ?? '').localeCompare(String(vb ?? ''));
      return sort.dir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [items, sort]);

  function toggleSort(key) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'desc' }));
  }

  return (
    <section style={S.section}>
      <h2 style={S.h2}>Drilldown por inmobiliaria</h2>
      <div style={S.toolbar}>
        <span style={{ fontSize: 13, color: MUTED }}>
          {items.length} inmobiliaria(s) · ordená por columna
        </span>
        <span style={S.spacer} />
        <button type="button" className="btn btn-secondary btn-sm" disabled={items.length === 0} onClick={() => downloadCsv(sorted)}>
          Exportar CSV
        </button>
      </div>
      <div style={S.tableCard}>
        <table style={S.table}>
          <thead>
            <tr>
              {SORT_COLS.map((c) => (
                <th
                  key={c.key}
                  style={S.th(sort.key === c.key)}
                  aria-sort={sort.key === c.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  {/* Botón interno: <th> no es interactivo por sí solo (Tab/Enter/Space). */}
                  <button type="button" style={S.thButton} onClick={() => toggleSort(c.key)}>
                    {c.label}{sort.key === c.key ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.tenant_id}>
                <td style={S.td}><span style={S.tenantPill}>{r.tenant_name}</span></td>
                <td style={S.td}>
                  <span style={S.statusBadge(r.subscription_status === 'active')}>
                    {r.subscription_status || 'sin suscripción'}
                  </span>
                </td>
                <td style={S.td}>{r.properties}</td>
                <td style={S.td}>{r.appointments}</td>
                <td style={S.td}>{r.conversations}</td>
                <td style={S.td}>{pct(r.conversion_rate)}</td>
                <td style={S.td}>{r.mrr_amount != null ? `${r.currency || ''} ${Number(r.mrr_amount).toLocaleString('es-AR')}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {isLoading && <div style={S.empty}>Cargando…</div>}
        {isError && <div style={S.empty}>No se pudieron cargar los datos.</div>}
        {!isLoading && !isError && items.length === 0 && <div style={S.empty}>Sin datos de inmobiliarias.</div>}
      </div>
    </section>
  );
}

export default function PlatformAnalytics() {
  const { data, isLoading, isError } = useAnalyticsOverview();

  if (isLoading) return <div style={S.empty}>Cargando analítica…</div>;
  if (isError) return <div style={S.empty}>No se pudo cargar la analítica de plataforma.</div>;
  if (!data) return <div style={S.empty}>Sin datos.</div>;

  return (
    <div>
      <div style={S.narrative}>{data.narrative}</div>
      <SaasSection saas={data.saas} />
      <UsageSection usage={data.usage} />
      <OpsSection ops={data.ops} />
      <DrilldownSection />
    </div>
  );
}

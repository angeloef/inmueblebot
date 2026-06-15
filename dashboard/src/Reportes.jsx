import { useState, useRef, useEffect, useId } from 'react';
import {
  TrendingUp, PieChart, DollarSign, Users, Handshake, AlertTriangle,
  Activity, Zap, BarChart3, MapPin, Filter, Building2,
  Calendar, Clock, ArrowRight, CheckCircle2, TrendingDown,
} from 'lucide-react';
import { useAuth } from './auth';
import { useReport, useReportPeriods } from './api';
import './ReportesBento.css';

// ─── Formatters ──────────────────────────────────────────────────────────────
function moneyShort(n) {
  const v = Number(n || 0);
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (v >= 1_000) return `$${Math.round(v / 1_000)}K`;
  return `$${Math.round(v)}`;
}
function num(n) { return Number(n || 0).toLocaleString('es-AR'); }
function pct(n) { return `${Number(n || 0).toFixed(0)}%`; }
function periodLong(p) {
  const [y, m] = (p || '').split('-');
  const MO = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
  return m ? `${MO[parseInt(m, 10)]} ${y}` : (p || '');
}

// ─── Lógica de negocio (portada de report.js) ─────────────────────────────────
function buildAreas(f, c, ca, de) {
  const totalProps = (ca.available + ca.dead) || 1;
  const deadShare = Math.round((ca.dead / totalProps) * 100);
  const deadEnd = (de.dead_end_searches || []).reduce((a, s) => a + s.count, 0);
  const topSearch = (de.top_zones || []).reduce((a, z) => a + z.searches, 0);
  const deadEndShare = (topSearch + deadEnd)
    ? Math.round((deadEnd / (topSearch + deadEnd)) * 100) : 0;
  const gaps = (de.supply_gaps || []).length;
  const hi = (v, g, w) => v == null ? 'none' : v >= g ? 'good' : v >= w ? 'warn' : 'bad';
  const lo = (v, g, w) => v == null ? 'none' : v <= g ? 'good' : v <= w ? 'warn' : 'bad';
  return [
    {
      key: 'cobranzas', label: 'Cobranzas', Icon: DollarSign,
      status: hi(c.pct_cobrado, 85, 70),
      value: pct(c.pct_cobrado), note: 'cobrado del mes · meta 85%',
    },
    {
      key: 'embudo', label: 'Embudo', Icon: Filter,
      status: hi(f.rates?.visit_to_close, 18, 12),
      value: pct(f.rates?.visit_to_close), note: 'cierre / visita · meta 18%',
    },
    {
      key: 'cartera', label: 'Cartera', Icon: Building2,
      status: lo(deadShare, 12, 25),
      value: `${deadShare}%`, note: `stock sin consultas · ${ca.dead} props`,
    },
    {
      key: 'demanda', label: 'Demanda', Icon: MapPin,
      status: lo(deadEndShare, 15, 30),
      value: `${deadEndShare}%`,
      note: gaps ? `búsq. sin match · ${gaps} zonas sin oferta` : 'sin búsquedas sin match',
    },
  ];
}

function buildAlerts(isOrg, f, c, ca, de, branches) {
  const out = [];
  if (c.morosidad_amount > 0) out.push({
    tone: 'danger', Icon: DollarSign, priority: 3,
    title: `${moneyShort(c.morosidad_amount)} en morosidad`,
    detail: `${c.overdue_count} cobros vencidos sin regularizar`,
  });
  if (ca.dead > 0) out.push({
    tone: 'warning', Icon: Building2, priority: 2,
    title: `${ca.dead} propiedades sin una sola consulta`,
    detail: `Antigüedad media ${ca.avg_age_days} días en publicación`,
  });
  if (de.supply_gaps?.[0]) out.push({
    tone: 'info', Icon: MapPin, priority: 1,
    title: `Demanda sin oferta en ${de.supply_gaps[0].zone}`,
    detail: `${de.supply_gaps[0].searches} búsquedas y 0 propiedades cargadas`,
  });
  if (c.contracts_expiring > 0) out.push({
    tone: 'warning', Icon: Clock, priority: 1,
    title: `${c.contracts_expiring} contratos vencen en 60 días`,
    detail: 'Anticipá la renovación o la búsqueda de reemplazo',
  });
  if (isOrg && branches?.length) {
    const worst = [...branches].sort(
      (a, b) => (a.metrics?.cobranzas?.pct_cobrado ?? 0) - (b.metrics?.cobranzas?.pct_cobrado ?? 0)
    )[0];
    if (worst?.metrics?.cobranzas?.pct_cobrado < 78) out.push({
      tone: 'danger', Icon: TrendingDown, priority: 2,
      title: `${worst.name} arrastra la cobranza`,
      detail: `Cobra ${pct(worst.metrics.cobranzas.pct_cobrado)} · cierre ${pct(worst.metrics.funnel?.rates?.visit_to_close)}`,
    });
  }
  if (f.no_show > 0) out.push({
    tone: 'neutral', Icon: Calendar, priority: 0,
    title: `${f.no_show} visitas caídas por no-show`,
    detail: `Asistencia ${pct(f.rates?.show_rate)} · recordá confirmar el día previo`,
  });
  return out.sort((a, b) => b.priority - a.priority);
}

// ─── SVG primitivos ───────────────────────────────────────────────────────────
function svgPath(pts) {
  return pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
}

function useMeasuredWidth(fallback = 520) {
  const ref = useRef(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    if (!ref.current) return;
    const measure = () => { const cw = ref.current?.clientWidth; if (cw > 0) setW(cw); };
    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    if (ro) { ro.observe(ref.current); return () => ro.disconnect(); }
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);
  return [ref, w];
}

function Sparkline({ data, width = 56, height = 24, color = 'var(--accent-500)' }) {
  const gid = useId().replace(/:/g, '');
  if (!data || data.length < 2) return <svg width={width} height={height} />;
  const min = Math.min(...data), max = Math.max(...data);
  const pad = 3, span = max - min || 1;
  const xs = (i) => pad + (i / (data.length - 1)) * (width - pad * 2);
  const ys = (v) => height - pad - ((v - min) / span) * (height - pad * 2);
  const pts = data.map((v, i) => [xs(i), ys(v)]);
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <linearGradient id={`sg${gid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.22} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={`${svgPath(pts)} L${last[0]},${height} L${pts[0][0]},${height} Z`} fill={`url(#sg${gid})`} stroke="none" />
      <path d={svgPath(pts)} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TrendChart({ data, labels, height = 208, color = 'var(--accent-500)', fmt = (v) => v }) {
  const gid = useId().replace(/:/g, '');
  const [ref, width] = useMeasuredWidth(520);
  const [hi, setHi] = useState(null);

  if (!data || data.length < 2) {
    return (
      <div ref={ref} style={{ position: 'relative', width: '100%', height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>Sin histórico disponible</span>
      </div>
    );
  }

  const padL = 10, padR = 10, padT = 16, padB = 26;
  const max = Math.max(...data) * 1.12 || 1;
  const n = data.length;
  const xs = (i) => padL + (i / (n - 1)) * (width - padL - padR);
  const ys = (v) => height - padB - (v / max) * (height - padT - padB);
  const pts = data.map((v, i) => [xs(i), ys(v)]);
  const baseY = height - padB;
  const step = width < 360 ? 3 : 2;

  function onMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const idx = Math.max(0, Math.min(n - 1, Math.round(((x - padL) / (width - padL - padR)) * (n - 1))));
    setHi(idx);
  }

  return (
    <div ref={ref} style={{ position: 'relative', width: '100%' }}>
      <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}
        onMouseMove={onMove} onMouseLeave={() => setHi(null)}>
        <defs>
          <linearGradient id={`tg${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.18} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75, 1].map((g, i) => (
          <line key={i} x1={padL} x2={width - padR} y1={ys(max * g)} y2={ys(max * g)}
            stroke="var(--border-subtle)" strokeWidth={1} strokeDasharray="2 4" />
        ))}
        <path d={`${svgPath(pts)} L${pts[n - 1][0]},${baseY} L${pts[0][0]},${baseY} Z`} fill={`url(#tg${gid})`} />
        <path d={svgPath(pts)} fill="none" stroke={color} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        {labels.map((l, i) =>
          (i % step === 0 || i === labels.length - 1)
            ? <text key={i} x={xs(i)} y={height - 8} fontSize={11} textAnchor="middle" fill="var(--fg-muted)">{l}</text>
            : null
        )}
        {hi != null && <line x1={xs(hi)} x2={xs(hi)} y1={padT - 8} y2={baseY} stroke={color} strokeWidth={1} strokeOpacity={0.4} />}
        {hi != null && <circle cx={xs(hi)} cy={ys(data[hi])} r={4.5} fill="var(--surface-raised)" stroke={color} strokeWidth={2.4} />}
        {hi == null && <circle cx={pts[n - 1][0]} cy={pts[n - 1][1]} r={3.4} fill={color} />}
      </svg>
      {hi != null && (
        <div style={{
          position: 'absolute',
          left: Math.max(36, Math.min(width - 36, xs(hi))),
          top: -4, transform: 'translateX(-50%)',
          pointerEvents: 'none',
          background: 'var(--surface-float)', border: '1px solid var(--border-default)',
          borderRadius: 8, boxShadow: 'var(--shadow-md)', padding: '5px 9px',
          whiteSpace: 'nowrap', fontSize: 11, color: 'var(--fg-primary)', fontWeight: 600,
        }}>
          <span style={{ color: 'var(--fg-tertiary)', fontWeight: 500, marginRight: 6 }}>{labels[hi]}</span>
          {fmt(data[hi])}
        </div>
      )}
    </div>
  );
}

function CarteraDonut({ segments, size = 156, thickness = 26, onOpen }) {
  const [hi, setHi] = useState(null);
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const r = (size - thickness) / 2;
  const circ = 2 * Math.PI * r;
  let acc = 0;

  const avail = (segments.find(s => /disponible/i.test(s.label)) || segments[0]).value;
  const pctAvail = Math.round((avail / total) * 100);
  const center = hi != null
    ? { big: Math.round((segments[hi].value / total) * 100) + '%', sub: segments[hi].label }
    : { big: pctAvail + '%', sub: 'disponibles' };

  return (
    <div className="cartera-layout">
      <div className="cartera-donut" style={{ width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border-subtle)" strokeWidth={thickness} />
          {segments.map((s, i) => {
            const frac = s.value / total;
            const dash = frac * circ;
            const el = (
              <circle key={i}
                cx={size / 2} cy={size / 2} r={r} fill="none" stroke={s.color}
                strokeWidth={thickness}
                strokeDasharray={`${dash} ${circ - dash}`}
                strokeDashoffset={-acc * circ}
                strokeLinecap="butt"
                opacity={hi != null && hi !== i ? 0.32 : 1}
                style={{ transition: 'stroke-dasharray .6s var(--ease-out,ease), opacity .18s', cursor: 'pointer' }}
                onMouseEnter={() => setHi(i)} onMouseLeave={() => setHi(null)}
                onClick={() => onOpen?.(s)}
              />
            );
            acc += frac;
            return el;
          })}
        </svg>
        <div className="cartera-center">
          <div className="cartera-center-big" style={hi != null ? { color: segments[hi].color } : null}>
            {center.big}
          </div>
          <div className="cartera-center-sub">{center.sub}</div>
        </div>
      </div>
      <div className="cartera-legend">
        {segments.map((s, i) => {
          const p = Math.round((s.value / total) * 100);
          return (
            <button key={i}
              className={`cartera-leg-row${hi === i ? ' on' : ''}`}
              onMouseEnter={() => setHi(i)} onMouseLeave={() => setHi(null)}
              onClick={() => onOpen?.(s)}
            >
              <span className="cartera-leg-dot" style={{ background: s.color }} />
              <span className="cartera-leg-label">{s.label}</span>
              <span className="cartera-leg-bar">
                <span className="cartera-leg-fill" style={{ width: Math.max(3, p) + '%', background: s.color }} />
              </span>
              <span className="cartera-leg-val">{s.value}</span>
              <span className="cartera-leg-pct">{p}%</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── UI Components ────────────────────────────────────────────────────────────
function Delta({ cur, prev, inverse = false }) {
  const d = Math.round(((cur || 0) - (prev || 0)) * 10) / 10;
  if (!d) return <span className="delta flat">—</span>;
  const good = inverse ? d < 0 : d > 0;
  return (
    <span className={`delta ${good ? 'up' : 'down'}`}>
      {d > 0 ? '▲' : '▼'} {Math.abs(d)}
    </span>
  );
}

function Tile({ c = 1, r = 1, children, className, pad = 16 }) {
  return (
    <div
      className={`tile${className ? ' ' + className : ''}`}
      style={{ gridColumn: `span ${c}`, gridRow: `span ${r}`, padding: pad }}
    >
      {children}
    </div>
  );
}

function TileHead({ icon: Icon, title, right }) {
  return (
    <div className="tile-head">
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        {Icon && <Icon size={14} color="var(--fg-tertiary)" strokeWidth={2} />}
        <span className="tile-title">{title}</span>
      </div>
      {right}
    </div>
  );
}

function KpiTile({ Icon, label, value, sub, cur, prev, inverse, spark, color }) {
  return (
    <Tile c={1} r={1} className="kpi-tile">
      <div className="kpi-tile-top">
        <span className="kpi-tile-ic" style={{ background: `color-mix(in srgb, ${color} 14%, transparent)`, color }}>
          {Icon && <Icon size={15} strokeWidth={2} />}
        </span>
        {cur != null && <Delta cur={cur} prev={prev} inverse={inverse} />}
      </div>
      <div className="kpi-tile-val">{value}</div>
      <div className="kpi-tile-foot">
        <div style={{ minWidth: 0 }}>
          <div className="kpi-tile-label">{label}</div>
          <div className="kpi-tile-sub">{sub}</div>
        </div>
        {spark && <Sparkline data={spark} width={56} height={24} color={color} />}
      </div>
    </Tile>
  );
}

function DemandList({ title, tone, rows }) {
  return (
    <div className="demand-col">
      <div className={`demand-head ${tone}`}>{title}</div>
      {rows.length === 0
        ? <div className="empty-mini">Sin datos.</div>
        : rows.map((r, i) => (
          <div key={i} className="demand-row simple">
            <span className="demand-k">{r.k}</span>
            <span className="demand-v">{r.v}</span>
          </div>
        ))}
    </div>
  );
}

// ─── Constantes ───────────────────────────────────────────────────────────────
const SEM_WORD = { good: 'OK', warn: 'Atención', bad: 'Riesgo', none: 'Sin datos' };

const TREND_TABS = [
  { id: 'leads',    label: 'Interesados', color: 'var(--accent-500)',  fmt: num },
  { id: 'paid',     label: 'Cobrado',     color: 'var(--success-500)', fmt: moneyShort },
  { id: 'closings', label: 'Cierres',     color: 'var(--info-500)',    fmt: num },
];

const RANK_METRICS = [
  { id: 'paid',     label: 'Cobrado',   get: (b) => b.metrics?.cobranzas?.paid ?? 0,       fmt: moneyShort },
  { id: 'closings', label: 'Cierres',   get: (b) => b.metrics?.funnel?.closings ?? 0,       fmt: num },
  { id: 'cobro',    label: '% cobrado', get: (b) => b.metrics?.cobranzas?.pct_cobrado ?? 0, fmt: pct },
];

// ─── Componente principal ─────────────────────────────────────────────────────
export default function Reportes() {
  const { me } = useAuth();
  const { data: periodsData } = useReportPeriods();
  const [period, setPeriod]         = useState('');
  const { data, isLoading }         = useReport(period);
  const [trendTab, setTrendTab]     = useState('leads');
  const [rankMetric, setRankMetric] = useState('paid');
  const [carteraSel, setCarteraSel] = useState(null);

  const periods      = periodsData?.periods || [];
  const isOrg        = data?.scope === 'org';
  const m            = isOrg ? data?.totals     : data?.metrics;
  const prev         = isOrg ? data?.totals_prev : data?.prev;
  const branches     = data?.branches || [];
  const showBranches = isOrg && branches.length > 0;

  const curPeriodStr = period || periods.find(p => p.is_current)?.period || '';
  const isPartial    = !period && periods.some(p => p.is_current);

  if (isLoading || !m) {
    return (
      <div className="page-view">
        {isLoading && <p style={{ color: 'var(--fg-muted)', padding: '20px 28px' }}>Cargando reporte…</p>}
      </div>
    );
  }

  const f  = m.funnel;
  const c  = m.cobranzas;
  const ca = m.cartera;
  const de = m.demanda || { top_zones: [], supply_gaps: [], dead_end_searches: [] };
  const pf = prev?.funnel;
  const pc = prev?.cobranzas;

  // Serie de 2 puntos (anterior → actual) como fallback hasta tener /reports/trend
  const trend2 = {
    leads:     [pf?.leads            ?? 0, f.leads            ?? 0],
    paid:      [pc?.paid             ?? 0, c.paid             ?? 0],
    closings:  [pf?.closings         ?? 0, f.closings         ?? 0],
    morosidad: [pc?.morosidad_amount ?? 0, c.morosidad_amount ?? 0],
  };
  const trendLabels = ['Ant.', 'Actual'];
  const tt = TREND_TABS.find(x => x.id === trendTab);

  const carteraSegs = [
    { label: 'Disponibles',   value: ca.available, color: 'var(--success-500)' },
    { label: 'Reservadas',    value: ca.reserved,  color: 'var(--warning-500)' },
    { label: 'Cerradas',      value: ca.closed,    color: 'var(--info-500)'    },
    { label: 'Sin consultas', value: ca.dead,      color: 'var(--danger-500)'  },
  ];
  const carteraTotal = ca.available + ca.reserved + ca.closed + ca.dead;

  const areas  = buildAreas(f, c, ca, de);
  const alerts = buildAlerts(isOrg, f, c, ca, de, branches);

  const rm       = RANK_METRICS.find(x => x.id === rankMetric);
  const rankRows = [...branches]
    .map(b => ({ name: b.name, val: rm.get(b) }))
    .sort((a, b) => b.val - a.val);
  const maxRank = Math.max(...rankRows.map(r => r.val)) || 1;

  return (
    <div className="page-view bento-page">

      {/* ── Cabecera ── */}
      <div className="page-h">
        <div>
          <h1>Reportes ejecutivos</h1>
          <p className="sub">
            {isOrg ? 'Consolidado de todas las sucursales' : (me?.org_name || 'Tu inmobiliaria')}
            {curPeriodStr ? ` · ${periodLong(curPeriodStr)}` : ''}
          </p>
        </div>
        <div className="page-h-actions" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {isPartial && (
            <span className="pill warning">
              <Clock size={11} strokeWidth={2} /> En curso
            </span>
          )}
          <div className="period-wrap">
            <Calendar size={15} color="var(--fg-tertiary)" strokeWidth={2} />
            <select
              className="period"
              value={period}
              onChange={(e) => { setPeriod(e.target.value); setCarteraSel(null); }}
            >
              {periods.map(p => (
                <option key={p.period} value={p.is_current ? '' : p.period}>
                  {periodLong(p.period)}{p.is_current ? ' · en curso' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* ── Grilla Bento ── */}
      <div className="bento-grid">

        {/* Fila 1 — Tendencia (2×2) */}
        <Tile c={2} r={2} className="tile-trend">
          <TileHead
            icon={TrendingUp}
            title="Tendencia · vs mes anterior"
            right={
              <div className="seg sm">
                {TREND_TABS.map(x => (
                  <button key={x.id} className={`seg-btn${trendTab === x.id ? ' on' : ''}`}
                    onClick={() => setTrendTab(x.id)}>
                    {x.label}
                  </button>
                ))}
              </div>
            }
          />
          <div className="trend-body">
            <TrendChart data={trend2[trendTab]} labels={trendLabels} color={tt.color} fmt={tt.fmt} height={208} />
          </div>
        </Tile>

        {/* Fila 1 — Cartera (2×2) */}
        <Tile c={2} r={2} className="tile-cartera">
          <TileHead
            icon={PieChart}
            title="Cartera de propiedades"
            right={<span className="tile-total">{carteraTotal} props</span>}
          />
          <div className="cartera-body">
            <CarteraDonut segments={carteraSegs} onOpen={setCarteraSel} />
          </div>
          {carteraSel && (
            <button className="cartera-cta" onClick={() => setCarteraSel(null)}>
              <span className="cartera-cta-dot" style={{ background: carteraSel.color }} />
              <span className="cartera-cta-txt">Ver {carteraSel.value} {carteraSel.label.toLowerCase()}</span>
              <ArrowRight size={15} strokeWidth={2.2} />
            </button>
          )}
        </Tile>

        {/* Fila 2 — KPIs (4 × 1×1) */}
        <KpiTile
          Icon={DollarSign} label="Cobrado"
          value={moneyShort(c.paid)} sub={`${pct(c.pct_cobrado)} facturado`}
          cur={c.paid} prev={pc?.paid}
          spark={trend2.paid} color="var(--success-500)"
        />
        <KpiTile
          Icon={Users} label="Interesados"
          value={num(f.leads)} sub={`${num(f.visits_scheduled)} agendaron`}
          cur={f.leads} prev={pf?.leads}
          spark={trend2.leads} color="var(--accent-500)"
        />
        <KpiTile
          Icon={Handshake} label="Cierres"
          value={num(f.closings)} sub={`${pct(f.rates?.visit_to_close)} cierre/visita`}
          cur={f.closings} prev={pf?.closings}
          spark={trend2.closings} color="var(--info-500)"
        />
        <KpiTile
          Icon={AlertTriangle} label="Morosidad"
          value={moneyShort(c.morosidad_amount)} sub={`${num(c.overdue_count)} vencidos`}
          cur={c.morosidad_amount} prev={pc?.morosidad_amount}
          inverse spark={trend2.morosidad} color="var(--danger-500)"
        />

        {/* Fila 3 — Semáforo (2×2) */}
        <Tile c={2} r={2} className="tile-semaforo">
          <div className="eyebrow">
            <Activity size={13} strokeWidth={2} /> Estado por área
          </div>
          <div className="sem-list">
            {areas.map(a => (
              <div key={a.key} className={`sem-row ${a.status}`}>
                <span className="sem-ic"><a.Icon size={16} strokeWidth={2} /></span>
                <div className="sem-mid">
                  <div className="sem-label">{a.label}</div>
                  <div className="sem-note">{a.note}</div>
                </div>
                <div className="sem-val">{a.value}</div>
                <span className={`sem-tag ${a.status}`}>{SEM_WORD[a.status]}</span>
              </div>
            ))}
          </div>
        </Tile>

        {/* Fila 3 — Alertas (2×2) */}
        <Tile c={2} r={2} className="tile-alerts">
          <TileHead
            icon={Zap}
            title="Señales accionables"
            right={alerts.length ? <span className="tile-count">{alerts.length}</span> : null}
          />
          <div className="tile-alerts-list">
            {alerts.length ? alerts.slice(0, 4).map((a, i) => (
              <div key={i} className={`alert-card mini ${a.tone}`}>
                <span className="alert-ic"><a.Icon size={15} strokeWidth={2} /></span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="alert-title">{a.title}</div>
                  <div className="alert-detail">{a.detail}</div>
                </div>
                <button className="alert-cta icon">
                  <ArrowRight size={15} strokeWidth={2.2} />
                </button>
              </div>
            )) : (
              <div className="empty-tile">
                <CheckCircle2 size={20} color="var(--success-500)" />
                <span>Todo en orden. Sin alertas.</span>
              </div>
            )}
          </div>
        </Tile>

        {/* Fila 4 — Sucursales (2×2, solo org) */}
        {showBranches && (
          <Tile c={2} r={2} className="tile-rank">
            <TileHead
              icon={BarChart3}
              title="Sucursales"
              right={
                <div className="seg sm">
                  {RANK_METRICS.map(x => (
                    <button key={x.id} className={`seg-btn${rankMetric === x.id ? ' on' : ''}`}
                      onClick={() => setRankMetric(x.id)}>
                      {x.label}
                    </button>
                  ))}
                </div>
              }
            />
            <div className="rank-list">
              {rankRows.map((b, i) => (
                <div key={i} className="rank-row">
                  <div className="rank-name">
                    <span className="rank-pos">{i + 1}</span>
                    <span style={{ fontWeight: 600 }}>{b.name.replace('Sucursal ', '')}</span>
                  </div>
                  <div className="rank-track">
                    <div className="rank-fill" style={{
                      width: `${Math.max(6, (b.val / maxRank) * 100)}%`,
                      background: i === 0 ? 'var(--accent-500)'
                        : i === rankRows.length - 1 ? 'var(--danger-500)'
                        : 'var(--accent-300)',
                    }} />
                  </div>
                  <div className="rank-val">{rm.fmt(b.val)}</div>
                </div>
              ))}
            </div>
          </Tile>
        )}

        {/* Fila 4 — Demanda (2×2 o 4×2 si no hay ranking) */}
        <Tile c={showBranches ? 2 : 4} r={2} className="tile-demand">
          <TileHead icon={MapPin} title="Demanda de mercado" />
          <div className="demand-grid" style={{
            marginTop: 10,
            gridTemplateColumns: showBranches ? '1fr' : 'repeat(3, 1fr)',
          }}>
            <DemandList
              title="Zonas más buscadas" tone="accent"
              rows={de.top_zones.slice(0, showBranches ? 3 : 5).map(z => ({
                k: z.zone,
                v: `${z.searches} búsq · ${z.inventory}p`,
              }))}
            />
            {!showBranches && (
              <DemandList
                title="Demanda sin oferta" tone="warning"
                rows={de.supply_gaps.map(z => ({ k: z.zone, v: `${z.searches}` }))}
              />
            )}
            {!showBranches && (
              <DemandList
                title="Sin resultado" tone="danger"
                rows={de.dead_end_searches.map(s => ({
                  k: [s.operation, s.type, s.zone].filter(Boolean).join(' · ') || '—',
                  v: `${s.count}`,
                }))}
              />
            )}
          </div>
        </Tile>

      </div>
    </div>
  );
}

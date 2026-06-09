'use client'

import { useState } from 'react'
import { Icon, Avatar, Badge, Reveal } from './atoms'

function KpiCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '14px 16px' }}>
      <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 10.5, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--muted-soft)' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 30, letterSpacing: '-1px', color: 'var(--ink)', margin: '4px 0 2px' }}>{value}</div>
      <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--muted-soft)' }}>{sub}</div>
    </div>
  )
}

function PanelView() {
  const funnel = [
    { l: 'Todos los contactos', n: 142, w: 100 },
    { l: 'Calificados',         n: 38,  w: 27  },
    { l: 'Con visita / oferta', n: 14,  w: 16  },
    { l: 'Contrato firmado',    n: 6,   w: 9   },
  ]
  const citas = [
    { t: 'Carlos',     p: 'Av. Andresito 1979',  d: 'Jue 28 · 11:00', tone: 'emerald' as const, s: 'Conf.'  },
    { t: 'María',      p: 'Av. Sarmiento 744',   d: 'Vie 29 · 10:00', tone: 'blue'    as const, s: 'Nuevo'  },
    { t: 'Sin nombre', p: 'Calle Santa Fe 1100', d: 'Vie 29 · 15:00', tone: 'violet'  as const, s: 'Agend.' },
  ]
  return (
    <div className="panel-inner" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
          <KpiCard label="Visitas hoy"      value="4"   sub="2 confirmadas"  />
          <KpiCard label="Clientes activos" value="142" sub="+3 esta semana" />
          <KpiCard label="Propiedades"      value="50"  sub="50 disponibles" />
        </div>
        <div style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 18 }}>
          <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 14, color: 'var(--ink)', marginBottom: 16 }}>Embudo de clientes</div>
          {funnel.map(f => (
            <div key={f.l} style={{ marginBottom: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--body)', marginBottom: 6 }}>
                <span>{f.l}</span><span style={{ fontWeight: 600 }}>{f.n}</span>
              </div>
              <div style={{ height: 7, borderRadius: 4, background: 'var(--surface-card)' }}>
                <div style={{ width: `${f.w}%`, height: '100%', borderRadius: 4, background: 'var(--primary)' }} />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 18 }}>
        <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 14, color: 'var(--ink)', marginBottom: 14 }}>Próximas citas</div>
        {citas.map((c, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderBottom: i < 2 ? '1px solid var(--hairline-soft)' : 'none' }}>
            <Avatar initials={c.t === 'Sin nombre' ? 'S' : c.t[0]} size={32} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13, color: 'var(--ink)' }}>{c.t}</div>
              <div style={{ fontFamily: 'var(--font-body)', fontSize: 11.5, color: 'var(--muted-soft)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.d} · {c.p}</div>
            </div>
            <Badge tone={c.tone} dot>{c.s}</Badge>
          </div>
        ))}
      </div>
    </div>
  )
}

function ClientesView() {
  const rows = [
    { n: 'Carlos Giménez', tone: 'emerald' as const, tipo: 'Inquilino',   tel: '5493764 55-0999', v: 3, u: 'hace 2 días'  },
    { n: 'María Pereyra',  tone: 'blue'    as const, tipo: 'Prospecto',   tel: '5493764 41-2208', v: 1, u: 'hace 4 días'  },
    { n: 'Sin nombre',     tone: 'amber'   as const, tipo: 'Prospecto',   tel: '5493754 53-2056', v: 0, u: 'hace 16 días' },
    { n: 'Sin nombre',     tone: 'amber'   as const, tipo: 'Prospecto',   tel: '5493754 45-5340', v: 0, u: 'hace 22 días' },
    { n: 'Lucía Ferreyra', tone: 'teal'    as const, tipo: 'Propietario', tel: '5493764 60-1187', v: 2, u: 'hace 5 días'  },
  ]
  return (
    <div style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1.3fr .6fr 1fr', padding: '11px 18px', borderBottom: '1px solid var(--hairline)', fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 10.5, letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--muted-soft)' }}>
        <span>Cliente</span><span>Tipo</span><span>Teléfono</span><span>Visitas</span><span>Últ. contacto</span>
      </div>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1.3fr .6fr 1fr', alignItems: 'center', padding: '11px 18px', borderBottom: i < rows.length - 1 ? '1px solid var(--hairline-soft)' : 'none' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Avatar initials={r.n === 'Sin nombre' ? 'SN' : r.n.split(' ').map(x => x[0]).join('')} size={30} bg={r.n === 'Sin nombre' ? 'var(--surface-card)' : undefined} fg={r.n === 'Sin nombre' ? 'var(--muted-soft)' : undefined} />
            <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13.5, color: r.n === 'Sin nombre' ? 'var(--muted)' : 'var(--ink)' }}>{r.n}</span>
          </span>
          <span><Badge tone={r.tone} dot>{r.tipo}</Badge></span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, color: 'var(--muted)' }}>{r.tel}</span>
          <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--body)' }}>{r.v}</span>
          <span style={{ fontFamily: 'var(--font-body)', fontSize: 12.5, color: 'var(--muted-soft)' }}>{r.u}</span>
        </div>
      ))}
    </div>
  )
}

function AgendaView() {
  const slots = [
    { t: '08:30', who: 'Visita · Av. Andresito 1721',  on: false },
    { t: '10:00', who: 'Visita · Av. Sarmiento 744',   on: true  },
    { t: '12:15', who: 'Visita · Calle Chaco 3082',    on: false },
    { t: '15:00', who: 'Visita · Calle Santa Fe 1100', on: true  },
  ]
  return (
    <div style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ padding: '13px 18px', borderBottom: '1px solid var(--hairline-soft)', display: 'flex', alignItems: 'center', gap: 10 }}>
        <Icon name="calendar" size={18} color="var(--primary)" />
        <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 14, color: 'var(--ink)' }}>Viernes 29 de mayo</span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-body)', fontSize: 12.5, color: 'var(--muted-soft)' }}>4 visitas</span>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 9 }}>
        {slots.map((s, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 13, padding: '12px 14px', borderRadius: 10, background: s.on ? 'var(--brand-tint)' : 'var(--surface-soft)', borderLeft: `3px solid ${s.on ? 'var(--primary)' : 'var(--surface-strong)'}` }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500, fontSize: 13, color: s.on ? 'var(--primary)' : 'var(--muted)' }}>{s.t}</span>
            <span style={{ fontFamily: 'var(--font-body)', fontWeight: 500, fontSize: 13.5, color: 'var(--ink)' }}>{s.who}</span>
            {s.on
              ? <Badge tone="emerald" dot style={{ marginLeft: 'auto' }}>Sincronizado</Badge>
              : <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--muted-soft)' }}>pendiente</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

function PropiedadesView() {
  const props = [
    { d: 'Calle Carhué 262',      b: 'Villa Stemberg', m: '3 amb · 104 m²', p: 'USD 78.962',  grad: '#2e6ea0,#164a71' },
    { d: 'Av. Sarmiento 744',     b: 'Barrio Copisa',  m: '4 amb · 296 m²', p: 'USD 149.612', grad: '#3a7a52,#1f5a37' },
    { d: 'Calle Corrientes 1395', b: 'Villa Stemberg', m: '4 amb · 252 m²', p: 'USD 148.520', grad: '#7a5fa0,#4a3570' },
  ]
  return (
    <div className="prop-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14 }}>
      {props.map((p, i) => (
        <div key={i} style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <div style={{ height: 96, background: `linear-gradient(135deg, ${p.grad})`, position: 'relative' }}>
            <span style={{ position: 'absolute', top: 8, left: 8 }}><Badge tone="emerald" dot>Disponible</Badge></span>
          </div>
          <div style={{ padding: '11px 13px 13px' }}>
            <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13.5, color: 'var(--ink)' }}>{p.d}</div>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--muted-soft)', margin: '2px 0' }}>{p.b} · {p.m}</div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--primary)', marginTop: 4 }}>{p.p}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

const TABS = [
  { id: 'panel',    label: 'Panel de control', icon: 'layout-dashboard' },
  { id: 'clientes', label: 'Clientes',         icon: 'users'            },
  { id: 'agenda',   label: 'Calendario',       icon: 'calendar'         },
  { id: 'props',    label: 'Propiedades',      icon: 'building-2'       },
]

export default function ProductShowcase() {
  const [tab, setTab] = useState('panel')

  const views: Record<string, React.ReactNode> = {
    panel:    <PanelView />,
    clientes: <ClientesView />,
    agenda:   <AgendaView />,
    props:    <PropiedadesView />,
  }

  return (
    <section style={{ background: 'var(--surface-soft)', borderTop: '1px solid var(--hairline-soft)', borderBottom: '1px solid var(--hairline-soft)', marginTop: 92 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '84px 28px' }}>
        <Reveal style={{ textAlign: 'center', maxWidth: 680, margin: '0 auto 40px' }}>
          <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--primary)' }}>El panel</span>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 40, letterSpacing: '-1.3px', color: 'var(--ink)', margin: '12px 0 0' }}>Todo tu negocio, en una pantalla.</h2>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 17, color: 'var(--muted)', margin: '14px 0 0' }}>Mientras el bot trabaja en WhatsApp, vos ves el pipeline al día desde el celular o la compu.</p>
        </Reveal>

        <Reveal delay={100}>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 24, flexWrap: 'wrap' }}>
            {TABS.map(t => {
              const active = tab === t.id
              return (
                <button key={t.id} onClick={() => setTab(t.id)} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8, height: 40, padding: '0 16px', cursor: 'pointer',
                  borderRadius: 'var(--radius-pill)', border: `1px solid ${active ? 'var(--primary)' : 'var(--hairline)'}`,
                  background: active ? 'var(--primary)' : '#fff', color: active ? '#fff' : 'var(--body)',
                  fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13.5, transition: 'all .15s',
                }}>
                  <Icon name={t.icon} size={16} /> {t.label}
                </button>
              )
            })}
          </div>

          <div style={{ background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-lg)', overflow: 'hidden' }}>
            <div style={{ height: 40, background: '#fff', borderBottom: '1px solid var(--hairline-soft)', display: 'flex', alignItems: 'center', gap: 7, padding: '0 16px' }}>
              {['#ff5f57', '#febc2e', '#28c840'].map(c => <span key={c} style={{ width: 11, height: 11, borderRadius: '50%', background: c }} />)}
              <span style={{ marginLeft: 12, fontFamily: 'var(--font-body)', fontSize: 12.5, color: 'var(--muted-soft)' }}>app.viviendapp.com.ar / {tab}</span>
            </div>
            <div key={tab} style={{ padding: 22, animation: 'fadeIn .3s ease' }}>
              {views[tab]}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

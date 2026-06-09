'use client'

// TODO(Fase 3): integrar checkout con MercadoPago. Botones apuntan a /signup por ahora.

import { useState } from 'react'
import { Icon, LandingButton, Reveal } from './atoms'

const PLANS = [
  {
    id: 'starter',
    name: 'Starter',
    tag: null,
    monthly: 55000,
    annual: 44000,
    annualTotal: 528000,
    desc: 'Para agentes independientes y dueños que recién arrancan.',
    cta: 'Empezar gratis',
    features: [
      '1 número de WhatsApp Business',
      'Hasta 300 conversaciones / mes',
      'Búsqueda semántica de propiedades',
      'Agenda de visitas con Google Calendar',
      'CRM básico (leads + seguimiento)',
      'Soporte por email',
    ],
    highlighted: false,
  },
  {
    id: 'pro',
    name: 'Pro',
    tag: 'Más popular',
    monthly: 66000,
    annual: 52800,
    annualTotal: 633600,
    desc: 'Para inmobiliarias con equipo que quieren escalar sin contratar.',
    cta: 'Empezar gratis',
    features: [
      'Todo lo de Starter',
      'Hasta 2.000 conversaciones / mes',
      'Hasta 3 agentes',
      'Reportes y métricas avanzadas',
      'Multicanal (próximamente: Instagram DMs)',
      'Soporte prioritario (chat en vivo)',
      'Onboarding guiado 1:1',
    ],
    highlighted: true,
  },
  {
    id: 'equipo',
    name: 'Equipo',
    tag: null,
    monthly: 110000,
    annual: 88000,
    annualTotal: 1056000,
    desc: 'Para desarrolladoras y carteras grandes con múltiples marcas.',
    cta: 'Hablar con ventas',
    features: [
      'Todo lo de Pro',
      'Conversaciones ilimitadas',
      'Agentes ilimitados',
      'Sub-cuentas por sucursal',
      'Integraciones custom (API)',
      'SLA garantizado 99,9 %',
      'Cuenta dedicada',
    ],
    highlighted: false,
  },
]

const MATRIX = [
  { label: 'Conversaciones / mes',        starter: '300',          pro: '2.000',         equipo: 'Ilimitadas' },
  { label: 'Agentes',                      starter: '1',            pro: 'Hasta 3',       equipo: 'Ilimitados' },
  { label: 'Google Calendar',              starter: true,           pro: true,            equipo: true         },
  { label: 'CRM leads',                    starter: true,           pro: true,            equipo: true         },
  { label: 'Reportes avanzados',           starter: false,          pro: true,            equipo: true         },
  { label: 'Multicanal',                   starter: false,          pro: 'Próximamente',  equipo: 'Próximamente'},
  { label: 'API / integraciones custom',   starter: false,          pro: false,           equipo: true         },
  { label: 'Sub-cuentas por sucursal',     starter: false,          pro: false,           equipo: true         },
  { label: 'Soporte',                      starter: 'Email',        pro: 'Chat en vivo',  equipo: 'Dedicado'   },
]

function Check({ ok }: { ok: boolean | string }) {
  if (typeof ok === 'string') return <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--muted)' }}>{ok}</span>
  return ok
    ? <Icon name="check" size={17} color="var(--primary)" />
    : <Icon name="minus" size={17} color="var(--hairline)" />
}

function formatARS(n: number) {
  return '$' + n.toLocaleString('es-AR')
}

export default function Pricing() {
  const [annual, setAnnual] = useState(false)
  const [matrixOpen, setMatrixOpen] = useState(false)

  return (
    <section id="precios" style={{ maxWidth: 1200, margin: '0 auto', padding: '96px 28px 0' }}>
      {/* Header */}
      <Reveal style={{ textAlign: 'center', marginBottom: 44 }}>
        <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--primary)' }}>Precios</span>
        <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 38, letterSpacing: '-1.3px', color: 'var(--ink)', margin: '12px 0 0' }}>
          Simples y transparentes.
        </h2>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 17, color: 'var(--muted)', margin: '12px 0 0' }}>
          30 días gratis con el plan completo. Sin tarjeta de crédito.
        </p>

        {/* Toggle */}
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12, marginTop: 24, background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 99, padding: '6px 18px' }}>
          <button
            onClick={() => setAnnual(false)}
            style={{ fontFamily: 'var(--font-body)', fontWeight: annual ? 400 : 600, fontSize: 14, color: annual ? 'var(--muted)' : 'var(--ink)', background: annual ? 'none' : '#fff', border: 'none', borderRadius: 99, padding: '5px 14px', cursor: 'pointer', boxShadow: annual ? 'none' : '0 1px 4px rgba(0,0,0,.09)', transition: 'all .18s' }}
          >
            Mensual
          </button>
          <button
            onClick={() => setAnnual(true)}
            style={{ fontFamily: 'var(--font-body)', fontWeight: annual ? 600 : 400, fontSize: 14, color: annual ? 'var(--ink)' : 'var(--muted)', background: annual ? '#fff' : 'none', border: 'none', borderRadius: 99, padding: '5px 14px', cursor: 'pointer', boxShadow: annual ? '0 1px 4px rgba(0,0,0,.09)' : 'none', transition: 'all .18s', display: 'flex', alignItems: 'center', gap: 8 }}
          >
            Anual
            <span style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 11, background: 'var(--whatsapp-dark)', color: '#fff', borderRadius: 99, padding: '2px 8px' }}>-20 %</span>
          </button>
        </div>
      </Reveal>

      {/* Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, alignItems: 'start' }}>
        {PLANS.map((plan, i) => (
          <Reveal key={plan.id} delay={i * 80}>
            <div style={{
              background: '#fff',
              border: plan.highlighted ? '2px solid var(--primary)' : '1px solid var(--hairline)',
              borderRadius: 'var(--radius-xl)',
              padding: '32px 28px',
              position: 'relative',
              boxShadow: plan.highlighted ? '0 8px 32px rgba(22,74,113,.14)' : 'none',
            }}>
              {plan.tag && (
                <div style={{ position: 'absolute', top: -13, left: '50%', transform: 'translateX(-50%)', background: 'var(--primary)', color: '#fff', fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 12, borderRadius: 99, padding: '4px 14px', whiteSpace: 'nowrap' }}>
                  {plan.tag}
                </div>
              )}

              <div style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--primary)', marginBottom: 10 }}>{plan.name}</div>

              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, marginBottom: 4 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 38, letterSpacing: '-1.5px', color: 'var(--ink)', lineHeight: 1 }}>
                  {formatARS(annual ? plan.annual : plan.monthly)}
                </span>
                <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--muted)', marginBottom: 5 }}>/ mes</span>
              </div>

              {annual && (
                <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--muted-soft)', marginBottom: 4 }}>
                  {formatARS(plan.annualTotal)} facturado anualmente
                </div>
              )}

              <p style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--muted)', margin: '10px 0 24px', lineHeight: 1.45 }}>{plan.desc}</p>

              <LandingButton
                variant={plan.highlighted ? 'primary' : 'secondary'}
                full
                href={plan.id === 'equipo' ? '#contacto' : '/signup'}
              >
                {plan.cta}
              </LandingButton>

              <ul style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 11 }}>
                {plan.features.map((f) => (
                  <li key={f} style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
                    <span style={{ marginTop: 1, flexShrink: 0 }}>
                      <Icon name="check" size={16} color="var(--primary)" />
                    </span>
                    <span style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--body)', lineHeight: 1.4 }}>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        ))}
      </div>

      {/* Comparison Matrix */}
      <Reveal style={{ marginTop: 48 }}>
        <div style={{ border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
          <button
            onClick={() => setMatrixOpen(v => !v)}
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 28px', cursor: 'pointer', background: 'var(--surface-soft)', border: 'none', textAlign: 'left' }}
          >
            <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 15, color: 'var(--ink)' }}>Comparar planes en detalle</span>
            <Icon name="chevron-down" size={20} color="var(--muted-soft)" style={{ transition: 'transform .2s', transform: matrixOpen ? 'rotate(180deg)' : 'none' }} />
          </button>

          {matrixOpen && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--hairline)' }}>
                    <th style={{ padding: '14px 28px', textAlign: 'left', fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13, color: 'var(--muted)', background: '#fff' }}>Característica</th>
                    {PLANS.map(p => (
                      <th key={p.id} style={{ padding: '14px 20px', textAlign: 'center', fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 13, color: p.highlighted ? 'var(--primary)' : 'var(--ink)', background: p.highlighted ? 'var(--brand-tint)' : '#fff' }}>{p.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {MATRIX.map((row, i) => (
                    <tr key={row.label} style={{ borderBottom: '1px solid var(--hairline-soft)', background: i % 2 === 0 ? '#fff' : 'var(--surface-soft)' }}>
                      <td style={{ padding: '12px 28px', fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--body)' }}>{row.label}</td>
                      <td style={{ padding: '12px 20px', textAlign: 'center' }}><Check ok={row.starter} /></td>
                      <td style={{ padding: '12px 20px', textAlign: 'center', background: 'rgba(22,74,113,.03)' }}><Check ok={row.pro} /></td>
                      <td style={{ padding: '12px 20px', textAlign: 'center' }}><Check ok={row.equipo} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Reveal>

      <Reveal style={{ textAlign: 'center', marginTop: 20 }}>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--muted-soft)' }}>
          Precios en ARS indexados al dólar · Revisados cada trimestre · Pagás con Mercado Pago o transferencia
        </p>
      </Reveal>
    </section>
  )
}

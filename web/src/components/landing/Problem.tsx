'use client'

import { useState } from 'react'
import { Icon, Reveal } from './atoms'

const VIVIENDAPP_ARS = 66000

const REASONS = [
  { t: 'Solo 1 de cada 10 es un cliente real',   d: 'Pero igual abrís el WhatsApp, buscás fotos, armás el mensaje y lo mandás. Para cada uno. Todo el día. ViviendApp hace eso solo.' },
  { t: 'Oportunidades perdidas',                  d: 'Si tardás más de 5 minutos en responder, el cliente se va a la competencia. Y si escribe a las 11 de la noche o el domingo, directamente no hay respuesta. ViviendApp atiende las 24 hs, lo unico que tenés que hacer es cargar tus propiedades en el panel y listo.' },
  { t: 'Caos administrativo',                     d: 'Notitas en la pared, paneles desactualizados y visitas perdidas. El seguimiento manual es insostenible.' },
  { t: 'Interrupciones constantes',               d: 'Cada WhatsApp te corta el ritmo de trabajo. Tardás 15 minutos en recuperar la concentración.' },
]

interface SliderProps {
  icon: string
  label: string
  value: number
  display: string
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}

function CostSlider({ icon, label, value, display, min, max, step, onChange }: SliderProps) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <Icon name={icon} size={18} color="var(--primary)" />
        <span style={{ fontFamily: 'var(--font-body)', fontWeight: 500, fontSize: 14.5, color: 'var(--body)' }}>{label}</span>
        <span style={{
          marginLeft: 'auto', fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13,
          color: 'var(--ink)', background: 'var(--surface-card)', border: '1px solid var(--hairline)',
          borderRadius: 'var(--radius-sm)', padding: '4px 11px', minWidth: 64, textAlign: 'center',
        }}>
          {display}
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--primary)', cursor: 'pointer', height: 4 }} />
    </div>
  )
}

export default function Problem() {
  const [clientes,  setClientes]  = useState(30)
  const [minutos,   setMinutos]   = useState(15)
  const [costoHora, setCostoHora] = useState(4000)

  const horas       = (clientes * 30 * minutos) / 60
  const gastoManual = horas * costoHora
  const empleados   = horas / 160
  const ahorro      = Math.max(0, gastoManual - VIVIENDAPP_ARS)
  const pct         = gastoManual > 0 ? Math.round((ahorro / gastoManual) * 100) : 0

  const pesos = (n: number) => '$' + Math.round(n).toLocaleString('es-AR')
  const num   = (n: number, d = 0) => n.toLocaleString('es-AR', { minimumFractionDigits: d, maximumFractionDigits: d })

  return (
    <section style={{ maxWidth: 1200, margin: '0 auto', padding: '88px 28px 0' }}>
      <div className="problem-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1.05fr', gap: 56, alignItems: 'center' }}>

        <Reveal>
          <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--error)', background: 'var(--error-bg)', padding: '5px 11px', borderRadius: 'var(--radius-pill)' }}>
            El problema
          </span>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 38, lineHeight: 1.08, letterSpacing: '-1.3px', color: 'var(--ink)', margin: '18px 0 0' }}>
            El costo invisible de la gestión manual
          </h2>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 17, lineHeight: 1.6, color: 'var(--muted)', margin: '16px 0 0', maxWidth: 480 }}>
            Tu tiempo es para cerrar ventas, no para hacer de call center. Cada minuto perdido filtrando curiosos es plata que dejás sobre la mesa.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 22, margin: '32px 0 0' }}>
            {REASONS.map((r, i) => (
              <div key={r.t} style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                <span style={{ flex: 'none', width: 30, height: 30, borderRadius: '50%', background: 'var(--error-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--error)', marginTop: 1 }}>
                  {i + 1}
                </span>
                <div>
                  <h3 style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 16, color: 'var(--ink)', margin: 0 }}>{r.t}</h3>
                  <p style={{ fontFamily: 'var(--font-body)', fontSize: 14.5, lineHeight: 1.55, color: 'var(--muted)', margin: '4px 0 0' }}>{r.d}</p>
                </div>
              </div>
            ))}
          </div>
          <p style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: 14, color: 'var(--muted-soft)', margin: '30px 0 0' }}>
            Movés los deslizadores para ver cuánta plata estás perdiendo hoy.
          </p>
        </Reveal>

        <Reveal delay={120}>
          <div style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-md)', overflow: 'hidden' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24, padding: '30px 30px 26px' }}>
              <CostSlider icon="users"       label="Consultas por día"         value={clientes}  display={num(clientes)}           min={5}    max={200}   step={5}   onChange={setClientes} />
              <CostSlider icon="clock"       label="Minutos por cliente"       value={minutos}   display={`${minutos} min`}         min={5}    max={60}    step={5}   onChange={setMinutos} />
              <CostSlider icon="dollar-sign" label="Costo por hora (personal)" value={costoHora} display={`${pesos(costoHora)}/h`} min={2000} max={12000} step={500} onChange={setCostoHora} />
            </div>

            <div style={{ background: 'var(--surface-soft)', borderTop: '1px solid var(--hairline-soft)', padding: '26px 30px 30px' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: 13.5, color: 'var(--muted)' }}>Gastás hoy en gestión manual</div>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 6, margin: '6px 0 4px' }}>
                  <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 42, letterSpacing: '-1.5px', color: 'var(--ink)' }}>{pesos(gastoManual)}</span>
                  <span style={{ fontFamily: 'var(--font-body)', fontSize: 15, color: 'var(--muted-soft)' }}>/mes</span>
                </div>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: 12.5, color: 'var(--muted-soft)' }}>
                  {num(horas)} horas/mes = {num(empleados, 1)} empleados a jornada completa
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 14, margin: '22px 0' }}>
                <span style={{ flex: 1, height: 1, background: 'var(--hairline)' }} />
                <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--muted-soft)' }}>vs</span>
                <span style={{ flex: 1, height: 1, background: 'var(--hairline)' }} />
              </div>

              <div style={{ textAlign: 'center' }}>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: 13.5, color: 'var(--muted)' }}>Con ViviendApp</div>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 6, marginTop: 4 }}>
                  <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 42, letterSpacing: '-1.5px', color: 'var(--primary)' }}>{pesos(VIVIENDAPP_ARS)}</span>
                  <span style={{ fontFamily: 'var(--font-body)', fontSize: 15, color: 'var(--muted-soft)' }}>/mes</span>
                </div>
              </div>

              <div style={{ background: 'var(--success-bg)', border: '1px solid rgba(47,143,78,.22)', borderRadius: 'var(--radius-lg)', padding: '18px 20px', margin: '22px 0 0', textAlign: 'center' }}>
                <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 13, color: 'var(--success)' }}>Ahorro mensual</div>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 34, letterSpacing: '-1.2px', color: 'var(--success)', margin: '2px 0' }}>{pesos(ahorro)}</div>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: 12.5, color: 'var(--success)' }}>{pct}% menos que la gestión manual</div>
              </div>

              <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, lineHeight: 1.5, color: 'var(--muted)', margin: '22px 0 0', textAlign: 'center' }}>
                <strong style={{ color: 'var(--ink)' }}>{num(horas)} horas recuperadas</strong> cada mes para hacer visitas, captar exclusivas y cerrar operaciones.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}

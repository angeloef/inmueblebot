'use client'

import { useState } from 'react'
import { Icon, Reveal } from './atoms'

const QS = [
  { q: '¿Necesito instalar algo?',               a: 'No. ViviendApp se conecta a tu número de WhatsApp Business y tu cliente sigue usando la app que ya tiene. Vos manejás todo desde el panel web.' },
  { q: '¿El bot inventa propiedades?',            a: 'Nunca. Solo responde con propiedades reales de tu cartera. Si no encuentra algo que encaje, lo dice y propone alternativas parecidas.' },
  { q: '¿Cómo es la prueba gratis?',              a: '30 días con el plan completo, sin tarjeta de crédito, con onboarding guiado. Probás los resultados antes de pagar nada.' },
  { q: '¿Se integra con Google Calendar?',        a: 'Sí, en todos los planes. Las visitas se crean, reprograman y cancelan solas en tu calendario, con recordatorios automáticos.' },
  { q: '¿Puedo intervenir en una conversación?',  a: 'Siempre. El bot deriva a un agente humano cuando el cliente lo pide o cuando la consulta se sale de su alcance. El control es tuyo.' },
  { q: '¿En qué moneda pago?',                    a: 'Facturamos en pesos indexados al dólar, revisados cada trimestre. Pagás con Mercado Pago (débito, crédito o transferencia) o transferencia en USD.' },
]

export default function FAQ() {
  const [open, setOpen] = useState(0)

  return (
    <section style={{ maxWidth: 820, margin: '0 auto', padding: '92px 28px 0' }}>
      <Reveal style={{ textAlign: 'center', marginBottom: 40 }}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 36, letterSpacing: '-1.2px', color: 'var(--ink)', margin: 0 }}>
          Preguntas frecuentes
        </h2>
      </Reveal>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {QS.map((item, i) => {
          const isOpen = open === i
          return (
            <Reveal key={i} delay={i * 50}>
              <div style={{ border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', background: '#fff', overflow: 'hidden' }}>
                <button
                  onClick={() => setOpen(isOpen ? -1 : i)}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '18px 22px', cursor: 'pointer', background: 'none', border: 'none', textAlign: 'left' }}
                >
                  <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 16, color: 'var(--ink)' }}>{item.q}</span>
                  <Icon name="chevron-down" size={20} color="var(--muted-soft)" style={{ flex: 'none', transition: 'transform .2s', transform: isOpen ? 'rotate(180deg)' : 'none' }} />
                </button>
                {isOpen && (
                  <p style={{ fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.6, color: 'var(--muted)', margin: 0, padding: '0 22px 20px' }}>
                    {item.a}
                  </p>
                )}
              </div>
            </Reveal>
          )
        })}
      </div>
    </section>
  )
}

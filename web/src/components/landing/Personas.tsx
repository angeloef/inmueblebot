import { Icon, Reveal } from './atoms'

const PERSONAS = [
  { icon: 'user-round', tag: 'Agente independiente', t: '"USD 55 al mes para que ningún cliente se enfríe a las 11 de la noche."',             d: 'Trabajás solo o con un asistente, con 10 a 25 propiedades. Automatizás WhatsApp sin perder el trato personal.' },
  { icon: 'building-2', tag: 'Dueño de inmobiliaria', t: '"Cliente nuevo a las 9. Visita confirmada a las 10. Resumen el lunes a la mañana."',  d: 'Coordinás 2 a 5 agentes y querés ver todo el negocio desde el celular. Visibilidad y orden, sin planillas.' },
  { icon: 'line-chart',  tag: 'Desarrolladora',        t: '"Data de mercado que ninguna inmobiliaria del NEA tiene todavía."',                  d: 'Manejás carteras grandes y decidís con datos. Sabés qué se busca, dónde y a qué precio.' },
]

export default function Personas() {
  return (
    <section style={{ maxWidth: 1200, margin: '0 auto', padding: '96px 28px 0' }}>
      <Reveal style={{ textAlign: 'center', maxWidth: 620, margin: '0 auto 44px' }}>
        <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--primary)' }}>Para quién es</span>
        <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 38, letterSpacing: '-1.3px', color: 'var(--ink)', margin: '12px 0 0' }}>
          Sea cual sea tu tamaño.
        </h2>
      </Reveal>

      <div className="persona-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 22 }}>
        {PERSONAS.map((it, i) => (
          <Reveal key={it.tag} delay={i * 90}>
            <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 30, height: '100%' }}>
              <span style={{ width: 46, height: 46, borderRadius: 12, background: 'var(--brand-tint)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--primary)' }}>
                <Icon name={it.icon} size={22} />
              </span>
              <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12.5, letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--muted-soft)', margin: '18px 0 10px' }}>{it.tag}</div>
              <p style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 19, lineHeight: 1.3, letterSpacing: '-.4px', color: 'var(--ink)', margin: 0 }}>{it.t}</p>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 14, lineHeight: 1.55, color: 'var(--muted)', margin: '12px 0 0' }}>{it.d}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}

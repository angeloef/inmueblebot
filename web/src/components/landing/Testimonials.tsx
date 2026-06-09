import { Icon, Avatar, Reveal } from './atoms'

const TESTIMONIALS = [
  { q: 'Pasamos de responder en horas a responder en segundos. El primer mes cerramos un 30% más de visitas.',               n: 'Jorge López',  r: 'Inmobiliaria Norte · Posadas',  bg: 'var(--brand-tint-strong)', fg: 'var(--primary)' },
  { q: 'El equipo dejó de cargar clientes a mano. El CRM está siempre al día solo, y la data ya no se va con el agente.',   n: 'Carla Méndez', r: 'Méndez Propiedades · Oberá',    bg: '#f0ebf7',                  fg: '#6b4d99'         },
  { q: 'Las visitas se agendan de noche y los findes. En Eldorado no perdemos ni un interesado.',                            n: 'Andrés Vidal', r: 'Vidal & Asociados · Eldorado',  bg: '#eaf3f5',                  fg: '#2e7686'         },
]

export default function Testimonials() {
  return (
    <section id="clientes" style={{ background: 'var(--surface-soft)', borderTop: '1px solid var(--hairline-soft)', marginTop: 96 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '84px 28px' }}>
        <Reveal style={{ textAlign: 'center', marginBottom: 44 }}>
          <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--primary)' }}>Clientes</span>
          <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 36, letterSpacing: '-1.2px', color: 'var(--ink)', margin: '12px 0 0' }}>
            Inmobiliarias de Misiones que ya no pierden leads.
          </h2>
        </Reveal>

        <div className="testi-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 22 }}>
          {TESTIMONIALS.map((it, i) => (
            <Reveal key={i} delay={i * 90}>
              <div style={{ background: '#fff', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 28, height: '100%' }}>
                <div style={{ display: 'flex', gap: 3, marginBottom: 14 }}>
                  {Array.from({ length: 5 }).map((_, k) => (
                    <Icon key={k} name="star" size={15} color="#f0a92b" fill="#f0a92b" stroke={0} />
                  ))}
                </div>
                <p style={{ fontFamily: 'var(--font-body)', fontSize: 15.5, lineHeight: 1.55, color: 'var(--body)', margin: '0 0 22px' }}>
                  &ldquo;{it.q}&rdquo;
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                  <Avatar initials={it.n.split(' ').map(x => x[0]).join('')} size={40} bg={it.bg} fg={it.fg} />
                  <div>
                    <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 14, color: 'var(--ink)' }}>{it.n}</div>
                    <div style={{ fontFamily: 'var(--font-body)', fontSize: 12.5, color: 'var(--muted-soft)' }}>{it.r}</div>
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

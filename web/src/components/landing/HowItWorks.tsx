import { Icon, Reveal } from './atoms'

const STEPS = [
  { n: '01', icon: 'message-circle', t: 'El cliente escribe a tu WhatsApp',    d: 'Pregunta por una propiedad, un precio o un horario — en lenguaje natural, como le habla a una persona.' },
  { n: '02', icon: 'sparkles',       t: 'ViviendApp entiende y responde',       d: 'Busca en tu cartera, muestra fotos y datos, contesta las FAQ y recuerda lo que ese cliente ya buscó antes.' },
  { n: '03', icon: 'calendar-check', t: 'Agenda la visita y avisa al agente',   d: 'Ofrece horarios libres, confirma con el cliente y crea el evento en Google Calendar. Vos recibís la notificación.' },
  { n: '04', icon: 'trending-up',    t: 'Todo queda cargado en el panel',       d: 'Cada conversación se vuelve un cliente con su score, su historial y la propiedad de interés. Sin cargar nada a mano.' },
]

export default function HowItWorks() {
  return (
    <section id="como-funciona" style={{ maxWidth: 1200, margin: '0 auto', padding: '92px 28px 0' }}>
      <Reveal style={{ textAlign: 'center', maxWidth: 660, margin: '0 auto 52px' }}>
        <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--primary)' }}>Cómo funciona</span>
        <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 40, letterSpacing: '-1.3px', color: 'var(--ink)', margin: '12px 0 0' }}>
          Del primer &ldquo;hola&rdquo; a la visita agendada, solo.
        </h2>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 17, color: 'var(--muted)', margin: '14px 0 0' }}>
          ViviendApp automatiza la primera etapa del embudo. Vos entrás cuando hay que cerrar.
        </p>
      </Reveal>

      <div className="steps-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 20 }}>
        {STEPS.map((s, i) => (
          <Reveal key={s.n} delay={i * 90}>
            <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: 26, height: '100%', boxShadow: 'var(--shadow-sm)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ width: 46, height: 46, borderRadius: 12, background: 'var(--brand-tint)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--primary)' }}>
                  <Icon name={s.icon} size={22} />
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500, color: 'var(--surface-strong)' }}>{s.n}</span>
              </div>
              <h3 style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 17, lineHeight: 1.3, color: 'var(--ink)', margin: '18px 0 8px' }}>{s.t}</h3>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 14, lineHeight: 1.55, color: 'var(--muted)', margin: 0 }}>{s.d}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}

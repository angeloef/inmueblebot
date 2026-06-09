import { LandingButton, Reveal } from './atoms'

export default function CTABand() {
  return (
    <section id="contacto" style={{ maxWidth: 1200, margin: '0 auto', padding: '92px 28px' }}>
      <Reveal>
        <div style={{ background: 'var(--surface-dark)', borderRadius: 'var(--radius-xl)', padding: '64px 32px', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(rgba(255,255,255,.04) 1px, transparent 1px)', backgroundSize: '22px 22px' }} />
          <div style={{ position: 'relative' }}>
            <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 38, letterSpacing: '-1.3px', color: '#fff', margin: 0 }}>
              Probá ViviendApp con tu propio WhatsApp.
            </h2>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 17, color: 'var(--on-dark-soft)', margin: '16px auto 30px', maxWidth: 480 }}>
              30 días gratis, con el plan completo y onboarding guiado. Sin tarjeta. Lo conectás en minutos.
            </p>
            <div className="cta-row" style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
              <LandingButton size="lg" variant="whatsapp" icon="message-circle" href="/signup">Empezar gratis</LandingButton>
              <LandingButton size="lg" variant="secondary" href="#contacto">Agendar una demo</LandingButton>
            </div>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

import { Reveal } from './atoms'

const STATS = [
  { k: '< 2 seg', v: 'en responder cada mensaje' },
  { k: '24 / 7',  v: 'incluso noches y fines de semana' },
  { k: '98 %',    v: 'tasa de apertura en WhatsApp' },
  { k: '0',       v: 'clientes perdidos por no contestar' },
]

export default function StatBand() {
  return (
    <section style={{ borderTop: '1px solid var(--hairline-soft)', borderBottom: '1px solid var(--hairline-soft)', background: 'var(--surface-soft)' }}>
      <div className="stat-grid" style={{ maxWidth: 1100, margin: '0 auto', padding: '36px 28px', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 24 }}>
        {STATS.map((s, i) => (
          <Reveal key={s.k} delay={i * 80} style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 34, letterSpacing: '-1px', color: 'var(--primary)' }}>{s.k}</div>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 13.5, color: 'var(--muted)', marginTop: 4 }}>{s.v}</div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}

import { Icon, Wordmark } from './atoms'

const LINKS: Record<string, { label: string; href: string }[]> = {
  Producto: [
    { label: 'Funcionalidades',  href: '#funcionalidades' },
    { label: '¿Cómo funciona?', href: '#como-funciona' },
    { label: 'Precios',          href: '#precios' },
    { label: 'Clientes',         href: '#clientes' },
  ],
  Empresa: [
    { label: 'Sobre nosotros',   href: '#' },
    { label: 'Blog',             href: '#' },
    { label: 'Contacto',         href: '#contacto' },
    { label: 'Ingresar',         href: '/login' },
  ],
  Legal: [
    { label: 'Privacidad',       href: '#' },
    { label: 'Términos',         href: '#' },
  ],
}

const SOCIALS = [
  { icon: 'instagram', href: '#', label: 'Instagram' },
  { icon: 'linkedin',  href: '#', label: 'LinkedIn' },
  { icon: 'twitter',   href: '#', label: 'Twitter / X' },
]

export default function Footer() {
  return (
    <footer style={{ background: 'var(--surface-dark)', borderTop: '1px solid rgba(255,255,255,.07)', marginTop: 96 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '64px 28px 40px' }}>
        {/* Top grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 40, marginBottom: 56 }}>
          {/* Brand */}
          <div>
            <Wordmark height={28} dark />
            <p style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--on-dark-soft)', lineHeight: 1.6, margin: '14px 0 24px', maxWidth: 260 }}>
              IA + WhatsApp para inmobiliarias argentinas. Respondé leads, agendá visitas y cerrá más propiedades — 24/7.
            </p>
            <div style={{ display: 'flex', gap: 10 }}>
              {SOCIALS.map(s => (
                <a
                  key={s.icon}
                  href={s.href}
                  aria-label={s.label}
                  style={{ width: 36, height: 36, borderRadius: 10, border: '1px solid rgba(255,255,255,.12)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--on-dark-soft)', transition: 'border-color .15s, color .15s', textDecoration: 'none' }}
                >
                  <Icon name={s.icon} size={16} />
                </a>
              ))}
            </div>
          </div>

          {/* Link columns */}
          {Object.entries(LINKS).map(([title, links]) => (
            <div key={title}>
              <div style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 12, letterSpacing: '.07em', textTransform: 'uppercase', color: 'rgba(255,255,255,.4)', marginBottom: 16 }}>
                {title}
              </div>
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {links.map(l => (
                  <li key={l.label}>
                    <a
                      href={l.href}
                      style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--on-dark-soft)', textDecoration: 'none', transition: 'color .15s' }}
                    >
                      {l.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div style={{ borderTop: '1px solid rgba(255,255,255,.07)', paddingTop: 24, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <p style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'rgba(255,255,255,.3)', margin: 0 }}>
            © 2025 ViviendApp. Todos los derechos reservados.
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'rgba(255,255,255,.3)' }}>Construido con</span>
            <Icon name="heart" size={13} color="#e25" fill="#e25" stroke={0} />
            <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'rgba(255,255,255,.3)' }}>en Misiones, Argentina</span>
          </div>
        </div>
      </div>
    </footer>
  )
}

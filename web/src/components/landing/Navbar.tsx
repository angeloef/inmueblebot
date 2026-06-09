'use client'

import { useState, useEffect } from 'react'
import { Wordmark, LandingButton } from './atoms'

const NAV_LINKS = [
  { l: 'Cómo funciona', h: '#como-funciona' },
  { l: 'Funciones',     h: '#funciones'     },
  { l: 'Precios',       h: '#precios'       },
  { l: 'Clientes',      h: '#clientes'      },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 30, height: 66,
      background: 'rgba(255,255,255,.82)',
      backdropFilter: 'saturate(180%) blur(12px)',
      borderBottom: `1px solid ${scrolled ? 'var(--hairline)' : 'transparent'}`,
      transition: 'border-color .2s',
    }}>
      <div style={{
        maxWidth: 1200, margin: '0 auto', height: '100%',
        padding: '0 28px', display: 'flex', alignItems: 'center', gap: 32,
      }}>
        <a href="#top" style={{ textDecoration: 'none' }}>
          <Wordmark height={28} />
        </a>

        <nav className="nav-desktop" style={{ display: 'flex', gap: 26, marginLeft: 14 }}>
          {NAV_LINKS.map(l => (
            <a key={l.l} href={l.h} style={{
              fontFamily: 'var(--font-body)', fontWeight: 500, fontSize: 14,
              color: 'var(--muted)', textDecoration: 'none',
            }}>
              {l.l}
            </a>
          ))}
        </nav>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 14 }}>
          <a href="/login" className="nav-desktop" style={{
            fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 14,
            color: 'var(--ink)', textDecoration: 'none',
          }}>
            Iniciar sesión
          </a>
          <LandingButton size="sm" href="/signup">Probar 30 días gratis</LandingButton>
        </div>
      </div>
    </header>
  )
}

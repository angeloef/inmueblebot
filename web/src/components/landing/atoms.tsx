'use client'

import { useEffect, useRef, useState } from 'react'
import * as LucideIcons from 'lucide-react'

/* ─── Icon ─────────────────────────────────────────────── */

interface IconProps {
  name: string
  size?: number
  stroke?: number
  color?: string
  fill?: string
  style?: React.CSSProperties
}

type LucideIconComponent = React.ComponentType<{
  size?: number
  strokeWidth?: number
  color?: string
  fill?: string
  style?: React.CSSProperties
}>

function toPascalCase(name: string): string {
  return name.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join('')
}

export function Icon({ name, size = 20, stroke = 2, color, fill, style = {} }: IconProps) {
  const iconName = toPascalCase(name)
  const LucideIcon = (LucideIcons as unknown as Record<string, LucideIconComponent>)[iconName]
  if (!LucideIcon) return null
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color, lineHeight: 0, ...style }}>
      <LucideIcon size={size} strokeWidth={stroke} {...(fill ? { fill } : {})} />
    </span>
  )
}

/* ─── Button ────────────────────────────────────────────── */

interface LandingButtonProps {
  children: React.ReactNode
  variant?: 'primary' | 'secondary' | 'ghost' | 'whatsapp' | 'dark'
  size?: 'sm' | 'md' | 'lg'
  icon?: string
  iconRight?: string
  full?: boolean
  onClick?: () => void
  href?: string
  style?: React.CSSProperties
}

export function LandingButton({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  full,
  onClick,
  href,
  style = {},
}: LandingButtonProps) {
  const base: React.CSSProperties = {
    fontFamily: 'var(--font-body)',
    fontWeight: 600,
    border: 'none',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 'var(--radius-md)',
    transition: 'background .15s, box-shadow .15s, transform .05s',
    width: full ? '100%' : 'auto',
    whiteSpace: 'nowrap',
    textDecoration: 'none',
  }
  const sizes: Record<string, React.CSSProperties> = {
    sm: { height: 36, padding: '0 15px', fontSize: 13 },
    md: { height: 42, padding: '0 20px', fontSize: 14 },
    lg: { height: 50, padding: '0 28px', fontSize: 15 },
  }
  const variants: Record<string, React.CSSProperties> = {
    primary:   { background: 'var(--primary)',       color: '#fff' },
    secondary: { background: '#fff',                 color: 'var(--ink)', border: '1px solid var(--hairline)' },
    ghost:     { background: 'transparent',          color: 'var(--ink)' },
    whatsapp:  { background: 'var(--whatsapp-dark)', color: '#fff' },
    dark:      { background: 'var(--surface-dark)',  color: '#fff' },
  }
  const hoverVariants: Record<string, React.CSSProperties> = {
    primary:   { background: 'var(--primary-hover)',  boxShadow: 'var(--shadow-md)' },
    secondary: { background: 'var(--surface-soft)' },
    ghost:     { background: 'var(--surface-card)' },
    whatsapp:  { background: '#0f7568',               boxShadow: 'var(--shadow-md)' },
    dark:      { background: '#1d2024' },
  }
  const [hover, setHover] = useState(false)
  const hoverStyle = hover ? hoverVariants[variant] : {}
  const iconSize = size === 'lg' ? 19 : 17

  const Tag = href ? 'a' : 'button'
  return (
    <Tag
      onClick={onClick}
      href={href as string}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ ...base, ...sizes[size], ...variants[variant], ...hoverStyle, ...style }}
    >
      {icon && <Icon name={icon} size={iconSize} />}
      {children}
      {iconRight && <Icon name={iconRight} size={iconSize} />}
    </Tag>
  )
}

/* ─── Wordmark ──────────────────────────────────────────── */

interface WordmarkProps {
  height?: number
  color?: string
  dark?: boolean
}

export function Wordmark({ height = 30, color, dark = false }: WordmarkProps) {
  const ink = color || (dark ? '#fff' : 'var(--ink)')
  const accent = dark ? '#9bc2e0' : 'var(--brand-accent)'
  // Icon-only SVG (symbol mark, viewBox 283 212 455 428) — same paths as original HTML
  const fill = dark ? '#ffffff' : '#164a71'
  // aspect ratio 455:428
  const iconW = Math.round(height * (455 / 428))
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9 }}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="283 212 455 428"
        width={iconW}
        height={height}
        aria-hidden="true"
        style={{ display: 'block', flex: 'none' }}
      >
        <g transform="translate(0,1024) scale(0.1,-0.1)" fill={fill}>
          <path d="M5052 8040 c-35 -15 23 26 -1207 -848 -181 -129 -372 -264 -424 -301 -481 -340 -490 -348 -491 -434 0 -109 107 -195 211 -169 24 6 175 107 401 268 200 142 503 357 673 478 171 121 425 301 565 401 140 100 274 194 298 210 l42 28 100 -69 c110 -76 590 -416 910 -644 713 -509 910 -646 951 -663 72 -31 150 -6 202 65 28 38 34 116 11 163 -21 46 -31 53 -447 348 l-336 238 -3 314 -3 315 -28 27 c-27 28 -28 28 -188 31 -172 4 -210 -3 -232 -42 -7 -12 -14 -80 -17 -164 l-5 -143 -340 242 c-492 350 -491 350 -562 355 -32 2 -68 0 -81 -6z" />
          <path d="M4976 6560 c-71 -23 -155 -79 -196 -130 -45 -57 -89 -158 -96 -222 l-7 -58 187 0 186 0 0 215 c0 118 -3 215 -7 214 -5 0 -35 -9 -67 -19z" />
          <path d="M5190 6365 l0 -215 185 0 185 0 0 35 c0 89 -74 234 -152 298 -48 39 -134 81 -185 91 l-33 6 0 -215z" />
          <path d="M3632 6340 c-84 -60 -172 -124 -195 -143 l-42 -35 1 -178 c0 -145 4 -198 22 -281 34 -158 76 -276 152 -428 243 -486 678 -821 1215 -935 144 -31 432 -38 575 -15 199 32 146 46 510 -143 179 -92 368 -191 420 -218 79 -41 103 -49 146 -48 60 0 124 36 147 81 33 66 31 84 -68 478 -52 209 -95 387 -95 397 0 10 35 64 78 121 232 305 352 647 356 1016 l1 144 -45 39 c-46 39 -353 258 -357 254 -1 -1 4 -23 12 -49 8 -27 21 -94 30 -151 59 -403 -63 -812 -336 -1121 -73 -83 -99 -134 -99 -195 1 -25 27 -150 59 -277 32 -128 57 -233 54 -233 -2 0 -131 65 -287 145 -317 162 -303 158 -453 125 -383 -84 -761 -13 -1085 202 -119 79 -293 253 -377 376 -220 325 -296 745 -200 1101 11 40 18 75 17 76 -2 2 -72 -46 -156 -105z" />
          <path d="M4692 6008 c-9 -9 -12 -68 -12 -205 0 -251 -16 -233 205 -233 l165 0 0 225 0 225 -173 0 c-121 0 -177 -4 -185 -12z" />
          <path d="M5190 5795 l0 -225 169 0 c164 0 170 1 185 22 13 18 16 57 16 213 0 135 -4 195 -12 203 -8 8 -64 12 -185 12 l-173 0 0 -225z" />
        </g>
      </svg>
      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: height * 0.72, letterSpacing: '-0.04em' }}>
        <span style={{ color: ink }}>Viviend</span><span style={{ color: accent }}>App</span>
      </span>
    </span>
  )
}

/* ─── Avatar ────────────────────────────────────────────── */

interface AvatarProps {
  initials: string
  size?: number
  bg?: string
  fg?: string
  src?: string
}

export function Avatar({ initials, size = 38, bg = 'var(--brand-tint-strong)', fg = 'var(--primary)', src }: AvatarProps) {
  return (
    <span style={{
      width: size, height: size, borderRadius: '50%',
      background: src ? `url(${src}) center/cover` : bg,
      color: fg, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flex: 'none',
      fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: size * 0.36,
    }}>
      {!src && initials}
    </span>
  )
}

/* ─── Badge ─────────────────────────────────────────────── */

type BadgeTone = 'neutral' | 'blue' | 'teal' | 'violet' | 'emerald' | 'amber' | 'error' | 'brand' | 'whatsapp'

interface BadgeProps {
  children: React.ReactNode
  tone?: BadgeTone
  dot?: boolean
  style?: React.CSSProperties
}

export function Badge({ children, tone = 'neutral', dot = false, style = {} }: BadgeProps) {
  const tones: Record<BadgeTone, [string, string]> = {
    neutral:  ['var(--surface-card)',    'var(--ink)'],
    blue:     ['#eef2fa',                '#3a5fa8'],
    teal:     ['#eaf3f5',                '#2e7686'],
    violet:   ['#f0ebf7',                '#6b4d99'],
    emerald:  ['var(--success-bg)',      'var(--success)'],
    amber:    ['var(--warning-bg)',      'var(--warning)'],
    error:    ['var(--error-bg)',        'var(--error)'],
    brand:    ['var(--brand-tint)',      'var(--primary)'],
    whatsapp: ['var(--whatsapp-bubble)', '#0f7568'],
  }
  const [bg, fg] = tones[tone]
  return (
    <span style={{
      background: bg, color: fg, fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12,
      padding: '5px 11px', borderRadius: 'var(--radius-pill)',
      display: 'inline-flex', alignItems: 'center', gap: 6, lineHeight: 1, ...style,
    }}>
      {dot && <span style={{ width: 7, height: 7, borderRadius: '50%', background: fg, flex: 'none' }} />}
      {children}
    </span>
  )
}

/* ─── Reveal (scroll-based fade-in) ────────────────────── */

interface RevealProps {
  children: React.ReactNode
  delay?: number
  style?: React.CSSProperties
}

export function Reveal({ children, delay = 0, style = {} }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      entries => { entries.forEach(e => { if (e.isIntersecting) { setShown(true); io.disconnect() } }) },
      { threshold: 0.14 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      style={{
        transition: 'opacity .6s ease, transform .6s ease',
        transitionDelay: `${delay}ms`,
        opacity: shown ? 1 : 0,
        transform: shown ? 'none' : 'translateY(20px)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

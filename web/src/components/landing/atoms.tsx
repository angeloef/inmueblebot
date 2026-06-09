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
  // SVG viewBox: 143 188 735 660 → aspect ratio 735:660
  const w = Math.round(height * (735 / 660))
  const fill = color || (dark ? '#ffffff' : '#164a71')
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="143 188 735 660"
      width={w}
      height={height}
      aria-label="ViviendApp"
      role="img"
      style={{ display: 'block', flex: 'none' }}
    >
      <g transform="translate(0,1024) scale(0.1,-0.1)" fill={fill}>
        <path d="M5052 8040 c-35 -15 23 26 -1207 -848 -181 -129 -372 -264 -424 -301 -481 -340 -490 -348 -491 -434 0 -109 107 -195 211 -169 24 6 175 107 401 268 200 142 503 357 673 478 171 121 425 301 565 401 140 100 274 194 298 210 l42 28 100 -69 c110 -76 590 -416 910 -644 713 -509 910 -646 951 -663 72 -31 150 -6 202 65 28 38 34 116 11 163 -21 46 -31 53 -447 348 l-336 238 -3 314 -3 315 -28 27 c-27 28 -28 28 -188 31 -172 4 -210 -3 -232 -42 -7 -12 -14 -80 -17 -164 l-5 -143 -340 242 c-492 350 -491 350 -562 355 -32 2 -68 0 -81 -6z" />
        <path d="M4976 6560 c-71 -23 -155 -79 -196 -130 -45 -57 -89 -158 -96 -222 l-7 -58 187 0 186 0 0 215 c0 118 -3 215 -7 214 -5 0 -35 -9 -67 -19z" />
        <path d="M5190 6365 l0 -215 185 0 185 0 0 35 c0 89 -74 234 -152 298 -48 39 -134 81 -185 91 l-33 6 0 -215z" />
        <path d="M3632 6340 c-84 -60 -172 -124 -195 -143 l-42 -35 1 -178 c0 -145 4 -198 22 -281 34 -158 76 -276 152 -428 243 -486 678 -821 1215 -935 144 -31 432 -38 575 -15 199 32 146 46 510 -143 179 -92 368 -191 420 -218 79 -41 103 -49 146 -48 60 0 124 36 147 81 33 66 31 84 -68 478 -52 209 -95 387 -95 397 0 10 35 64 78 121 232 305 352 647 356 1016 l1 144 -45 39 c-46 39 -353 258 -357 254 -1 -1 4 -23 12 -49 8 -27 21 -94 30 -151 59 -403 -63 -812 -336 -1121 -73 -83 -99 -134 -99 -195 1 -25 27 -150 59 -277 32 -128 57 -233 54 -233 -2 0 -131 65 -287 145 -317 162 -303 158 -453 125 -383 -84 -761 -13 -1085 202 -119 79 -293 253 -377 376 -220 325 -296 745 -200 1101 11 40 18 75 17 76 -2 2 -72 -46 -156 -105z" />
        <path d="M4692 6008 c-9 -9 -12 -68 -12 -205 0 -251 -16 -233 205 -233 l165 0 0 225 0 225 -173 0 c-121 0 -177 -4 -185 -12z" />
        <path d="M5190 5795 l0 -225 169 0 c164 0 170 1 185 22 13 18 16 57 16 213 0 135 -4 195 -12 203 -8 8 -64 12 -185 12 l-173 0 0 -225z" />
        <path d="M1630 2765 l0 -555 128 0 127 0 1 555 1 555 -129 0 -128 0 0 -555z" />
        <path d="M6000 2765 l0 -556 353 3 c400 4 409 6 496 84 62 56 83 106 83 204 1 126 -57 222 -163 269 l-38 18 43 30 c63 45 98 109 104 192 9 132 -54 234 -176 283 -55 22 -70 23 -379 26 l-323 3 0 -556z m660 420 c153 -84 123 -297 -49 -345 -20 -5 -138 -10 -263 -10 l-228 0 0 196 0 195 243 -3 242 -3 55 -30z m21 -483 c89 -35 129 -95 129 -192 0 -64 -18 -109 -59 -143 -59 -49 -110 -57 -383 -57 l-248 0 0 211 0 211 253 -4 c230 -4 257 -6 308 -26z" />
        <path d="M8190 3145 l0 -95 -75 0 -75 0 0 -50 0 -49 73 -3 72 -3 5 -300 5 -300 27 -47 c39 -66 111 -100 210 -101 71 0 155 25 172 51 3 5 -2 28 -12 49 l-17 39 -40 -18 c-49 -22 -126 -23 -165 -3 -62 32 -65 51 -65 355 l0 275 128 3 127 3 0 49 0 50 -130 0 -130 0 0 95 0 95 -55 0 -55 0 0 -95z" />
        <path d="M2580 3074 c-61 -12 -124 -39 -166 -70 l-44 -34 0 45 0 45 -97 1 c-54 0 -108 2 -120 5 l-23 4 0 -430 0 -430 125 0 124 0 -3 198 c-6 311 12 385 106 433 56 28 159 24 204 -9 64 -45 69 -68 72 -359 l3 -263 126 0 125 0 -5 293 c-5 320 -10 352 -67 439 -33 49 -89 91 -151 113 -42 15 -169 26 -209 19z" />
        <path d="M3655 3070 c-61 -13 -95 -28 -147 -66 l-48 -34 0 49 0 49 -115 1 -115 1 0 -430 0 -430 119 0 119 0 4 253 c3 241 4 254 26 300 32 63 88 97 163 97 68 0 110 -25 141 -82 22 -41 23 -53 25 -308 2 -146 5 -264 8 -262 3 1 56 2 119 2 l114 0 4 253 c3 241 4 254 26 300 63 126 246 133 307 12 18 -36 20 -64 23 -305 l4 -265 121 0 121 0 -3 299 c-3 319 -7 348 -55 431 -98 166 -393 191 -559 46 l-37 -33 -50 45 c-28 25 -71 52 -97 61 -58 20 -165 28 -218 16z" />
        <path d="M5194 3066 c-144 -33 -259 -121 -317 -243 -31 -65 -32 -73 -32 -189 0 -119 0 -121 38 -196 83 -169 250 -257 462 -245 192 11 342 113 407 277 29 74 32 240 5 318 -40 114 -143 214 -270 261 -76 28 -211 36 -293 17z m187 -207 c86 -29 137 -100 146 -201 10 -107 -34 -196 -120 -239 -61 -32 -170 -24 -221 14 -64 49 -90 100 -94 183 -5 86 9 133 51 181 57 65 154 90 238 62z" />
        <path d="M7413 3045 c-128 -28 -227 -109 -286 -233 -30 -64 -32 -73 -32 -187 0 -113 2 -124 31 -185 36 -76 79 -129 140 -171 166 -114 419 -93 557 47 202 205 145 577 -106 695 -105 49 -191 58 -304 34z m255 -130 c60 -32 102 -80 134 -152 34 -73 32 -207 -4 -285 -56 -121 -162 -183 -298 -176 -129 7 -226 78 -271 197 -17 46 -20 72 -17 146 5 109 33 171 103 233 65 57 112 72 215 69 72 -3 93 -7 138 -32z" />
      </g>
    </svg>
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

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
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 9 }}>
      <span style={{
        width: height, height, borderRadius: Math.round(height * 0.28),
        background: dark ? 'rgba(255,255,255,.12)' : 'var(--brand-tint)',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flex: 'none',
      }}>
        <Icon name="home" size={Math.round(height * 0.55)} color={dark ? '#9bc2e0' : 'var(--primary)'} />
      </span>
      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: height * 0.72, letterSpacing: '-0.04em' }}>
        <span style={{ color: ink }}>Viviend</span>
        <span style={{ color: accent }}>App</span>
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

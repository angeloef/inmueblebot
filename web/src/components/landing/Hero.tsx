'use client'

import { useState, useEffect, useRef } from 'react'
import { Icon, LandingButton, Badge } from './atoms'

interface ChatMessage {
  side?: 'in' | 'out'
  t?: string
  typing?: number
  d: number
  card?: boolean
  divider?: string
}

type Scene = ChatMessage[]

const SCENES: Scene[] = [
  [
    { side: 'in',  t: 'Hola! Busco una casa en Oberá, hasta USD 80.000, 2 o 3 dormitorios', d: 700 },
    { side: 'out', typing: 900, t: 'Hola 🙌 Tengo 3 opciones que encajan. Te paso la mejor:', d: 600 },
    { side: 'out', card: true, d: 1100 },
    { side: 'in',  t: '¡Me gusta! ¿Puedo verla el sábado a la mañana?', d: 800 },
    { side: 'out', typing: 850, t: 'Sí, tengo el sábado 10:00 hs libre. ¿Te la reservo? 🗓️', d: 700 },
    { side: 'in',  t: 'Dale, perfecto', d: 700 },
    { side: 'out', typing: 800, t: 'Listo, visita agendada para el sáb 31/05 · 10:00 hs. Te llega el recordatorio por acá ✅', d: 1400 },
  ],
  [
    { divider: 'sábado 31/05', d: 700 },
    { side: 'out', typing: 950, t: '¡Hola! Te recuerdo que tu visita es hoy a las 10:00 hs 🗓️', d: 800 },
    { side: 'in',  t: '¡Sí! Ahí voy, muchas gracias 🙌', d: 800 },
    { side: 'out', typing: 800, t: 'Genial, te espero. Cualquier cosa me escribís por acá ✅', d: 2600 },
  ],
]

function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isIn = msg.side === 'in'

  if (msg.divider) {
    return (
      <div style={{
        alignSelf: 'center', background: 'rgba(255,255,255,.92)', color: 'var(--muted-soft)',
        fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 11, letterSpacing: '.02em',
        padding: '5px 12px', borderRadius: 'var(--radius-pill)', boxShadow: '0 1px 1px rgba(0,0,0,.06)',
        margin: '2px 0', animation: 'fadeIn .3s ease',
      }}>
        {msg.divider}
      </div>
    )
  }

  if (msg.card) {
    return (
      <div style={{
        alignSelf: 'flex-end', maxWidth: '86%', background: 'var(--whatsapp-bubble)',
        borderRadius: 12, borderTopRightRadius: 2, padding: 6, boxShadow: '0 1px 1px rgba(0,0,0,.08)',
      }}>
        <div style={{ borderRadius: 8, overflow: 'hidden', background: '#fff' }}>
          <div style={{ height: 96, background: 'linear-gradient(135deg, #2e6ea0, #164a71)', display: 'flex', alignItems: 'flex-end', padding: 8 }}>
            <Badge tone="emerald" dot style={{ fontSize: 11 }}>Disponible</Badge>
          </div>
          <div style={{ padding: '8px 10px 10px' }}>
            <div style={{ fontFamily: 'var(--font-body)', fontWeight: 700, fontSize: 13.5, color: 'var(--ink)' }}>Calle Carhué 262 · Villa Stemberg</div>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--muted-soft)', margin: '2px 0 6px' }}>Casa · 3 amb · 104 m²</div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 16, color: 'var(--primary)' }}>USD 78.962</div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{
      maxWidth: '82%', alignSelf: isIn ? 'flex-start' : 'flex-end',
      background: isIn ? '#fff' : 'var(--whatsapp-bubble)', padding: '8px 11px',
      borderRadius: 12, borderTopLeftRadius: isIn ? 2 : 12, borderTopRightRadius: !isIn ? 2 : 12,
      boxShadow: '0 1px 1px rgba(0,0,0,.08)', fontFamily: 'var(--font-body)',
      fontSize: 13.5, lineHeight: 1.42, color: '#111', animation: 'pop .22s ease',
    }}>
      {msg.t}
      <span style={{ fontSize: 10, color: 'rgba(0,0,0,.4)', float: 'right', margin: '6px 0 -2px 10px' }}>
        10:2{isIn ? '4' : '5'}
      </span>
    </div>
  )
}

function HeroChat() {
  const [scene, setScene]   = useState(0)
  const [step, setStep]     = useState(0)
  const [typing, setTyping] = useState(false)
  const scrollRef           = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    const timers: ReturnType<typeof setTimeout>[] = []

    const run = (s: number, i: number) => {
      const list = SCENES[s]
      if (cancelled) return
      if (i >= list.length) {
        const nextScene = (s + 1) % SCENES.length
        timers.push(setTimeout(() => {
          if (cancelled) return
          setTyping(false); setStep(0); setScene(nextScene)
          timers.push(setTimeout(() => run(nextScene, 0), 700))
        }, 1600))
        return
      }
      const msg = list[i]
      const advance = () => {
        if (cancelled) return
        setTyping(false)
        setStep(i + 1)
        timers.push(setTimeout(() => run(s, i + 1), msg.d))
      }
      if (msg.typing) { setTyping(true); timers.push(setTimeout(advance, msg.typing)) }
      else advance()
    }

    timers.push(setTimeout(() => run(0, 0), 600))
    return () => { cancelled = true; timers.forEach(clearTimeout) }
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [scene, step, typing])

  const visible = SCENES[scene].slice(0, step)

  return (
    <div style={{
      borderRadius: 'var(--radius-xl)', border: '1px solid var(--hairline)',
      background: '#fff', boxShadow: 'var(--shadow-lg)', overflow: 'hidden',
      maxWidth: 420, margin: '0 auto', width: '100%',
    }}>
      <div style={{ height: 58, background: 'var(--whatsapp-dark)', display: 'flex', alignItems: 'center', gap: 11, padding: '0 16px' }}>
        <span style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(255,255,255,.16)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon name="bot" size={20} color="#fff" />
        </span>
        <div>
          <div style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 14, color: '#fff' }}>Inmobiliaria Norte</div>
          <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'rgba(255,255,255,.8)', display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--whatsapp)' }} /> respondiendo…
          </div>
        </div>
        <Icon name="more-vertical" size={18} color="rgba(255,255,255,.8)" style={{ marginLeft: 'auto' }} />
      </div>

      <div ref={scrollRef} style={{
        background: 'var(--whatsapp-bg)',
        backgroundImage: 'radial-gradient(rgba(0,0,0,.035) 1px, transparent 1px)',
        backgroundSize: '15px 15px',
        padding: 16, display: 'flex', flexDirection: 'column', gap: 9,
        height: 392, overflowY: 'hidden', scrollBehavior: 'smooth',
      }}>
        {visible.map((r, i) => <ChatBubble key={i} msg={r} />)}
        {typing && (
          <div style={{ alignSelf: 'flex-end', background: 'var(--whatsapp-bubble)', padding: '11px 14px', borderRadius: 12, borderTopRightRadius: 2, display: 'flex', gap: 4 }}>
            {[0, 1, 2].map(d => (
              <span key={d} className="typing-dot" style={{ width: 7, height: 7, borderRadius: '50%', background: '#0f7568', animationDelay: `${d * 0.18}s` }} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Hero() {
  return (
    <section id="top" style={{ maxWidth: 1200, margin: '0 auto', padding: '76px 28px 64px' }}>
      <div className="hero-grid" style={{ display: 'grid', gridTemplateColumns: '1.05fr .95fr', gap: 56, alignItems: 'center' }}>
        <div>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12,
            letterSpacing: '.04em', textTransform: 'uppercase', color: 'var(--primary)',
            background: 'var(--brand-tint)', padding: '6px 12px', borderRadius: 'var(--radius-pill)',
          }}>
            <Icon name="sparkles" size={14} /> IA + WhatsApp para inmobiliarias
          </span>

          <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 56, lineHeight: 1.04, letterSpacing: '-2px', color: 'var(--ink)', margin: '20px 0 0' }}>
            Respondé cada consulta al instante, incluso mientras dormís.
          </h1>

          <p style={{ fontFamily: 'var(--font-body)', fontSize: 18, lineHeight: 1.55, color: 'var(--muted)', margin: '22px 0 0', maxWidth: 500 }}>
            ViviendApp atiende tu WhatsApp, busca propiedades, agenda las visitas y carga cada cliente en el CRM. Vos te dedicás a cerrar.
          </p>

          <div className="hero-cta" style={{ display: 'flex', gap: 12, marginTop: 30 }}>
            <LandingButton size="lg" icon="message-circle" variant="whatsapp" href="/signup">Empezar gratis</LandingButton>
            <LandingButton size="lg" variant="secondary" iconRight="play" href="#como-funciona">Ver cómo funciona</LandingButton>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 18, marginTop: 26, fontFamily: 'var(--font-body)', fontSize: 13.5, color: 'var(--muted-soft)' }}>
            {['30 días gratis', 'Sin tarjeta', 'Onboarding guiado'].map(item => (
              <span key={item} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <Icon name="check" size={15} color="var(--success)" /> {item}
              </span>
            ))}
          </div>
        </div>

        <HeroChat />
      </div>
    </section>
  )
}

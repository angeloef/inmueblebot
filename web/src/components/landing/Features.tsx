import { Icon, Reveal } from './atoms'

const FEATURES = [
  { icon: 'message-circle', t: 'Conversa de verdad, no por menús',  d: 'Entiende español rioplatense en lenguaje natural. Sin árboles de decisión: el cliente escribe como habla.' },
  { icon: 'search',         t: 'Busca en tu cartera',                d: 'Encuentra propiedades aunque escriban con errores o sin acentos, y manda fotos y datos por WhatsApp.' },
  { icon: 'calendar-check', t: 'Agenda visitas solo',                d: 'Coordina, reserva y recuerda, con sincronización automática a Google Calendar. Cero superposiciones.' },
  { icon: 'brain',          t: 'Recuerda a cada cliente',            d: 'Guarda zona, presupuesto y tipo de propiedad entre conversaciones. No pregunta lo que ya sabe.' },
  { icon: 'target',         t: 'Califica los clientes solo',         d: 'Puntúa cada contacto según la calidad de la charla y lo carga en el CRM con su estado.' },
  { icon: 'user-round',     t: 'Te pasa la posta cuando hace falta', d: 'Deriva a un agente humano si el cliente lo pide o si la consulta se sale de su alcance. Vos tenés el control.' },
]

export default function Features() {
  return (
    <section id="funciones" style={{ maxWidth: 1200, margin: '0 auto', padding: '92px 28px 0' }}>
      <Reveal style={{ textAlign: 'center', maxWidth: 660, margin: '0 auto 48px' }}>
        <span style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 12, letterSpacing: '.06em', textTransform: 'uppercase', color: 'var(--primary)' }}>Funciones</span>
        <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 40, letterSpacing: '-1.3px', color: 'var(--ink)', margin: '12px 0 0' }}>
          Un recepcionista que no duerme.
        </h2>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 17, color: 'var(--muted)', margin: '14px 0 0' }}>
          Atiende, busca, agenda y ordena. Todo lo que hoy hacés a mano, automático.
        </p>
      </Reveal>

      <div className="feat-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 20 }}>
        {FEATURES.map((it, i) => (
          <Reveal key={it.t} delay={(i % 3) * 80}>
            <div style={{ background: 'var(--surface-card)', borderRadius: 'var(--radius-lg)', padding: 30, height: '100%' }}>
              <span style={{ width: 46, height: 46, borderRadius: 12, background: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'var(--primary)', boxShadow: 'var(--shadow-sm)' }}>
                <Icon name={it.icon} size={22} />
              </span>
              <h3 style={{ fontFamily: 'var(--font-body)', fontWeight: 600, fontSize: 18, color: 'var(--ink)', margin: '20px 0 8px' }}>{it.t}</h3>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: 15, lineHeight: 1.55, color: 'var(--muted)', margin: 0 }}>{it.d}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  )
}

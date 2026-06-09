const features = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-6 h-6">
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    title: 'Captación de leads 24/7',
    description:
      'El bot atiende cada consulta de WhatsApp al instante, califica al interesado y lo guarda en tu CRM. Sin demoras, sin leads perdidos.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-6 h-6">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
    title: 'Búsqueda de propiedades',
    description:
      'Conectado a tu cartera, el bot muestra propiedades que se ajustan al presupuesto y preferencias del interesado en segundos.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-6 h-6">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
    title: 'Agenda de visitas',
    description:
      'Coordiná visitas automáticamente. El bot propone fechas disponibles, confirma con el interesado y actualiza tu calendario.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-6 h-6">
        <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
    title: 'CRM integrado',
    description:
      'Todos tus contactos, conversaciones y el estado de cada operación en un solo lugar. Sin planillas, sin post-its.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-6 h-6">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    title: 'Gestión de cobranzas',
    description:
      'Recordatorios de alquiler, seguimiento de pagos y notificaciones automáticas por WhatsApp a inquilinos y propietarios.',
  },
]

export default function Features() {
  return (
    <section
      id="funcionalidades"
      className="bg-white py-20 md:py-28 border-y border-surface-strong"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="text-center max-w-2xl mx-auto mb-14">
          <h2 className="font-display font-bold text-3xl sm:text-4xl text-ink-900">
            Todo lo que tu inmobiliaria necesita
          </h2>
          <p className="mt-3 text-ink-500 text-lg">
            Automatizá las tareas repetitivas y enfocate en cerrar operaciones.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f) => (
            <div
              key={f.title}
              className="bg-surface-soft rounded-xl p-6 border border-surface-strong hover:border-brand-tint-strong hover:shadow-card transition-all"
            >
              <div className="w-10 h-10 rounded-lg bg-brand-tint text-primary flex items-center justify-center mb-4">
                {f.icon}
              </div>
              <h3 className="font-display font-semibold text-ink-900 text-base mb-2">
                {f.title}
              </h3>
              <p className="text-ink-500 text-sm leading-relaxed">
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

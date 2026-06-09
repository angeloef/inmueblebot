const steps = [
  {
    number: '01',
    title: 'Conectás tu WhatsApp',
    description:
      'Vinculás tu número de WhatsApp Business en minutos. Sin instalaciones complicadas ni contratos con proveedores externos.',
  },
  {
    number: '02',
    title: 'El bot atiende y califica',
    description:
      'Cada lead que escribe recibe respuesta inmediata. El bot entiende qué busca, muestra propiedades relevantes y agenda visitas.',
  },
  {
    number: '03',
    title: 'Vos cerrás la venta',
    description:
      'Recibís notificaciones de leads calificados y visitas confirmadas. Solo intervenis cuando realmente importa: al cierre.',
  },
]

export default function HowItWorks() {
  return (
    <section id="como-funciona" className="py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        <div className="text-center max-w-2xl mx-auto mb-14">
          <h2 className="font-display font-bold text-3xl sm:text-4xl text-ink-900">
            ¿Cómo funciona?
          </h2>
          <p className="mt-3 text-ink-500 text-lg">
            En tres pasos, tu inmobiliaria trabaja sola mientras vos te enfocás
            en lo que importa.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 relative">
          {/* Connecting line (desktop) */}
          <div className="hidden md:block absolute top-8 left-[calc(16.666%+1rem)] right-[calc(16.666%+1rem)] h-px bg-brand-tint-strong" />

          {steps.map((step) => (
            <div key={step.number} className="flex flex-col items-center text-center gap-4">
              <div className="relative w-16 h-16 rounded-full bg-primary text-white font-display font-extrabold text-xl flex items-center justify-center shadow-md z-10">
                {step.number}
              </div>
              <h3 className="font-display font-semibold text-ink-900 text-lg">
                {step.title}
              </h3>
              <p className="text-ink-500 text-sm leading-relaxed max-w-xs">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

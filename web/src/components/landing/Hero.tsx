import WhatsappMock from './WhatsappMock'

export default function Hero() {
  return (
    <section className="max-w-6xl mx-auto px-4 sm:px-6 py-20 md:py-28 flex flex-col md:flex-row items-center gap-12">
      {/* Copy */}
      <div className="flex-1 flex flex-col gap-6 text-center md:text-left">
        <div className="inline-flex self-center md:self-start items-center gap-2 bg-brand-tint text-primary text-xs font-semibold px-3 py-1.5 rounded-full border border-brand-tint-strong">
          <span className="w-2 h-2 rounded-full bg-wa-green animate-pulse" />
          IA + WhatsApp para inmobiliarias
        </div>

        <h1 className="font-display font-extrabold text-4xl sm:text-5xl lg:text-6xl text-ink-900 leading-[1.1] tracking-tight">
          Captá leads y{' '}
          <span className="text-primary">agendá visitas</span>{' '}
          mientras dormís
        </h1>

        <p className="text-ink-500 text-lg sm:text-xl max-w-xl">
          ViviendApp conecta tu WhatsApp Business con IA para atender consultas,
          mostrar propiedades, calificar leads y agendar visitas — todo
          automáticamente, las 24 horas.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center md:justify-start">
          <a
            href="/signup"
            className="inline-flex items-center justify-center bg-primary text-white hover:bg-primary-hover font-semibold px-6 py-3.5 rounded-xl text-base transition-colors shadow-md"
          >
            Probar gratis 14 días
          </a>
          <a
            href="/#como-funciona"
            className="inline-flex items-center justify-center border border-surface-strong text-ink-700 hover:border-brand-accent hover:text-primary font-medium px-6 py-3.5 rounded-xl text-base transition-colors"
          >
            Ver cómo funciona
          </a>
        </div>

        <p className="text-ink-300 text-sm">
          Sin tarjeta de crédito. Cancelá cuando quieras.
        </p>
      </div>

      {/* Mock */}
      <div className="flex-shrink-0 w-full max-w-xs">
        <WhatsappMock />
      </div>
    </section>
  )
}

// TODO(Fase 3): integrar checkout con MercadoPago. Por ahora precios PLACEHOLDER.

interface PricingProps {
  showTitle?: boolean
}

export default function Pricing({ showTitle = true }: PricingProps) {
  return (
    <section id="precios" className="bg-white py-20 md:py-28 border-y border-surface-strong">
      <div className="max-w-6xl mx-auto px-4 sm:px-6">
        {showTitle && (
          <div className="text-center max-w-2xl mx-auto mb-14">
            <h2 className="font-display font-bold text-3xl sm:text-4xl text-ink-900">
              Precios simples y transparentes
            </h2>
            <p className="mt-3 text-ink-500 text-lg">
              Empezá con 14 días gratis. Sin tarjeta de crédito.
            </p>
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6 max-w-3xl mx-auto">
          {/* Starter */}
          <div className="rounded-2xl border border-surface-strong p-7 flex flex-col gap-5 bg-surface-soft">
            <div>
              <p className="text-sm font-semibold text-ink-500 uppercase tracking-wide">Starter</p>
              <div className="mt-2 flex items-end gap-1">
                <span className="font-display font-extrabold text-4xl text-ink-900">
                  $XX.XXX
                </span>
                <span className="text-ink-500 text-sm mb-1">/ mes</span>
              </div>
              <p className="mt-1 text-xs text-ink-300 italic">
                * Precio en ARS — pendiente definición (Fase 3)
              </p>
            </div>

            <ul className="flex flex-col gap-2.5 text-sm text-ink-700">
              {[
                '1 número de WhatsApp',
                'Hasta 200 conversaciones / mes',
                'Búsqueda de propiedades',
                'Agenda de visitas',
                'CRM básico',
              ].map((f) => (
                <li key={f} className="flex items-center gap-2">
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-state-success-fg flex-shrink-0">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                  {f}
                </li>
              ))}
            </ul>

            <a
              href="/signup"
              className="mt-auto inline-flex items-center justify-center border border-primary text-primary hover:bg-brand-tint font-semibold px-5 py-3 rounded-xl text-sm transition-colors"
            >
              Probar gratis 14 días
            </a>
          </div>

          {/* Pro */}
          <div className="rounded-2xl border-2 border-primary p-7 flex flex-col gap-5 bg-white shadow-md relative overflow-hidden">
            <div className="absolute top-4 right-4 bg-primary text-white text-xs font-bold px-3 py-1 rounded-full">
              Más popular
            </div>

            <div>
              <p className="text-sm font-semibold text-primary uppercase tracking-wide">Pro</p>
              <div className="mt-2 flex items-end gap-1">
                <span className="font-display font-extrabold text-4xl text-ink-900">
                  $XX.XXX
                </span>
                <span className="text-ink-500 text-sm mb-1">/ mes</span>
              </div>
              <p className="mt-1 text-xs text-ink-300 italic">
                * Precio en ARS — pendiente definición (Fase 3)
              </p>
            </div>

            <ul className="flex flex-col gap-2.5 text-sm text-ink-700">
              {[
                'Todo lo de Starter',
                'Hasta 2.000 conversaciones / mes',
                'Gestión de cobranzas',
                'Múltiples agentes',
                'Reportes avanzados',
                'Soporte prioritario',
              ].map((f) => (
                <li key={f} className="flex items-center gap-2">
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-primary flex-shrink-0">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                  {f}
                </li>
              ))}
            </ul>

            <a
              href="/signup"
              className="mt-auto inline-flex items-center justify-center bg-primary text-white hover:bg-primary-hover font-semibold px-5 py-3 rounded-xl text-sm transition-colors shadow-sm"
            >
              Probar gratis 14 días
            </a>
          </div>
        </div>
      </div>
    </section>
  )
}

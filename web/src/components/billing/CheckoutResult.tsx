/**
 * Post-checkout result card. MercadoPago redirects the payer back to one of the
 * /checkout/{success,failure,pending} routes; each renders this with a variant.
 *
 * Note: the authoritative subscription state comes from the signed webhook, not
 * this redirect — so the copy stays cautious ("estamos confirmando") rather than
 * asserting payment succeeded.
 */

type Variant = 'success' | 'failure' | 'pending'

interface CheckoutResultProps {
  variant: Variant
}

const CONTENT: Record<Variant, { emoji: string; title: string; body: string; cls: string }> = {
  success: {
    emoji: '✅',
    title: '¡Listo!',
    body: 'Recibimos tu autorización. Estamos confirmando el pago con MercadoPago; en unos instantes tu cuenta queda activa.',
    cls: 'text-state-success-fg',
  },
  pending: {
    emoji: '⏳',
    title: 'Pago pendiente',
    body: 'Tu pago está siendo procesado por MercadoPago. Te avisamos apenas se confirme. Podés volver al panel mientras tanto.',
    cls: 'text-state-warning-fg',
  },
  failure: {
    emoji: '⚠️',
    title: 'No se pudo completar',
    body: 'El pago no se concretó. No te cobramos nada. Podés intentar suscribirte de nuevo cuando quieras.',
    cls: 'text-state-warning-fg',
  },
}

export default function CheckoutResult({ variant }: CheckoutResultProps) {
  const { emoji, title, body, cls } = CONTENT[variant]
  return (
    <main className="min-h-screen bg-surface-soft flex items-center justify-center px-4 py-12">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-md p-8 flex flex-col gap-5 text-center">
        <span className="text-4xl">{emoji}</span>
        <h1 className={`font-display font-bold text-2xl ${cls}`}>{title}</h1>
        <p className="text-sm text-ink-700">{body}</p>
        <div className="flex flex-col gap-2 pt-2">
          <a
            href="/app"
            className="inline-flex items-center justify-center bg-primary text-white hover:bg-primary-hover font-semibold px-5 py-3 rounded-xl text-sm transition-colors"
          >
            Ir al panel
          </a>
          {variant !== 'success' && (
            <a
              href="/checkout"
              className="text-sm text-ink-500 hover:text-primary transition-colors"
            >
              Intentar de nuevo
            </a>
          )}
        </div>
      </div>
    </main>
  )
}

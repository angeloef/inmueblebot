/**
 * Subscription state banner for the dashboard.
 *
 * Presentational + server-safe: it receives the subscription status and trial
 * end date (already loaded by the page from /auth/me) and renders the right
 * call-to-action. Days-remaining is derived during render — no effects, no state.
 */

interface TrialBannerProps {
  status: string
  trialEndsAt: string | null
}

const MS_PER_DAY = 1000 * 60 * 60 * 24

function daysRemaining(trialEndsAt: string | null): number | null {
  if (!trialEndsAt) return null
  const end = new Date(trialEndsAt).getTime()
  if (Number.isNaN(end)) return null
  return Math.ceil((end - Date.now()) / MS_PER_DAY)
}

export default function TrialBanner({ status, trialEndsAt }: TrialBannerProps) {
  // Active subscription → quiet confirmation, no CTA.
  if (status === 'active') {
    return (
      <div className="rounded-xl bg-state-success-bg border border-state-success-fg/30 p-4 flex items-center gap-2">
        <span className="text-state-success-fg">✓</span>
        <p className="text-sm text-state-success-fg font-medium">
          Suscripción activa. ¡Gracias!
        </p>
      </div>
    )
  }

  const remaining = daysRemaining(trialEndsAt)
  const trialActive = status === 'trial' && remaining !== null && remaining > 0

  if (trialActive) {
    return (
      <div className="rounded-xl bg-state-info-bg border border-brand-tint-strong p-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <p className="text-sm text-primary font-medium flex-1">
          Prueba gratis: te {remaining === 1 ? 'queda' : 'quedan'}{' '}
          <strong>{remaining}</strong> {remaining === 1 ? 'día' : 'días'}.
        </p>
        <a
          href="/checkout"
          className="inline-flex items-center justify-center bg-primary text-white hover:bg-primary-hover font-semibold px-4 py-2 rounded-lg text-sm transition-colors whitespace-nowrap"
        >
          Suscribirme
        </a>
      </div>
    )
  }

  // Trial expired, paused, cancelled, past_due, or unknown → require subscription.
  return (
    <div className="rounded-xl bg-state-warning-bg border border-state-warning-fg/30 p-4 flex flex-col sm:flex-row sm:items-center gap-3">
      <p className="text-sm text-state-warning-fg font-medium flex-1">
        Tu prueba terminó. Suscribite para seguir usando ViviendApp.
      </p>
      <a
        href="/checkout"
        className="inline-flex items-center justify-center bg-primary text-white hover:bg-primary-hover font-semibold px-4 py-2 rounded-lg text-sm transition-colors whitespace-nowrap"
      >
        Suscribirme
      </a>
    </div>
  )
}

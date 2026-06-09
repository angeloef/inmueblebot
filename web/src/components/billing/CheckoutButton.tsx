'use client'

import { useState } from 'react'
import Button from '@/components/ui/Button'
import Alert from '@/components/ui/Alert'

/**
 * Starts the MercadoPago subscription: calls the server route handler (which
 * forwards the httpOnly JWT) and redirects the browser to the returned
 * `init_point`. Errors are surfaced inline; the JWT never touches the client.
 */
export default function CheckoutButton({ label = 'Suscribirme ahora' }: { label?: string }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubscribe() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/billing/subscribe', { method: 'POST' })
      const data = (await res.json()) as { init_point?: string; error?: string }

      if (!res.ok || !data.init_point) {
        setError(data.error ?? 'No pudimos iniciar la suscripción. Probá de nuevo.')
        setLoading(false)
        return
      }
      // Redirect to MercadoPago. Keep loading=true so the button stays disabled
      // during the navigation.
      window.location.href = data.init_point
    } catch {
      setError('Error de conexión. Probá de nuevo en unos minutos.')
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {error && <Alert variant="error">{error}</Alert>}
      <Button
        variant="primary"
        size="lg"
        loading={loading}
        onClick={handleSubscribe}
        className="w-full"
      >
        {label}
      </Button>
    </div>
  )
}

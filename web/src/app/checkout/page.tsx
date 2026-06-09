import type { Metadata } from 'next'
import { redirect } from 'next/navigation'
import { getSessionReadOnly } from '@/lib/auth'
import CheckoutButton from '@/components/billing/CheckoutButton'

export const metadata: Metadata = {
  title: 'Suscripción',
}

const PLAN_PRICE = process.env.NEXT_PUBLIC_PLAN_PRICE_ARS // optional display only

export default async function CheckoutPage() {
  const session = await getSessionReadOnly()
  if (!session) redirect('/login?next=/checkout')
  if (session.subscription?.status === 'active') redirect('/app')

  return (
    <main className="min-h-screen bg-surface-soft flex items-center justify-center px-4 py-12">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-md p-8 flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <h1 className="font-display font-bold text-2xl text-ink-900">
            Activá tu suscripción
          </h1>
          <p className="text-sm text-ink-500">
            Pagás con MercadoPago de forma segura. Podés cancelar cuando quieras.
          </p>
        </div>

        <div className="rounded-xl border border-surface-strong bg-surface-card p-5 flex flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <span className="font-display font-semibold text-ink-900">
              Plan mensual
            </span>
            {PLAN_PRICE && (
              <span className="text-lg font-bold text-primary">
                ${PLAN_PRICE}
                <span className="text-xs font-normal text-ink-500"> ARS/mes</span>
              </span>
            )}
          </div>
          <ul className="flex flex-col gap-2 text-sm text-ink-700">
            <li className="flex items-center gap-2">
              <span className="text-state-success-fg">✓</span> Bot de WhatsApp para tu inmobiliaria
            </li>
            <li className="flex items-center gap-2">
              <span className="text-state-success-fg">✓</span> Panel de gestión y cobranzas
            </li>
            <li className="flex items-center gap-2">
              <span className="text-state-success-fg">✓</span> Soporte y actualizaciones
            </li>
          </ul>
        </div>

        <CheckoutButton label="Suscribirme con MercadoPago" />

        <a
          href="/app"
          className="text-center text-sm text-ink-500 hover:text-primary transition-colors"
        >
          Volver al panel
        </a>
      </div>
    </main>
  )
}

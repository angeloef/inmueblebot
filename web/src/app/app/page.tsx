import type { Metadata } from 'next'
import { getSessionReadOnly } from '@/lib/auth'
import TrialBanner from '@/components/billing/TrialBanner'

export const metadata: Metadata = {
  title: 'Panel',
}

export default async function AppPage() {
  const session = await getSessionReadOnly()

  return (
    <main className="min-h-screen bg-surface-soft flex items-center justify-center px-4">
      <div className="max-w-lg w-full bg-white rounded-2xl shadow-md p-8 flex flex-col gap-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-brand-tint flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="w-5 h-5 text-primary">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
          </div>
          <h1 className="font-display font-bold text-xl text-ink-900">
            Panel de ViviendApp
          </h1>
        </div>

        {session?.subscription && (
          <TrialBanner
            status={session.subscription.status}
            trialEndsAt={session.subscription.trial_ends_at}
          />
        )}

        <div className="rounded-xl bg-state-info-bg border border-brand-tint-strong p-4">
          <p className="text-sm text-primary font-medium">
            Sesión iniciada. El panel completo se conecta en la Fase 4.
          </p>
        </div>

        {session ? (
          <div className="rounded-xl bg-surface-card border border-surface-strong p-4 flex flex-col gap-2 text-sm">
            <p className="font-semibold text-ink-700 mb-1">Datos de tu cuenta</p>
            <div className="flex justify-between">
              <span className="text-ink-500">Email</span>
              <span className="text-ink-900 font-mono text-xs">{session.account.email}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-500">Nombre</span>
              <span className="text-ink-900">{session.account.full_name || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-500">Rol</span>
              <span className="text-ink-900">{session.account.role}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-500">Tenant</span>
              <span className="text-ink-900 font-mono text-xs">{session.tenant_slug}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-500">Estado</span>
              <span className="text-ink-900">{session.tenant_status}</span>
            </div>
            {session.subscription && (
              <div className="flex justify-between">
                <span className="text-ink-500">Plan</span>
                <span className="text-ink-900">
                  {session.subscription.plan} · {session.subscription.status}
                </span>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-ink-500">
            No se pudo cargar la sesión. Intentá{' '}
            <a href="/login" className="text-brand-accent hover:underline">
              iniciando sesión nuevamente
            </a>
            .
          </p>
        )}

        <form action="/api/auth/logout" method="POST">
          <button
            type="submit"
            className="text-sm text-ink-500 hover:text-red-600 transition-colors"
          >
            Cerrar sesión
          </button>
        </form>
      </div>
    </main>
  )
}

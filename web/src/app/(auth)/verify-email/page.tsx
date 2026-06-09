import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Verificar email',
}

const API_BASE =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

interface VerifyEmailPageProps {
  searchParams: Promise<{ token?: string }>
}

export default async function VerifyEmailPage({
  searchParams,
}: VerifyEmailPageProps) {
  const { token } = await searchParams

  if (!token) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Enlace inválido
        </h1>
        <p className="text-sm text-ink-500">
          No se encontró el token de verificación.
        </p>
      </div>
    )
  }

  let verified = false
  let errorMessage = ''

  try {
    const res = await fetch(
      `${API_BASE}/auth/verify-email?token=${encodeURIComponent(token)}`,
      { cache: 'no-store' },
    )
    if (res.ok) {
      verified = true
    } else if (res.status === 400 || res.status === 401) {
      errorMessage = 'El enlace de verificación es inválido o ya expiró.'
    } else {
      errorMessage = 'Error del servidor. Intentá de nuevo más tarde.'
    }
  } catch {
    errorMessage = 'No pudimos conectarnos al servidor. Intentá de nuevo.'
  }

  if (verified) {
    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-xl bg-state-success-bg border border-green-200 p-5">
          <h1 className="font-display font-bold text-xl text-state-success-fg">
            ¡Email verificado!
          </h1>
          <p className="mt-2 text-sm text-ink-700">
            Tu email fue verificado correctamente. Ya podés ingresar a tu cuenta.
          </p>
        </div>
        <a
          href="/login"
          className="text-center text-sm text-brand-accent hover:text-primary font-medium"
        >
          Iniciar sesión →
        </a>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl bg-state-error-bg border border-red-200 p-5">
        <h1 className="font-display font-bold text-xl text-red-800">
          Verificación fallida
        </h1>
        <p className="mt-2 text-sm text-ink-700">{errorMessage}</p>
      </div>
      <a
        href="/login"
        className="text-center text-sm text-brand-accent hover:text-primary font-medium"
      >
        ← Volver al inicio de sesión
      </a>
    </div>
  )
}

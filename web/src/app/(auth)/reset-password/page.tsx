import type { Metadata } from 'next'
import ResetForm from '@/components/auth/ResetForm'

export const metadata: Metadata = {
  title: 'Nueva contraseña',
}

interface ResetPasswordPageProps {
  searchParams: Promise<{ token?: string }>
}

export default async function ResetPasswordPage({
  searchParams,
}: ResetPasswordPageProps) {
  const { token } = await searchParams

  if (!token) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Enlace inválido
        </h1>
        <p className="text-sm text-ink-500">
          Este enlace de restablecimiento es inválido o ya expiró.
        </p>
        <a
          href="/forgot-password"
          className="text-sm text-brand-accent hover:text-primary font-medium"
        >
          Solicitá un nuevo enlace →
        </a>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Nueva contraseña
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Elegí una contraseña segura de al menos 8 caracteres.
        </p>
      </div>

      <ResetForm token={token} />
    </div>
  )
}

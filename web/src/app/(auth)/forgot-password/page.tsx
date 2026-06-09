import type { Metadata } from 'next'
import ForgotForm from '@/components/auth/ForgotForm'

export const metadata: Metadata = {
  title: 'Recuperar contraseña',
}

export default function ForgotPasswordPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Recuperar contraseña
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Ingresá tu email y te enviamos las instrucciones.
        </p>
      </div>

      <ForgotForm />

      <p className="text-center text-sm text-ink-500">
        <a href="/login" className="text-brand-accent hover:text-primary font-medium">
          ← Volver al inicio de sesión
        </a>
      </p>
    </div>
  )
}

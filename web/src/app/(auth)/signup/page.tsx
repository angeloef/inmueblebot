import type { Metadata } from 'next'
import SignupForm from '@/components/auth/SignupForm'

export const metadata: Metadata = {
  title: 'Crear cuenta',
}

export default function SignupPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Empezá gratis
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          14 días de prueba, sin tarjeta de crédito.
        </p>
      </div>

      <SignupForm />

      <p className="text-center text-sm text-ink-500">
        ¿Ya tenés cuenta?{' '}
        <a href="/login" className="text-brand-accent hover:text-primary font-medium">
          Iniciá sesión
        </a>
      </p>
    </div>
  )
}

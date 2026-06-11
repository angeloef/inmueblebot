import type { Metadata } from 'next'
import LoginForm from '@/components/auth/LoginForm'

export const metadata: Metadata = {
  title: 'Ingresar',
}

interface LoginPageProps {
  searchParams: Promise<{ next?: string; error?: string }>
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { next, error } = await searchParams
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Iniciá sesión
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          Ingresá a tu cuenta de ViviendApp.
        </p>
      </div>

      <LoginForm next={next} errorCode={error} />

      <p className="text-center text-sm text-ink-500">
        ¿No tenés cuenta?{' '}
        <a href="/signup" className="text-brand-accent hover:text-primary font-medium">
          Registrate gratis
        </a>
      </p>
    </div>
  )
}

import type { Metadata } from 'next'
import GoogleCompleteForm from '@/components/auth/GoogleCompleteForm'

export const metadata: Metadata = {
  title: 'Completá tu registro',
}

interface CompletePageProps {
  searchParams: Promise<{ gt?: string }>
}

/**
 * Lee el `email` del registration token SOLO para mostrarlo (no se verifica acá:
 * la firma la valida la API al hacer submit). Devuelve '' ante cualquier problema.
 */
function emailFromToken(token: string | undefined): string {
  if (!token) return ''
  try {
    const payload = token.split('.')[1]
    if (!payload) return ''
    const json = Buffer.from(payload, 'base64url').toString('utf-8')
    const claims = JSON.parse(json) as { email?: string }
    return typeof claims.email === 'string' ? claims.email : ''
  } catch {
    return ''
  }
}

export default async function SignupCompletePage({ searchParams }: CompletePageProps) {
  const { gt } = await searchParams
  const email = emailFromToken(gt)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-ink-900">
          Un último paso
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          ¿Cómo se llama tu inmobiliaria? Empezás con 14 días gratis, sin tarjeta.
        </p>
      </div>

      <GoogleCompleteForm token={gt ?? ''} email={email} />
    </div>
  )
}
